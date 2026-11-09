"""Changing ports: description, enabled state and VLANs - with preview before applying."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DeviceError, NotFoundError, ValidationFailedError
from app.domain.changes import (
    ChangePlan,
    Operation,
    SetPortDescription,
    SetPortEnabled,
    SetPortVlans,
)
from app.drivers.writers import WriteError
from app.models import AuditLevel, Device, DeviceVlan, Port, PortVlan, SiteRole
from app.services import audit, polling
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.devices import get_device
from app.services.uplinks import uplink_port_ids

APPLY_TIMEOUT = 180


@dataclass(frozen=True)
class PortChange:
    """Wanted state; ``None`` means "leave unchanged"."""

    description: str | None = None
    enabled: bool | None = None
    untagged: int | None = None
    tagged: frozenset[int] | None = None
    #: set untagged to "none" explicitly (``untagged=None`` alone means unchanged)
    clear_untagged: bool = False

    @property
    def touches_vlans(self) -> bool:
        return self.untagged is not None or self.tagged is not None or self.clear_untagged


@dataclass
class PortPlan:
    plan: ChangePlan
    ports: list[Port] = field(default_factory=list)


def _operations(port: Port, change: PortChange) -> list[Operation]:
    ops: list[Operation] = []
    if change.description is not None and change.description != port.description:
        ops.append(SetPortDescription(port.name, change.description.strip()))
    if change.enabled is not None and change.enabled != port.admin_up:
        ops.append(SetPortEnabled(port.name, change.enabled))
    if change.touches_vlans:
        before_untagged = next((v.vid for v in port.vlans if not v.tagged), None)
        before_tagged = frozenset(v.vid for v in port.vlans if v.tagged)
        untagged = None if change.clear_untagged else (change.untagged or before_untagged)
        tagged = change.tagged if change.tagged is not None else before_tagged
        tagged = frozenset(tagged - {untagged} if untagged else tagged)
        if (untagged, tagged) != (before_untagged, before_tagged):
            ops.append(SetPortVlans(port.name, untagged, tagged, before_untagged, before_tagged))
    return ops


async def plan_port_change(
    db: AsyncSession,
    caller: Caller,
    runtime: Runtime,
    device_id: int,
    port_ids: Sequence[int],
    change: PortChange,
) -> PortPlan:
    device = await get_device(db, caller, device_id, SiteRole.ADMIN)
    if not port_ids:
        raise ValidationFailedError("No port selected")
    ports = (
        (
            await db.execute(
                select(Port)
                .where(Port.device_id == device_id, Port.id.in_(port_ids))
                .order_by(Port.if_index)
            )
        )
        .scalars()
        .all()
    )
    if len(ports) != len(set(port_ids)):
        raise NotFoundError("Port not found on this device")

    operations: list[Operation] = []
    for port in ports:
        operations += _operations(port, change)

    plan = ChangePlan(device.id, device.name, operations)
    plan.warnings = await _warnings(db, device, ports, change)
    plan.commands = (await device_writer(db, runtime, device)).render(operations)
    return PortPlan(plan, list(ports))


async def _warnings(
    db: AsyncSession, device: Device, ports: Sequence[Port], change: PortChange
) -> list[str]:
    warnings = []
    uplinks = await uplink_port_ids(db, device.id) & {p.id for p in ports}
    if uplinks:
        names = ", ".join(p.name for p in ports if p.id in uplinks)
        if change.enabled is False:
            warnings.append(f"DANGER: disabling uplink {names} can cut off this switch")
        else:
            warnings.append(f"Uplink port(s) affected: {names}")
    if change.touches_vlans:
        existing = set(
            (
                await db.execute(select(DeviceVlan.vid).where(DeviceVlan.device_id == device.id))
            ).scalars()
        )
        wanted = set(change.tagged or ()) | ({change.untagged} if change.untagged else set())
        if missing := sorted(wanted - existing):
            warnings.append(f"VLAN(s) {', '.join(map(str, missing))} do not exist on {device.name}")
    return warnings


async def apply_port_change(
    db: AsyncSession,
    caller: Caller,
    runtime: Runtime,
    device_id: int,
    port_ids: Sequence[int],
    change: PortChange,
) -> tuple[ChangePlan, list[str]]:
    result = await plan_port_change(db, caller, runtime, device_id, port_ids, change)
    plan = result.plan
    if plan.empty:
        return plan, []
    device = await get_device(db, caller, device_id, SiteRole.ADMIN)
    writer = await device_writer(db, runtime, device)
    before = {p.name: _port_state(p) for p in result.ports}
    try:
        async with asyncio.timeout(APPLY_TIMEOUT):
            log = await writer.apply(plan.operations)
    except (WriteError, TimeoutError) as exc:
        await audit.record(
            db,
            caller.actor,
            "port.update_failed",
            f"{device.name}: {exc}",
            level=AuditLevel.ERROR,
            site_id=device.site_id,
            device_id=device.id,
            new={"commands": plan.commands},
        )
        await db.commit()
        raise DeviceError(f"{device.name}: {exc}") from exc

    _update_ports(result.ports, plan.operations)
    after = {p.name: _port_state(p) for p in result.ports}
    old, new = audit.changes(before, after)
    await audit.record(
        db,
        caller.actor,
        "port.update",
        f"{device.name}: {', '.join(p.name for p in result.ports)} changed",
        site_id=device.site_id,
        device_id=device.id,
        old=old,
        new=new,
    )
    await polling.request_poll(db, device.id)
    return plan, log


def _port_state(port: Port) -> dict[str, object]:
    return {
        "description": port.description,
        "enabled": port.admin_up,
        "untagged": next((v.vid for v in port.vlans if not v.tagged), None),
        "tagged": sorted(v.vid for v in port.vlans if v.tagged),
    }


def _update_ports(ports: Sequence[Port], operations: Sequence[Operation]) -> None:
    """Reflect the applied change right away (the next poll confirms it)."""
    by_name = {p.name: p for p in ports}
    for op in operations:
        port = by_name.get(op.port) if hasattr(op, "port") else None
        match op:
            case SetPortDescription(_, description) if port:
                port.description = description
            case SetPortEnabled(_, enabled) if port:
                port.admin_up = enabled
            case SetPortVlans(untagged=untagged, tagged=tagged) if port:
                port.vlans = [
                    *([PortVlan(vid=untagged, tagged=False)] if untagged else []),
                    *(PortVlan(vid=v, tagged=True) for v in sorted(tagged)),
                ]
