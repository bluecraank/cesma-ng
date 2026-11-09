"""Rename a switch: its own hostname on the device and its name in cesma-ng."""

import asyncio
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DeviceError, ValidationFailedError
from app.domain.changes import ChangePlan, SetHostname
from app.drivers.writers import WriteError
from app.models import AuditLevel, Permission
from app.services import audit, polling
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.devices import get_device, update_device

APPLY_TIMEOUT = 120
# What all supported switch families accept as hostname: no spaces, no quotes.
HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


async def plan_rename(
    db: AsyncSession, caller: Caller, runtime: Runtime, device_id: int, name: str
) -> ChangePlan:
    device = await get_device(db, caller, device_id, Permission.DEVICES_MANAGE)
    name = name.strip()
    if not HOSTNAME.match(name):
        raise ValidationFailedError(
            "Hostname: letters, digits, '.', '_' and '-' (max. 63, no spaces)"
        )
    operations = [] if name == device.sys_name else [SetHostname(name)]
    plan = ChangePlan(device.id, device.name, list(operations))
    plan.commands = (await device_writer(db, runtime, device)).render(operations)
    return plan


async def apply_rename(
    db: AsyncSession, caller: Caller, runtime: Runtime, device_id: int, name: str
) -> tuple[ChangePlan, list[str]]:
    """Set the hostname on the switch, then use the same name in cesma-ng."""
    plan = await plan_rename(db, caller, runtime, device_id, name)
    device = await get_device(db, caller, device_id, Permission.DEVICES_MANAGE)
    log: list[str] = []
    if not plan.empty:
        writer = await device_writer(db, runtime, device)
        try:
            async with asyncio.timeout(APPLY_TIMEOUT):
                log = await writer.apply(plan.operations)
        except (WriteError, TimeoutError) as exc:
            await audit.record(
                db,
                caller.actor,
                "device.rename_failed",
                f"{device.name}: {exc}",
                level=AuditLevel.ERROR,
                site_id=device.site_id,
                device_id=device.id,
                new={"commands": plan.commands},
            )
            await db.commit()
            raise DeviceError(f"{device.name}: {exc}") from exc
        old_hostname = device.sys_name
        device.sys_name = name.strip()
        await audit.record(
            db,
            caller.actor,
            "device.hostname",
            f"Hostname of {device.name} set to {device.sys_name} on the switch",
            site_id=device.site_id,
            device_id=device.id,
            old={"sys_name": old_hostname},
            new={"sys_name": device.sys_name},
        )
    if device.name != name.strip():
        await update_device(db, caller, device.id, {"name": name.strip()})
    await polling.request_poll(db, device.id)
    return plan, log
