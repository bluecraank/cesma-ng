"""Changing ports: description, enabled state and VLANs - with preview before applying."""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import DeviceError, NotFoundError, ValidationFailedError
from app.domain.changes import (
    ChangePlan,
    Operation,
    SetPortDescription,
    SetPortEnabled,
    SetPortVlans,
)
from app.drivers.writers import WriteError
from app.models import (
    AuditLevel,
    Device,
    DeviceVlan,
    Permission,
    Port,
    PortEvent,
    PortEventKind,
    PortProfile,
)
from app.services import audit, polling
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.devices import get_device
from app.services.uplinks import uplink_port_ids

log = logging.getLogger(__name__)

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
    #: tag / untag single VLANs and keep the others (editing several ports at once)
    add_tagged: frozenset[int] = frozenset()
    remove_tagged: frozenset[int] = frozenset()
    #: the change applies this port profile
    profile_id: int | None = None
    #: bind the ports to the profile permanently (requires ``profile_id``)
    bind: bool = False

    @property
    def touches_vlans(self) -> bool:
        return (
            self.untagged is not None
            or self.tagged is not None
            or self.clear_untagged
            or bool(self.add_tagged or self.remove_tagged)
        )


def profile_change(
    profile: PortProfile, *, enabled: bool | None = None, bind: bool = False
) -> PortChange:
    """The port state a profile stands for."""
    return PortChange(
        description=profile.description,
        enabled=enabled,
        untagged=profile.untagged_vid,
        tagged=frozenset(profile.tagged_vids),
        clear_untagged=profile.untagged_vid is None,
        profile_id=profile.id,
        bind=bind,
    )


def check_bound(ports: Sequence[Port], change: PortChange, profiles: dict[int, str]) -> None:
    """Ports bound to a profile are changed only through a profile.

    Allowed: applying the bound profile again, binding to another profile, and switching the
    port on or off (not part of a profile).
    """
    if change.bind or (change.description is None and not change.touches_vlans):
        return
    locked = [p for p in ports if p.port_profile_id and p.port_profile_id != change.profile_id]
    if locked:
        names = ", ".join(f"{p.name} ({profiles.get(p.port_profile_id or 0, '?')})" for p in locked)
        raise ValidationFailedError(
            f"Port(s) bound to a port profile, change the profile or unbind them first: {names}"
        )


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
        tagged = (tagged | change.add_tagged) - change.remove_tagged
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
    permission: Permission = Permission.PORTS_EDIT,
) -> PortPlan:
    device = await get_device(db, caller, device_id, permission)
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
    if change.bind and change.profile_id is None:
        raise ValidationFailedError("Binding needs a port profile")
    check_bound(ports, change, await _profile_names(db, device.site_id))

    operations: list[Operation] = []
    for port in ports:
        operations += _operations(port, change)

    plan = ChangePlan(device.id, device.name, operations)
    plan.warnings = await _warnings(db, device, ports, change)
    plan.commands = (await device_writer(db, runtime, device)).render(operations)
    return PortPlan(plan, list(ports))


async def _profile_names(db: AsyncSession, site_id: int) -> dict[int, str]:
    rows = await db.execute(
        select(PortProfile.id, PortProfile.name).where(PortProfile.site_id == site_id)
    )
    return {pid: name for pid, name in rows}


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
        wanted = set(change.tagged or ()) | set(change.add_tagged)
        wanted |= {change.untagged} if change.untagged else set()
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
    permission: Permission = Permission.PORTS_EDIT,
) -> tuple[ChangePlan, list[str]]:
    result = await plan_port_change(db, caller, runtime, device_id, port_ids, change, permission)
    plan = result.plan
    device = await get_device(db, caller, device_id, permission)
    if plan.empty:
        await _bind(db, caller, device, result.ports, change)
        return plan, []
    writer = await device_writer(db, runtime, device)
    before = {p.name: _port_state(p) for p in result.ports}
    try:
        async with asyncio.timeout(APPLY_TIMEOUT):
            log = await writer.apply(plan.operations)
    except Exception as exc:  # whatever went wrong talking to the switch: report it, audited
        reason = describe_failure(exc, APPLY_TIMEOUT)
        await audit.record(
            db,
            caller.actor,
            "port.update_failed",
            f"{device.name}: {reason}",
            level=AuditLevel.ERROR,
            site_id=device.site_id,
            device_id=device.id,
            new={"commands": plan.commands},
        )
        await db.commit()
        raise DeviceError(f"{device.name}: {reason}") from exc

    await _reflect(db, result.ports, plan.operations)
    after = {p.name: _port_state(p) for p in result.ports}
    for port in result.ports:
        port_old, port_new = audit.changes(before[port.name], after[port.name])
        if port_new:
            db.add(
                PortEvent(
                    port_id=port.id,
                    kind=PortEventKind.CONFIGURED,
                    actor=caller.user.username,
                    detail={"old": port_old, "new": port_new},
                )
            )
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
    await _bind(db, caller, device, result.ports, change)
    await polling.request_poll(db, device.id)
    return plan, log


async def _bind(
    db: AsyncSession, caller: Caller, device: Device, ports: Sequence[Port], change: PortChange
) -> None:
    """After the profile was applied: bind the ports to it (if requested)."""
    if not change.bind or change.profile_id is None:
        return
    rebound = [p for p in ports if p.port_profile_id != change.profile_id]
    if not rebound:
        return
    for port in rebound:
        port.port_profile_id = change.profile_id
    profile = await db.get(PortProfile, change.profile_id)
    await audit.record(
        db,
        caller.actor,
        "port.bind",
        f"{device.name}: {', '.join(p.name for p in rebound)} bound to port profile "
        f"{profile.name if profile else change.profile_id}",
        site_id=device.site_id,
        device_id=device.id,
        new={"port_profile_id": change.profile_id, "ports": [p.name for p in rebound]},
    )


async def unbind_ports(
    db: AsyncSession, caller: Caller, device_id: int, port_ids: Sequence[int]
) -> int:
    """Release ports from their profile; the configuration on the switch stays as it is."""
    device = await get_device(db, caller, device_id, Permission.PORTS_EDIT)
    ports = (
        (
            await db.execute(
                select(Port).where(
                    Port.device_id == device_id,
                    Port.id.in_(port_ids),
                    Port.port_profile_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for port in ports:
        port.port_profile_id = None
    if ports:
        await audit.record(
            db,
            caller.actor,
            "port.unbind",
            f"{device.name}: {', '.join(p.name for p in ports)} released from port profile",
            site_id=device.site_id,
            device_id=device.id,
        )
    return len(ports)


def describe_failure(exc: BaseException, timeout: float) -> str:
    """A message for the user; some errors (timeouts) have no text of their own."""
    if isinstance(exc, TimeoutError) and not str(exc):
        return f"no answer from the switch within {timeout:.0f} s"
    if isinstance(exc, WriteError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def _port_state(port: Port) -> dict[str, object]:
    return {
        "description": port.description,
        "enabled": port.admin_up,
        "untagged": next((v.vid for v in port.vlans if not v.tagged), None),
        "tagged": sorted(v.vid for v in port.vlans if v.tagged),
    }


#: what ``_port_state`` reads
_STATE_FIELDS = ["description", "admin_up", "vlans"]


async def _reflect(
    db: AsyncSession, ports: Sequence[Port], operations: Sequence[Operation]
) -> None:
    """Show the applied change right away, the next poll confirms it.

    The switch already has the change. While it was written (AOS-CX saves slowly) the worker
    may have polled the switch and stored the new state itself: so start from the stored
    state, and if it still collides, keep what the worker stored instead of failing.
    """
    try:
        async with db.begin_nested():
            for port in ports:
                await db.refresh(port, _STATE_FIELDS)
            _update_ports(ports, operations)
    except (IntegrityError, StaleDataError) as exc:
        log.warning("Ports changed in parallel, keeping the polled state: %s", exc)
        for port in ports:
            await db.refresh(port, _STATE_FIELDS)


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
                port.set_vlans(
                    {**{v: True for v in tagged}, **({untagged: False} if untagged else {})}
                )
