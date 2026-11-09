"""SSH public keys that cesma-ng uploads to the switches."""

import base64
import binascii
import hashlib
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import SshPublicKey
from app.services import audit
from app.services.access import require_superadmin
from app.services.context import Caller

KEY_TYPES = (
    "ssh-rsa",
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
)


def fingerprint(key: str) -> str:
    """OpenSSH style SHA256 fingerprint; validates the key format on the way."""
    parts = key.strip().split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise ValidationFailedError("Not an OpenSSH public key (ssh-rsa, ssh-ed25519, ecdsa-...)")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except binascii.Error as exc:
        raise ValidationFailedError("The key data is not valid base64") from exc
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


async def list_keys(db: AsyncSession, caller: Caller) -> Sequence[SshPublicKey]:
    require_superadmin(caller.user)
    return (
        (await db.execute(select(SshPublicKey).order_by(SshPublicKey.description))).scalars().all()
    )


async def add_key(db: AsyncSession, caller: Caller, description: str, key: str) -> SshPublicKey:
    require_superadmin(caller.user)
    normalized = " ".join(key.strip().split())
    entry = SshPublicKey(
        description=description, key=normalized, fingerprint=fingerprint(normalized)
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("This key is already stored") from exc
    await audit.record(
        db, caller.actor, "ssh_key.add", f"SSH key {description} ({entry.fingerprint}) added"
    )
    return entry


async def delete_key(db: AsyncSession, caller: Caller, key_id: int) -> None:
    require_superadmin(caller.user)
    entry = await db.get(SshPublicKey, key_id)
    if entry is None:
        raise NotFoundError("Key not found")
    await db.delete(entry)
    await audit.record(db, caller.actor, "ssh_key.delete", f"SSH key {entry.description} deleted")
