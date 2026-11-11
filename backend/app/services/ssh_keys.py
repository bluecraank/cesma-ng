"""The shared list of SSH public keys that cesma-ng uploads to the switches."""

import base64
import binascii
import hashlib
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    """One shared list: every user sees all keys (public keys are not secret)."""
    stmt = select(SshPublicKey).options(selectinload(SshPublicKey.user))
    return (await db.execute(stmt.order_by(SshPublicKey.description))).scalars().all()


async def add_key(db: AsyncSession, caller: Caller, description: str, key: str) -> SshPublicKey:
    """Every user may add their own keys; they go to the switches with the next upload."""
    normalized = " ".join(key.strip().split())
    entry = SshPublicKey(
        user_id=caller.user.id,
        description=description,
        key=normalized,
        fingerprint=fingerprint(normalized),
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("This key is already stored") from exc
    await db.refresh(entry, ["user"])
    await audit.record(
        db, caller.actor, "ssh_key.add", f"SSH key {description} ({entry.fingerprint}) added"
    )
    return entry


async def delete_key(db: AsyncSession, caller: Caller, key_id: int) -> None:
    entry = await db.get(SshPublicKey, key_id)
    if entry is None:
        raise NotFoundError("Key not found")
    if entry.user_id != caller.user.id:
        require_superadmin(caller.user)
    await db.delete(entry)
    await audit.record(db, caller.actor, "ssh_key.delete", f"SSH key {entry.description} deleted")


def with_own_key(keys: Sequence[str], own_key: str | None) -> list[str]:
    """The key list plus Cesma's own public key, unless it is already in it.

    Uploading replaces the keys on the switch; without its own key Cesma would lock itself
    out of switches that accept no password. Keys are compared by type and data (the
    comment does not matter).
    """
    result = list(keys)
    if own_key and own_key.split()[:2] not in [k.split()[:2] for k in keys]:
        result.append(own_key)
    return result


async def keys_to_push(db: AsyncSession) -> list[SshPublicKey]:
    """Keys that belong on every switch: all keys of active users, plus keys without owner
    (imported from cesma-on-premise). Keys of deactivated users are left out."""
    rows = (
        (
            await db.execute(
                select(SshPublicKey)
                .options(selectinload(SshPublicKey.user))
                .order_by(SshPublicKey.id)
            )
        )
        .scalars()
        .all()
    )
    return [k for k in rows if k.user is None or k.user.is_active]
