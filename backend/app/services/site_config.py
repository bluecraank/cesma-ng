"""Site VLANs (wanted state), VLAN sync planning and port profiles."""

import ipaddress
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain.changes import (
    ChangePlan,
    CreateVlan,
    DeleteVlan,
    Operation,
    RenameVlan,
    SetPortVlans,
)
from app.models import (
    Device,
    DeviceStatus,
    DeviceVlan,
    Permission,
    Port,
    PortProfile,
    PortVlan,
    SiteVlan,
)
from app.services import audit
from app.services.access import require_permission, require_site_access
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.uplinks import uplink_port_ids

DEFAULT_VLAN = 1

# --- Site VLANs ------------------------------------------------------------------------------

SITE_VLAN_FIELDS = (
    "vid",
    "name",
    "description",
    "ip_range",
    "is_client_vlan",
    "scan_enabled",
    "sync_enabled",
)


async def list_site_vlans(db: AsyncSession, caller: Caller, site_id: int) -> list[dict[str, Any]]:
    """Site VLANs with the number of switches that have them (and with a different name)."""
    require_site_access(caller.user, site_id)
    vlans = (
        (
            await db.execute(
                select(SiteVlan).where(SiteVlan.site_id == site_id).order_by(SiteVlan.vid)
            )
        )
        .scalars()
        .all()
    )
    devices = (await db.execute(select(Device.id).where(Device.site_id == site_id))).scalars().all()
    actual = (
        (await db.execute(select(DeviceVlan).where(DeviceVlan.device_id.in_(devices))))
        .scalars()
        .all()
        if devices
        else []
    )
    present: dict[int, int] = {}
    mismatch: dict[int, int] = {}
    names = {v.vid: v.name for v in vlans}
    for dv in actual:
        present[dv.vid] = present.get(dv.vid, 0) + 1
        if dv.vid in names and dv.name and dv.name != names[dv.vid]:
            mismatch[dv.vid] = mismatch.get(dv.vid, 0) + 1
    return [
        {
            **{f: getattr(v, f) for f in ("id", "site_id", *SITE_VLAN_FIELDS)},
            "devices_with_vlan": present.get(v.vid, 0),
            "devices_name_mismatch": mismatch.get(v.vid, 0),
            "device_count": len(devices),
        }
        for v in vlans
    ]


def _validate_vlan(values: dict[str, Any]) -> None:
    vid = values.get("vid")
    if vid is not None and not 1 <= vid <= 4094:
        raise ValidationFailedError("VLAN id must be between 1 and 4094")
    if values.get("ip_range"):
        try:
            values["ip_range"] = str(ipaddress.ip_network(values["ip_range"], strict=False))
        except ValueError as exc:
            raise ValidationFailedError("IP range must be a network like 10.1.20.0/24") from exc


async def save_site_vlan(
    db: AsyncSession,
    caller: Caller,
    site_id: int,
    values: dict[str, Any],
    vlan_id: int | None = None,
) -> SiteVlan:
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    _validate_vlan(values)
    vlan = await _site_vlan(db, site_id, vlan_id) if vlan_id else SiteVlan(site_id=site_id)
    before = {f: getattr(vlan, f, None) for f in SITE_VLAN_FIELDS}
    for key in SITE_VLAN_FIELDS:
        if key in values:
            setattr(vlan, key, values[key])
    if vlan_id is None:
        db.add(vlan)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"VLAN {values.get('vid')} already exists at this site") from exc
    old, new = audit.changes(before, {f: getattr(vlan, f) for f in SITE_VLAN_FIELDS})
    await audit.record(
        db,
        caller.actor,
        "vlan.save",
        f"VLAN {vlan.vid} {vlan.name} saved",
        site_id=site_id,
        old=old if vlan_id else None,
        new=new,
    )
    return vlan


async def delete_site_vlan(db: AsyncSession, caller: Caller, site_id: int, vlan_id: int) -> None:
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    vlan = await _site_vlan(db, site_id, vlan_id)
    await db.delete(vlan)
    await audit.record(
        db, caller.actor, "vlan.delete", f"VLAN {vlan.vid} {vlan.name} deleted", site_id=site_id
    )


async def _site_vlan(db: AsyncSession, site_id: int, vlan_id: int) -> SiteVlan:
    vlan = await db.get(SiteVlan, vlan_id)
    if vlan is None or vlan.site_id != site_id:
        raise NotFoundError("VLAN not found")
    return vlan


async def import_vlans_from_devices(db: AsyncSession, caller: Caller, site_id: int) -> int:
    """QoL: take over the VLANs that already exist on the site's switches (first setup)."""
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    existing = set(
        (await db.execute(select(SiteVlan.vid).where(SiteVlan.site_id == site_id))).scalars()
    )
    rows = await db.execute(
        select(DeviceVlan.vid, DeviceVlan.name)
        .join(Device, Device.id == DeviceVlan.device_id)
        .where(Device.site_id == site_id)
        .order_by(DeviceVlan.vid)
    )
    added = 0
    for vid, name in rows.tuples():
        if vid not in existing:
            db.add(SiteVlan(site_id=site_id, vid=vid, name=name or f"VLAN{vid}"))
            existing.add(vid)
            added += 1
    await db.flush()
    if added:
        await audit.record(
            db,
            caller.actor,
            "vlan.import",
            f"{added} VLANs imported from switches",
            site_id=site_id,
        )
    return added


# --- VLAN sync -------------------------------------------------------------------------------


async def plan_vlan_sync(
    db: AsyncSession,
    caller: Caller,
    runtime: Runtime,
    site_id: int,
    *,
    device_ids: Sequence[int] | None = None,
    delete_extra: bool = False,
    tag_uplinks: bool = False,
) -> list[ChangePlan]:
    """What VLAN sync would change on each switch of the site (dry run).

    ``tag_uplinks`` also adds the wanted VLANs as tagged to every uplink (trunk/LAG) of the
    switch. It only ever adds VLANs to uplinks, it never removes any.
    """
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    wanted = {
        v.vid: v
        for v in (
            await db.execute(
                select(SiteVlan).where(SiteVlan.site_id == site_id, SiteVlan.sync_enabled)
            )
        ).scalars()
    }
    stmt = select(Device).where(
        Device.site_id == site_id, Device.status != DeviceStatus.UNCONFIRMED
    )
    if device_ids:
        stmt = stmt.where(Device.id.in_(device_ids))
    plans = []
    for device in (await db.execute(stmt.order_by(Device.name))).scalars():
        actual = {
            v.vid: v.name
            for v in (
                await db.execute(select(DeviceVlan).where(DeviceVlan.device_id == device.id))
            ).scalars()
        }
        ops: list[Operation] = []
        if device.last_seen_at is None:
            # The actual VLANs are unknown until the first successful poll: change nothing.
            plan = ChangePlan(
                device.id, device.name, [], warnings=[f"{device.name} has not been polled yet"]
            )
            plans.append(plan)
            continue
        for vid, vlan in sorted(wanted.items()):
            if vid == DEFAULT_VLAN:
                continue  # exists on every switch, cannot be created or renamed reliably
            if vid not in actual:
                ops.append(CreateVlan(vid, vlan.name))
            elif actual[vid] != vlan.name:
                ops.append(RenameVlan(vid, vlan.name))
        warnings = []
        if delete_extra:
            used = set(
                (
                    await db.execute(
                        select(PortVlan.vid).join(Port).where(Port.device_id == device.id)
                    )
                ).scalars()
            )
            for vid in sorted(set(actual) - set(wanted) - {DEFAULT_VLAN}):
                ops.append(DeleteVlan(vid))
                if vid in used:
                    warnings.append(f"VLAN {vid} is still used on ports of {device.name}")
        if tag_uplinks:
            uplink_ops = await _uplink_tagging(db, device, set(wanted) - {DEFAULT_VLAN})
            ops += uplink_ops
            if uplink_ops:
                names = ", ".join(op.port for op in uplink_ops)
                warnings.append(f"Uplinks of {device.name} are changed: {names}")
        if device.status is DeviceStatus.OFFLINE:
            warnings.append(f"{device.name} is offline")
        plan = ChangePlan(device.id, device.name, ops, warnings=warnings)
        plan.commands = (await device_writer(db, runtime, device)).render(ops)
        plans.append(plan)
    return plans


async def _uplink_tagging(db: AsyncSession, device: Device, vids: set[int]) -> list[SetPortVlans]:
    uplinks = await uplink_port_ids(db, device.id)
    ports = (
        (await db.execute(select(Port).where(Port.id.in_(uplinks)).order_by(Port.if_index)))
        .scalars()
        .all()
    )
    ops: list[SetPortVlans] = []
    for port in ports:
        untagged = next((v.vid for v in port.vlans if not v.tagged), None)
        tagged = frozenset(v.vid for v in port.vlans if v.tagged)
        missing = vids - tagged - ({untagged} if untagged else set())
        if missing:
            ops.append(SetPortVlans(port.name, untagged, tagged | missing, untagged, tagged))
    return ops


# --- Port profiles ---------------------------------------------------------------------------


async def list_profiles(db: AsyncSession, caller: Caller, site_id: int) -> Sequence[PortProfile]:
    require_site_access(caller.user, site_id)
    return (
        (
            await db.execute(
                select(PortProfile).where(PortProfile.site_id == site_id).order_by(PortProfile.name)
            )
        )
        .scalars()
        .all()
    )


async def save_profile(
    db: AsyncSession,
    caller: Caller,
    site_id: int,
    values: dict[str, Any],
    profile_id: int | None = None,
) -> PortProfile:
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    profile = await db.get(PortProfile, profile_id) if profile_id else PortProfile(site_id=site_id)
    if profile is None or profile.site_id != site_id:
        raise NotFoundError("Port profile not found")
    profile.name = values["name"]
    profile.untagged_vid = values.get("untagged_vid")
    profile.tagged_vids = sorted(set(values.get("tagged_vids") or []) - {profile.untagged_vid})
    profile.description = values.get("description") or None
    if profile_id is None:
        db.add(profile)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"Port profile '{values['name']}' already exists") from exc
    await audit.record(
        db, caller.actor, "port_profile.save", f"Port profile {profile.name} saved", site_id=site_id
    )
    return profile


async def delete_profile(db: AsyncSession, caller: Caller, site_id: int, profile_id: int) -> None:
    require_permission(caller.user, site_id, Permission.VLANS_MANAGE)
    profile = await db.get(PortProfile, profile_id)
    if profile is None or profile.site_id != site_id:
        raise NotFoundError("Port profile not found")
    await db.delete(profile)
    await audit.record(
        db,
        caller.actor,
        "port_profile.delete",
        f"Port profile {profile.name} deleted",
        site_id=site_id,
    )
