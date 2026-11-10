"""Port history and free ports (finding a port for a new connection)."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.core.errors import NotFoundError
from app.domain.switch import PortKind
from app.models import (
    Building,
    Client,
    Device,
    DeviceStatus,
    FdbEntry,
    LldpNeighbor,
    Port,
    PortEvent,
    PortMacSighting,
    Room,
)
from app.services.access import require_site_access
from app.services.clients import vendors_for
from app.services.context import Caller
from app.services.devices import get_device
from app.services.uplinks import uplink_port_ids

EVENT_LIMIT = 200
SIGHTING_LIMIT = 200
#: devices listed per port in the front panel tooltip
CONNECTED_LIMIT = 3


async def port_history(
    db: AsyncSession, caller: Caller, device_id: int, port_id: int
) -> dict[str, Any]:
    await get_device(db, caller, device_id)
    port = await db.get(Port, port_id)
    if port is None or port.device_id != device_id:
        raise NotFoundError("Port not found")
    events = (
        (
            await db.execute(
                select(PortEvent)
                .where(PortEvent.port_id == port_id)
                .order_by(PortEvent.at.desc(), PortEvent.id.desc())
                .limit(EVENT_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    sightings = (
        (
            await db.execute(
                select(PortMacSighting)
                .where(PortMacSighting.port_id == port_id)
                .order_by(PortMacSighting.last_seen_at.desc())
                .limit(SIGHTING_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    macs = [s.mac_address for s in sightings]
    vendors = await vendors_for(db, macs)
    clients = {
        c.mac_address: c
        for c in (await db.execute(select(Client).where(Client.mac_address.in_(macs)))).scalars()
    }
    return {
        "events": [
            {
                "at": e.at,
                "kind": e.kind.value,
                "actor": e.actor,
                "old": e.detail.get("old"),
                "new": e.detail.get("new"),
            }
            for e in events
        ],
        "devices": [
            {
                "mac_address": s.mac_address,
                "vid": s.vid,
                "first_seen_at": s.first_seen_at,
                "last_seen_at": s.last_seen_at,
                "vendor": vendors.get(s.mac_address),
                "ip_address": c.ip_address if (c := clients.get(s.mac_address)) else None,
                "hostname": c.hostname if c else None,
            }
            for s in sightings
        ],
    }


async def switch_ports(
    db: AsyncSession,
    caller: Caller,
    site_id: int,
    *,
    building_id: int | None = None,
    room_id: int | None = None,
    min_days: int = 30,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    """All ethernet ports of the site's switches, grouped by switch, for the front panel view.

    A port is *free* when it is not an uplink, has no link, and neither went down nor had a
    device within ``min_days`` (disabled ports only count with ``include_disabled``).
    """
    require_site_access(caller.user, site_id)
    stmt = (
        select(Device, Room, Building)
        .outerjoin(Room, Room.id == Device.room_id)
        .outerjoin(Building, Building.id == Room.building_id)
        .where(Device.site_id == site_id, Device.status != DeviceStatus.UNCONFIRMED)
        .order_by(Building.name, Room.name, Device.name)
    )
    if room_id is not None:
        stmt = stmt.where(Device.room_id == room_id)
    elif building_id is not None:
        stmt = stmt.where(Room.building_id == building_id)
    rows = (await db.execute(stmt)).tuples().all()
    if not rows:
        return []

    cutoff = utcnow() - timedelta(days=min_days)
    device_ids = [d.id for d, _, _ in rows]
    uplinks = await uplink_port_ids(db)
    sighting_rows = await db.execute(
        select(PortMacSighting.port_id, func.max(PortMacSighting.last_seen_at))
        .join(Port, Port.id == PortMacSighting.port_id)
        .where(Port.device_id.in_(device_ids))
        .group_by(PortMacSighting.port_id)
    )
    last_device = {port_id: seen for port_id, seen in sighting_rows.all()}
    ports = (
        (
            await db.execute(
                select(Port)
                .where(Port.device_id.in_(device_ids), Port.kind == PortKind.ETHERNET)
                .order_by(Port.device_id, Port.if_index)
            )
        )
        .scalars()
        .all()
    )
    connected, mac_counts = await _connected(db, [p.id for p in ports], uplinks)
    neighbors = {
        n.port_id: n
        for n in (
            await db.execute(select(LldpNeighbor).where(LldpNeighbor.device_id.in_(device_ids)))
        ).scalars()
        if n.port_id is not None
    }
    by_device: dict[int, list[dict[str, Any]]] = {}
    for port in ports:
        uplink = port.id in uplinks
        neighbor = neighbors.get(port.id)
        down_since = (
            ensure_utc(port.last_change_at) if port.last_change_at and not port.oper_up else None
        )
        seen = last_device.get(port.id)
        free = (
            not uplink
            and not port.oper_up
            and (include_disabled or port.admin_up)
            and not (down_since and down_since > cutoff)
            and not (seen and ensure_utc(seen) > cutoff)
        )
        by_device.setdefault(port.device_id, []).append(
            {
                "id": port.id,
                "name": port.name,
                "if_index": port.if_index,
                "description": port.description,
                "admin_up": port.admin_up,
                "oper_up": port.oper_up,
                "speed_mbps": port.speed_mbps,
                "uplink": uplink,
                "free": free,
                "down_since": down_since,
                "last_device_at": seen,
                "untagged_vlans": [v.vid for v in port.vlans if not v.tagged],
                "tagged_count": sum(1 for v in port.vlans if v.tagged),
                "poe": port.poe is not None,
                "neighbor": (
                    f"{neighbor.system_name or neighbor.chassis_id} ({neighbor.remote_port})"
                    if neighbor
                    else None
                ),
                "connected": connected.get(port.id, []),
                "mac_count": mac_counts.get(port.id, 0),
            }
        )
    return [
        {
            "device_id": device.id,
            "device_name": device.name,
            "model": device.model,
            "model_name": device.model_name,
            "status": device.status,
            "room": room.name if room else None,
            "building": building.name if building else None,
            "ports": by_device[device.id],
        }
        for device, room, building in rows
        if by_device.get(device.id)
    ]


async def _connected(
    db: AsyncSession, port_ids: list[int], uplinks: set[int]
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, int]]:
    """Devices currently in the MAC table of each access port (a few per port, plus the count)."""
    access = [p for p in port_ids if p not in uplinks]
    if not access:
        return {}, {}
    rows = (
        await db.execute(
            select(FdbEntry.port_id, FdbEntry.mac_address)
            .where(FdbEntry.port_id.in_(access))
            .order_by(FdbEntry.port_id, FdbEntry.mac_address)
        )
    ).all()
    per_port: dict[int, list[str]] = {}
    for port_id, mac in rows:
        if port_id is None:
            continue
        macs = per_port.setdefault(port_id, [])
        if mac not in macs:
            macs.append(mac)
    shown = sorted({m for macs in per_port.values() for m in macs[:CONNECTED_LIMIT]})
    vendors = await vendors_for(db, shown)
    clients = {
        c.mac_address: c
        for c in (await db.execute(select(Client).where(Client.mac_address.in_(shown)))).scalars()
    }
    connected = {
        port_id: [
            {
                "mac_address": mac,
                "vendor": vendors.get(mac),
                "ip_address": c.ip_address if (c := clients.get(mac)) else None,
                "hostname": c.hostname if c else None,
            }
            for mac in macs[:CONNECTED_LIMIT]
        ]
        for port_id, macs in per_port.items()
    }
    return connected, {port_id: len(macs) for port_id, macs in per_port.items()}
