"""Device inventory (CRUD). Polling and configuration live in their own services."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import CredentialProfile, Device, DeviceStatus, Permission, Site
from app.services import audit
from app.services.access import require_permission, require_site_access, visible_site_ids
from app.services.context import Caller
from app.services.discovery import remember_ignored
from app.services.org import room_site_id

EDITABLE_FIELDS = (
    "name",
    "hostname",
    "model",
    "site_id",
    "room_id",
    "credential_profile_id",
    "location_note",
)


async def list_devices(
    db: AsyncSession,
    caller: Caller,
    *,
    site_id: int | None = None,
    status: DeviceStatus | None = None,
    search: str | None = None,
) -> Sequence[Device]:
    stmt = select(Device).order_by(Device.name)
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Device.site_id.in_(ids))
    if site_id is not None:
        stmt = stmt.where(Device.site_id == site_id)
    if status is not None:
        stmt = stmt.where(Device.status == status)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Device.name.ilike(pattern),
                Device.hostname.ilike(pattern),
                Device.ip_address.ilike(pattern),
                Device.dns_name.ilike(pattern),
                Device.model_name.ilike(pattern),
                Device.serial_number.ilike(pattern),
            )
        )
    return (await db.execute(stmt)).scalars().all()


async def get_device(
    db: AsyncSession, caller: Caller, device_id: int, permission: Permission | None = None
) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise NotFoundError("Device not found")
    if permission is None:
        require_site_access(caller.user, device.site_id)
    else:
        require_permission(caller.user, device.site_id, permission)
    return device


async def create_device(db: AsyncSession, caller: Caller, values: dict[str, Any]) -> Device:
    require_permission(caller.user, values["site_id"], Permission.DEVICES_MANAGE)
    device = Device(status=DeviceStatus.UNKNOWN, location_note="")
    _apply(device, values)
    await _validate_references(db, device)
    db.add(device)
    await _flush_unique(db)
    await audit.record(
        db,
        caller.actor,
        "device.create",
        f"Device {device.name} ({device.hostname}) created",
        site_id=device.site_id,
        device_id=device.id,
        new=_snapshot(device),
    )
    return device


async def update_device(
    db: AsyncSession, caller: Caller, device_id: int, values: dict[str, Any]
) -> Device:
    device = await get_device(db, caller, device_id, Permission.DEVICES_MANAGE)
    if "site_id" in values:
        require_permission(caller.user, values["site_id"], Permission.DEVICES_MANAGE)
    before = _snapshot(device)
    _apply(device, values)
    if "hostname" in values and values["hostname"] != before.get("hostname"):
        device.address_checked_at = None  # resolve IP and DNS name again on the next poll
    if device.status is DeviceStatus.UNCONFIRMED and values:
        device.status = DeviceStatus.UNKNOWN  # an admin has reviewed the discovered device
    await _validate_references(db, device)
    await _flush_unique(db)
    old, new = audit.changes(before, _snapshot(device))
    if new:
        await audit.record(
            db,
            caller.actor,
            "device.update",
            f"Device {device.name} changed",
            site_id=device.site_id,
            device_id=device.id,
            old=old,
            new=new,
        )
    return device


async def delete_device(db: AsyncSession, caller: Caller, device_id: int) -> None:
    device = await get_device(db, caller, device_id, Permission.DEVICES_MANAGE)
    if device.status is DeviceStatus.UNCONFIRMED:
        await remember_ignored(db, device.hostname)
    await db.delete(device)
    await audit.record(
        db,
        caller.actor,
        "device.delete",
        f"Device {device.name} deleted",
        site_id=device.site_id,
        old=_snapshot(device),
    )


def _apply(device: Device, values: dict[str, Any]) -> None:
    for key in EDITABLE_FIELDS:
        if key in values:
            setattr(device, key, values[key])


async def _validate_references(db: AsyncSession, device: Device) -> None:
    if await db.get(Site, device.site_id) is None:
        raise ValidationFailedError("Unknown site")
    if device.room_id is not None and await room_site_id(db, device.room_id) != device.site_id:
        raise ValidationFailedError("Room does not belong to the selected site")
    if (
        device.credential_profile_id is not None
        and await db.get(CredentialProfile, device.credential_profile_id) is None
    ):
        raise ValidationFailedError("Unknown credential profile")


async def _flush_unique(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A device with this name or hostname already exists") from exc


def _snapshot(device: Device) -> dict[str, Any]:
    def plain(value: Any) -> Any:
        return value.value if isinstance(value, StrEnum) else value

    return {key: plain(getattr(device, key)) for key in EDITABLE_FIELDS}
