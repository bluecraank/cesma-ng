"""Setup problems of devices that an administrator should fix (missing credentials etc.)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretBox
from app.drivers.registry import WRITERS
from app.drivers.writers import CliWriter
from app.models import (
    CredentialProfile,
    Device,
    DevicePollState,
    DeviceStatus,
    PollTask,
    SnmpVersion,
)
from app.services.access import require_site_access
from app.services.context import Caller
from app.services.credentials import read_secrets


@dataclass(frozen=True)
class Hint:
    device_id: int
    #: no_profile | snmp_default | snmp_v3_incomplete | no_ssh_login | no_api_login |
    #: unreachable | never_polled
    code: str
    #: "error" blocks polling, "warning" blocks changes/backups
    level: str
    detail: str = ""


async def site_hints(db: AsyncSession, caller: Caller, box: SecretBox, site_id: int) -> list[Hint]:
    require_site_access(caller.user, site_id)
    devices = (
        (
            await db.execute(
                select(Device).where(
                    Device.site_id == site_id, Device.status != DeviceStatus.UNCONFIRMED
                )
            )
        )
        .scalars()
        .all()
    )
    profiles = {p.id: p for p in (await db.execute(select(CredentialProfile))).scalars()}
    errors = {
        s.device_id: s.last_error
        for s in (
            await db.execute(
                select(DevicePollState).where(
                    DevicePollState.task == PollTask.INVENTORY,
                    DevicePollState.device_id.in_([d.id for d in devices]),
                )
            )
        ).scalars()
    }
    hints: list[Hint] = []
    for device in devices:
        profile = profiles.get(device.credential_profile_id or -1)
        hints += _credential_hints(device, profile, box)
        if device.status is DeviceStatus.OFFLINE:
            hints.append(Hint(device.id, "unreachable", "error", errors.get(device.id) or ""))
        elif device.last_seen_at is None and errors.get(device.id):
            hints.append(Hint(device.id, "never_polled", "error", errors[device.id] or ""))
    return hints


def _credential_hints(
    device: Device, profile: CredentialProfile | None, box: SecretBox
) -> list[Hint]:
    if profile is None:
        return [Hint(device.id, "no_profile", "error")]
    secrets = read_secrets(profile, box)
    hints: list[Hint] = []
    if profile.snmp_version is SnmpVersion.V3:
        if not profile.snmp_v3_username or not secrets.get("snmp_v3_auth_password"):
            hints.append(Hint(device.id, "snmp_v3_incomplete", "error", profile.name))
    elif not secrets.get("snmp_community"):
        hints.append(Hint(device.id, "snmp_default", "warning", profile.name))
    # Changes and backups: Dell via SSH CLI, HP/Aruba via REST API.
    if issubclass(WRITERS[device.model], CliWriter):
        if not profile.ssh_username or not secrets.get("ssh_password"):
            hints.append(Hint(device.id, "no_ssh_login", "warning", profile.name))
    elif not profile.api_username or not secrets.get("api_password"):
        hints.append(Hint(device.id, "no_api_login", "warning", profile.name))
    return hints
