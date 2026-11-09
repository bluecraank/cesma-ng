"""Store what the poller read from a switch.

Ports are updated in place (stable ids for references and history), the MAC/ARP/LLDP
tables are snapshots and replaced as a whole.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domain import switch as dom
from app.drivers.mib import Counters
from app.models import (
    ArpEntry,
    Device,
    DeviceVlan,
    FdbEntry,
    LldpNeighbor,
    Port,
    PortCounterSample,
    PortVlan,
)


@dataclass
class InventoryChanges:
    """What changed compared to the previous poll (input for events/notifications)."""

    rebooted: bool = False
    links_up: list[str] = field(default_factory=list)
    links_down: list[str] = field(default_factory=list)
    speed_changed: list[tuple[str, int | None, int | None]] = field(default_factory=list)
    ports_added: int = 0
    ports_removed: int = 0


async def apply_inventory(db: AsyncSession, device: Device, inv: dom.Inventory) -> InventoryChanges:
    changes = InventoryChanges()
    s = inv.system
    if (
        device.uptime_seconds is not None
        and s.uptime_seconds is not None
        and s.uptime_seconds < device.uptime_seconds
    ):
        changes.rebooted = True
    device.sys_name = s.sys_name or None
    device.model_name = s.model_name
    device.serial_number = s.serial_number
    device.firmware = s.firmware
    device.mac_address = s.base_mac
    device.uptime_seconds = s.uptime_seconds
    device.last_seen_at = utcnow()

    await _apply_ports(db, device, inv.ports, changes)
    await _apply_vlans(db, device, inv.vlans)
    return changes


async def _apply_ports(
    db: AsyncSession, device: Device, ports: Sequence[dom.Port], changes: InventoryChanges
) -> None:
    existing = {
        p.if_index: p
        for p in (await db.execute(select(Port).where(Port.device_id == device.id))).scalars()
    }
    first_poll = not existing
    now = utcnow()
    seen = set()
    for data in ports:
        seen.add(data.if_index)
        port = existing.get(data.if_index)
        if port is None:
            port = Port(device_id=device.id, if_index=data.if_index, vlans=[])
            db.add(port)
            changes.ports_added += 0 if first_poll else 1
        elif port.oper_up != data.oper_up:
            port.last_change_at = now
            (changes.links_up if data.oper_up else changes.links_down).append(data.name)
        elif data.oper_up and port.speed_mbps != data.speed_mbps:
            changes.speed_changed.append((data.name, port.speed_mbps, data.speed_mbps))

        port.name = data.name
        port.kind = data.kind
        port.description = data.description
        port.admin_up = data.admin_up
        port.oper_up = data.oper_up
        port.speed_mbps = data.speed_mbps
        port.mac_address = data.mac_address
        port.pvid = data.pvid
        port.poe = data.poe
        wanted = {(v, False) for v in data.untagged_vlans} | {(v, True) for v in data.tagged_vlans}
        if {(v.vid, v.tagged) for v in port.vlans} != wanted:
            port.vlans = [PortVlan(vid=vid, tagged=tagged) for vid, tagged in sorted(wanted)]

    for if_index, port in existing.items():
        if if_index not in seen:
            await db.delete(port)
            changes.ports_removed += 1
    await db.flush()


async def _apply_vlans(db: AsyncSession, device: Device, vlans: Sequence[dom.Vlan]) -> None:
    existing = {
        v.vid: v
        for v in (
            await db.execute(select(DeviceVlan).where(DeviceVlan.device_id == device.id))
        ).scalars()
    }
    for vlan in vlans:
        row = existing.pop(vlan.vid, None)
        if row is None:
            db.add(DeviceVlan(device_id=device.id, vid=vlan.vid, name=vlan.name))
        else:
            row.name = vlan.name
    for row in existing.values():
        await db.delete(row)
    await db.flush()


async def _port_ids(db: AsyncSession, device_id: int) -> dict[int, int]:
    rows = await db.execute(select(Port.if_index, Port.id).where(Port.device_id == device_id))
    return {if_index: port_id for if_index, port_id in rows.tuples()}


async def apply_fdb(db: AsyncSession, device: Device, entries: Sequence[dom.FdbEntry]) -> None:
    ports = await _port_ids(db, device.id)
    await db.execute(delete(FdbEntry).where(FdbEntry.device_id == device.id))
    now = utcnow()
    db.add_all(
        FdbEntry(
            device_id=device.id,
            port_id=ports.get(e.if_index) if e.if_index is not None else None,
            vid=e.vid,
            mac_address=e.mac_address,
            seen_at=now,
        )
        for e in entries
    )
    await db.flush()


async def apply_arp(db: AsyncSession, device: Device, entries: Sequence[dom.ArpEntry]) -> None:
    await db.execute(delete(ArpEntry).where(ArpEntry.device_id == device.id))
    now = utcnow()
    db.add_all(
        ArpEntry(
            device_id=device.id,
            ip_address=e.ip_address,
            mac_address=e.mac_address,
            if_index=e.if_index,
            seen_at=now,
        )
        for e in entries
    )
    await db.flush()


async def apply_lldp(
    db: AsyncSession, device: Device, neighbors: Sequence[dom.LldpNeighbor]
) -> None:
    ports = await _port_ids(db, device.id)
    await db.execute(delete(LldpNeighbor).where(LldpNeighbor.device_id == device.id))
    now = utcnow()
    for n in neighbors:
        db.add(
            LldpNeighbor(
                device_id=device.id,
                port_id=ports.get(n.local_if_index) if n.local_if_index is not None else None,
                local_port_name=n.local_port_name,
                chassis_id=n.chassis_id[:255],
                remote_port=n.port_id[:255],
                remote_port_description=n.port_description[:255],
                system_name=n.system_name[:255],
                system_description=n.system_description,
                management_address=n.management_address,
                remote_device_id=await _resolve_neighbor(db, device.id, n),
                seen_at=now,
            )
        )
    await db.flush()


async def _resolve_neighbor(db: AsyncSession, own_id: int, n: dom.LldpNeighbor) -> int | None:
    """Find the managed switch behind an LLDP neighbour (topology)."""
    conditions = []
    if len(n.chassis_id) == 17:  # MAC address
        conditions.append(Device.mac_address == n.chassis_id)
        port_owner = select(Port.device_id).where(Port.mac_address == n.chassis_id)
        conditions.append(Device.id.in_(port_owner))
    if n.management_address:
        conditions.append(Device.hostname == n.management_address)
    if n.system_name:
        conditions.append(func.lower(Device.sys_name) == n.system_name.lower())
        conditions.append(func.lower(Device.name) == n.system_name.lower())
    if not conditions:
        return None
    return await db.scalar(select(Device.id).where(Device.id != own_id, or_(*conditions)).limit(1))


async def apply_counters(db: AsyncSession, device: Device, counters: dict[int, Counters]) -> None:
    ports = await _port_ids(db, device.id)
    now = utcnow()
    db.add_all(
        PortCounterSample(
            port_id=port_id,
            sampled_at=now,
            in_octets=c.in_octets,
            out_octets=c.out_octets,
            in_errors=c.in_errors,
            out_errors=c.out_errors,
        )
        for if_index, port_id in ports.items()
        if (c := counters.get(if_index)) is not None
    )
    await db.flush()
