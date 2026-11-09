"""Building the writer (CLI/REST) for a device from its credential profile."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers.writers import ConfigWriter
from app.models import CredentialProfile, Device
from app.services import polling
from app.services.context import Runtime
from app.services.credentials import to_device_credentials


async def device_writer(db: AsyncSession, runtime: Runtime, device: Device) -> ConfigWriter:
    profile = (
        await db.get(CredentialProfile, device.credential_profile_id)
        if device.credential_profile_id
        else None
    )
    credentials = to_device_credentials(profile, runtime.box)
    return polling.config_writer(runtime.settings, device, credentials)
