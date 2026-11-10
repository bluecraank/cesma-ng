"""Live port finder: which port just went up, and what is connected to it.

Someone plugs a device in somewhere, someone else watches in cesma-ng. While the view is open,
the link state (ifOperStatus only, one small SNMP walk) of all switches of the site is read every
few seconds. Changes are stored like the regular poll does (port state, port history). For ports
that just came up, the MAC table of that switch is read again shortly after, so the connected
device shows up as soon as it sends its first frames.

Scans are throttled per site and the MAC table reads per switch, so several people watching do
not multiply the load on the switches.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.core.db import utcnow
from app.drivers.registry import driver_for
from app.models import (
    ArpEntry,
    Building,
    Client,
    CredentialProfile,
    Device,
    DeviceStatus,
    FdbEntry,
    Port,
    PortEvent,
    PortEventKind,
    Room,
)
from app.services import events, inventory
from app.services.access import require_site_access
from app.services.clients import vendors_for
from app.services.context import Caller
from app.services.credentials import to_device_credentials
from app.services.inventory import InventoryChanges
from app.services.polling import snmp_client
from app.services.uplinks import uplink_port_ids

log = logging.getLogger(__name__)

#: at most one link scan per site in this time (several viewers share it)
SCAN_INTERVAL = 4.0
#: at most one MAC table read per switch in this time
FDB_INTERVAL = 10.0
#: how long after a link came up the MAC table is read again, while no device shows up
FDB_WINDOW = timedelta(minutes=3)
#: per switch, for the link state walk
SCAN_TIMEOUT = 5.0
FDB_TIMEOUT = 20.0
PARALLEL = 10
#: ports listed, and link-up events looked at (a flapping port has several)
PORT_LIMIT = 50
EVENT_LIMIT = 500
DEVICES_PER_PORT = 5


@dataclass
class _SiteState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_scan: float = 0.0
    scanned_at: datetime | None = None
    unreachable: list[str] = field(default_factory=list)


_sites: dict[int, _SiteState] = {}
_last_fdb: dict[int, float] = {}


async def scan(
    db: AsyncSession,
    caller: Caller,
    site_id: int,
    *,
    since: datetime,
    settings: Settings,
    box: SecretBox,
) -> dict[str, Any]:
    """Scan the site's switches (throttled) and return the ports that went up since ``since``."""
    require_site_access(caller.user, site_id)
    state = _sites.setdefault(site_id, _SiteState())
    async with state.lock:
        if time.monotonic() - state.last_scan >= SCAN_INTERVAL:
            state.unreachable = await _scan_site(db, site_id, settings, box)
            state.last_scan = time.monotonic()
            state.scanned_at = utcnow()
    return {
        "scanned_at": state.scanned_at,
        "unreachable": state.unreachable,
        "events": await recent_link_ups(db, site_id, since),
    }


async def _scan_site(
    db: AsyncSession, site_id: int, settings: Settings, box: SecretBox
) -> list[str]:
    devices = (
        (
            await db.execute(
                select(Device).where(
                    Device.site_id == site_id, Device.status == DeviceStatus.ONLINE
                )
            )
        )
        .scalars()
        .all()
    )
    if not devices:
        return []
    profiles = {
        p.id: p
        for p in (
            await db.execute(
                select(CredentialProfile).where(
                    CredentialProfile.id.in_(
                        {d.credential_profile_id for d in devices if d.credential_profile_id}
                    )
                )
            )
        ).scalars()
    }
    drivers = {
        d.id: driver_for(
            d.model,
            snmp_client(
                settings,
                d.hostname,
                to_device_credentials(profiles.get(d.credential_profile_id or -1), box),
                quick=True,
            ),
        )
        for d in devices
    }

    # network reads run in parallel, the database is updated afterwards (one session)
    limit = asyncio.Semaphore(PARALLEL)

    async def read(device: Device) -> dict[int, bool] | None:
        async with limit:
            try:
                async with asyncio.timeout(SCAN_TIMEOUT):
                    return await drivers[device.id].read_link_states()
            except Exception as exc:  # one unreachable switch must not stop the scan
                log.info("link scan of %s failed: %s", device.name, exc)
                return None

    states = await asyncio.gather(*(read(d) for d in devices))
    unreachable = [d.name for d, s in zip(devices, states, strict=True) if s is None]
    went_up: list[Device] = []
    for device, links in zip(devices, states, strict=True):
        if links and await _apply_links(db, device, links):
            went_up.append(device)
    await db.commit()

    # MAC tables of switches with ports that came up recently and show no device yet
    waiting = await _waiting_for_device(db, [d.id for d in devices])
    due = [
        d
        for d in devices
        if d.id in waiting and time.monotonic() - _last_fdb.get(d.id, 0.0) >= FDB_INTERVAL
    ]

    async def read_fdb(device: Device) -> Any:
        async with limit:
            _last_fdb[device.id] = time.monotonic()
            try:
                async with asyncio.timeout(FDB_TIMEOUT):
                    return await drivers[device.id].read_fdb()
            except Exception as exc:
                log.info("MAC table read of %s failed: %s", device.name, exc)
                return None

    tables = await asyncio.gather(*(read_fdb(d) for d in due))
    for device, entries in zip(due, tables, strict=True):
        if entries is not None:
            await inventory.apply_fdb(db, device, entries)
    await db.commit()
    return unreachable


async def _apply_links(db: AsyncSession, device: Device, links: dict[int, bool]) -> bool:
    """Store link changes like the regular inventory poll does; returns whether a link came up."""
    ports = (await db.execute(select(Port).where(Port.device_id == device.id))).scalars().all()
    changes = InventoryChanges()
    now = utcnow()
    for port in ports:
        up = links.get(port.if_index)
        if up is None or up == port.oper_up:
            continue
        port.oper_up = up
        port.last_change_at = now
        (changes.links_up if up else changes.links_down).append(port.name)
        kind = PortEventKind.LINK_UP if up else PortEventKind.LINK_DOWN
        db.add(PortEvent(port_id=port.id, at=now, kind=kind, detail={}))
    if changes.links_up or changes.links_down:
        device.last_seen_at = now
        await events.port_changes(db, device, changes)
    return bool(changes.links_up)


async def _waiting_for_device(db: AsyncSession, device_ids: list[int]) -> set[int]:
    """Switches with an access port that came up within the window and has no MAC entry yet."""
    recent = (
        await db.execute(
            select(Port.id, Port.device_id)
            .join(PortEvent, PortEvent.port_id == Port.id)
            .where(
                Port.device_id.in_(device_ids),
                Port.oper_up.is_(True),
                PortEvent.kind == PortEventKind.LINK_UP,
                PortEvent.at >= utcnow() - FDB_WINDOW,
            )
        )
    ).all()
    if not recent:
        return set()
    uplinks = await uplink_port_ids(db)
    with_mac = set(
        (
            await db.execute(
                select(FdbEntry.port_id).where(FdbEntry.port_id.in_([p for p, _ in recent]))
            )
        ).scalars()
    )
    return {d for p, d in recent if p not in uplinks and p not in with_mac}


async def recent_link_ups(db: AsyncSession, site_id: int, since: datetime) -> list[dict[str, Any]]:
    """Ports of the site that went up since ``since`` (newest first), with what is connected."""
    rows = (
        (
            await db.execute(
                select(PortEvent, Port, Device, Room, Building)
                .join(Port, Port.id == PortEvent.port_id)
                .join(Device, Device.id == Port.device_id)
                .outerjoin(Room, Room.id == Device.room_id)
                .outerjoin(Building, Building.id == Room.building_id)
                .where(
                    Device.site_id == site_id,
                    PortEvent.kind == PortEventKind.LINK_UP,
                    PortEvent.at >= since,
                )
                .order_by(PortEvent.at.desc(), PortEvent.id.desc())
                .limit(EVENT_LIMIT)
            )
        )
        .tuples()
        .all()
    )
    if not rows:
        return []
    # one entry per port (newest link-up); a port that flapped while being plugged in, or whose
    # change was also seen by the regular poll, must not show up twice
    ups: dict[int, int] = {}
    latest = []
    for row in rows:
        port_id = row[1].id
        if port_id not in ups:
            latest.append(row)
        ups[port_id] = ups.get(port_id, 0) + 1
    rows = latest[:PORT_LIMIT]
    port_ids = [port.id for _, port, _, _, _ in rows]
    uplinks = await uplink_port_ids(db)
    macs: dict[int, list[str]] = {}
    for fdb_port, mac in (
        await db.execute(
            select(FdbEntry.port_id, FdbEntry.mac_address)
            .where(FdbEntry.port_id.in_(port_ids))
            .order_by(FdbEntry.mac_address)
        )
    ).all():
        if fdb_port is not None and mac not in macs.setdefault(fdb_port, []):
            macs[fdb_port].append(mac)
    all_macs = sorted({m for found in macs.values() for m in found[:DEVICES_PER_PORT]})
    vendors = await vendors_for(db, all_macs)
    clients = {
        c.mac_address: c
        for c in (
            await db.execute(select(Client).where(Client.mac_address.in_(all_macs)))
        ).scalars()
    }
    arp = {
        a.mac_address: a.ip_address
        for a in (
            await db.execute(select(ArpEntry).where(ArpEntry.mac_address.in_(all_macs)))
        ).scalars()
    }

    def connected(mac: str) -> dict[str, Any]:
        client = clients.get(mac)
        return {
            "mac_address": mac,
            "vendor": vendors.get(mac),
            "ip_address": (client.ip_address if client else None) or arp.get(mac),
            "hostname": client.hostname if client else None,
        }

    return [
        {
            "at": event.at,
            "port_id": port.id,
            "port": port.name,
            "description": port.description,
            "still_up": port.oper_up,
            "uplink": port.id in uplinks,
            "speed_mbps": port.speed_mbps,
            "untagged_vlans": [v.vid for v in port.vlans if not v.tagged],
            "tagged_vlans": [v.vid for v in port.vlans if v.tagged],
            "device_id": device.id,
            "device_name": device.name,
            "building": building.name if building else None,
            "room": room.name if room else None,
            "connected": [connected(m) for m in macs.get(port.id, [])[:DEVICES_PER_PORT]],
            "mac_count": len(macs.get(port.id, [])),
            "link_ups": ups[port.id],
        }
        for event, port, device, room, building in rows
    ]
