"""Read views of the polled state, assembled for the UI."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ArpEntry,
    Device,
    DevicePollState,
    DeviceVlan,
    FdbEntry,
    LldpNeighbor,
    Port,
)
from app.services.context import Caller
from app.services.devices import get_device
from app.services.uplinks import uplink_port_ids


async def list_ports(db: AsyncSession, caller: Caller, device_id: int) -> list[dict[str, Any]]:
    await get_device(db, caller, device_id)
    ports = (
        (await db.execute(select(Port).where(Port.device_id == device_id).order_by(Port.if_index)))
        .scalars()
        .all()
    )
    uplinks = await uplink_port_ids(db, device_id)
    counted = await db.execute(
        select(FdbEntry.port_id, func.count())
        .where(FdbEntry.device_id == device_id)
        .group_by(FdbEntry.port_id)
    )
    mac_counts = {port_id: n for port_id, n in counted.tuples()}
    neighbors: dict[int, LldpNeighbor] = {}
    for n in (
        await db.execute(select(LldpNeighbor).where(LldpNeighbor.device_id == device_id))
    ).scalars():
        if n.port_id is not None:
            neighbors.setdefault(n.port_id, n)

    result = []
    for port in ports:
        neighbor = neighbors.get(port.id)
        result.append(
            {
                **{
                    c: getattr(port, c)
                    for c in (
                        "id",
                        "if_index",
                        "name",
                        "kind",
                        "description",
                        "admin_up",
                        "oper_up",
                        "speed_mbps",
                        "mac_address",
                        "pvid",
                        "poe",
                        "last_change_at",
                    )
                },
                "untagged_vlans": [v.vid for v in port.vlans if not v.tagged],
                "tagged_vlans": [v.vid for v in port.vlans if v.tagged],
                "is_uplink": port.id in uplinks,
                "neighbor": (neighbor.system_name or neighbor.chassis_id) if neighbor else None,
                "neighbor_device_id": neighbor.remote_device_id if neighbor else None,
                "mac_count": mac_counts.get(port.id, 0),
            }
        )
    return result


async def list_vlans(db: AsyncSession, caller: Caller, device_id: int) -> list[dict[str, Any]]:
    await get_device(db, caller, device_id)
    vlans = (
        (
            await db.execute(
                select(DeviceVlan).where(DeviceVlan.device_id == device_id).order_by(DeviceVlan.vid)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[tuple[int, bool], int] = defaultdict(int)
    for port in (await db.execute(select(Port).where(Port.device_id == device_id))).scalars():
        for v in port.vlans:
            counts[(v.vid, v.tagged)] += 1
    return [
        {
            "vid": v.vid,
            "name": v.name,
            "untagged_ports": counts[(v.vid, False)],
            "tagged_ports": counts[(v.vid, True)],
        }
        for v in vlans
    ]


async def list_fdb(
    db: AsyncSession, caller: Caller, device_id: int, port_id: int | None = None
) -> list[dict[str, Any]]:
    await get_device(db, caller, device_id)
    stmt = (
        select(FdbEntry, Port.name)
        .outerjoin(Port, Port.id == FdbEntry.port_id)
        .where(FdbEntry.device_id == device_id)
        .order_by(Port.if_index, FdbEntry.vid, FdbEntry.mac_address)
    )
    if port_id is not None:
        stmt = stmt.where(FdbEntry.port_id == port_id)
    rows = (await db.execute(stmt)).tuples().all()
    ips = await ip_addresses_for([e.mac_address for e, _ in rows], db)
    return [
        {
            "mac_address": e.mac_address,
            "vid": e.vid,
            "port_id": e.port_id,
            "port_name": name,
            "ip_addresses": sorted(ips.get(e.mac_address, ())),
            "seen_at": e.seen_at,
        }
        for e, name in rows
    ]


async def ip_addresses_for(macs: Sequence[str], db: AsyncSession) -> dict[str, set[str]]:
    """IP addresses of MACs from the ARP tables of all polled routers/switches."""
    result: dict[str, set[str]] = defaultdict(set)
    if not macs:
        return result
    for chunk in (macs[i : i + 500] for i in range(0, len(macs), 500)):
        rows = await db.execute(
            select(ArpEntry.mac_address, ArpEntry.ip_address).where(ArpEntry.mac_address.in_(chunk))
        )
        for mac, ip in rows.tuples():
            result[mac].add(ip)
    return result


async def list_lldp(db: AsyncSession, caller: Caller, device_id: int) -> Sequence[LldpNeighbor]:
    await get_device(db, caller, device_id)
    return (
        (
            await db.execute(
                select(LldpNeighbor)
                .where(LldpNeighbor.device_id == device_id)
                .order_by(LldpNeighbor.local_port_name)
            )
        )
        .scalars()
        .all()
    )


async def poll_states(
    db: AsyncSession, caller: Caller, device_id: int
) -> Sequence[DevicePollState]:
    await get_device(db, caller, device_id)
    return (
        (await db.execute(select(DevicePollState).where(DevicePollState.device_id == device_id)))
        .scalars()
        .all()
    )


async def device_summary(db: AsyncSession, device: Device) -> dict[str, int]:
    ports_up = await db.scalar(
        select(func.count()).select_from(Port).where(Port.device_id == device.id, Port.oper_up)
    )
    ports = await db.scalar(
        select(func.count()).select_from(Port).where(Port.device_id == device.id)
    )
    return {"ports": ports or 0, "ports_up": ports_up or 0}
