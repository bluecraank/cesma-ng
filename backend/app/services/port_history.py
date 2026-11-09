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


async def free_ports(
    db: AsyncSession,
    caller: Caller,
    site_id: int,
    *,
    building_id: int | None = None,
    room_id: int | None = None,
    min_days: int = 30,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    """Access ports that are down and had no device for ``min_days``, grouped by switch."""
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
    candidates = (
        (
            await db.execute(
                select(Port)
                .where(
                    Port.device_id.in_(device_ids),
                    Port.kind == PortKind.ETHERNET,
                    Port.oper_up.is_(False),
                )
                .order_by(Port.device_id, Port.if_index)
            )
        )
        .scalars()
        .all()
    )
    by_device: dict[int, list[dict[str, Any]]] = {}
    for port in candidates:
        if port.id in uplinks or (not include_disabled and not port.admin_up):
            continue
        down_since = ensure_utc(port.last_change_at) if port.last_change_at else None
        seen = last_device.get(port.id)
        if (down_since and down_since > cutoff) or (seen and ensure_utc(seen) > cutoff):
            continue
        by_device.setdefault(port.device_id, []).append(
            {
                "id": port.id,
                "name": port.name,
                "description": port.description,
                "admin_up": port.admin_up,
                "down_since": down_since,
                "last_device_at": seen,
                "untagged_vlans": [v.vid for v in port.vlans if not v.tagged],
                "poe": port.poe is not None,
            }
        )
    return [
        {
            "device_id": device.id,
            "device_name": device.name,
            "room": room.name if room else None,
            "building": building.name if building else None,
            "ports": by_device[device.id],
        }
        for device, room, building in rows
        if by_device.get(device.id)
    ]
