"""Read-only commands on a switch (the old "execute SSH command", made safe).

Only commands from an allowlist are accepted - nothing that changes the configuration.
"""

import asyncio
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DeviceError, ValidationFailedError
from app.drivers.writers import WriteError
from app.models import Permission
from app.services import audit
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.devices import get_device

#: show/display commands, ping and traceroute; an output filter ("| include x") is allowed
ALLOWED = re.compile(
    r"^(show|display|ping|traceroute)\s+[\w\s./:\-,\"'=]+(\|\s*(include|exclude|begin|section|grep)\s+.+)?$",
    re.IGNORECASE,
)
#: the first word decides (see ALLOWED); what must never pass is a second command
FORBIDDEN = re.compile(r"[\n\r;`]")
MAX_OUTPUT = 512 * 1024
TIMEOUT = 150


def validate(command: str) -> str:
    raw = command.strip()
    command = " ".join(raw.split())  # after the check: a newline must not become a space
    if not command or len(command) > 200 or FORBIDDEN.search(raw) or not ALLOWED.match(command):
        raise ValidationFailedError(
            "Only read-only commands are allowed: show …, display …, ping …, traceroute …"
        )
    return command


async def run_command(
    db: AsyncSession, caller: Caller, runtime: Runtime, device_id: int, command: str
) -> str:
    device = await get_device(db, caller, device_id, Permission.CONSOLE)
    command = validate(command)
    await audit.record(
        db,
        caller.actor,
        "console.command",
        f"{device.name}: {command}",
        site_id=device.site_id,
        device_id=device.id,
    )
    await db.commit()  # keep the audit entry even if the switch does not answer
    writer = await device_writer(db, runtime, device)
    try:
        async with asyncio.timeout(TIMEOUT):
            output = await writer.run_show(command)
    except (WriteError, TimeoutError) as exc:
        raise DeviceError(f"{device.name}: {exc or 'timeout'}") from exc
    return output[:MAX_OUTPUT]
