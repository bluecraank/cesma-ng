"""Credential profiles: reusable, encrypted access data for switches."""

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretBox
from app.core.errors import ConflictError, NotFoundError
from app.domain.credentials import (
    SECRET_FIELDS,
    DeviceCredentials,
    LoginCredentials,
    SnmpCredentials,
)
from app.models import CredentialProfile, SnmpVersion
from app.services import audit
from app.services.access import require_superadmin
from app.services.context import Caller

PLAIN_FIELDS = (
    "name",
    "snmp_version",
    "snmp_v3_username",
    "snmp_v3_auth_protocol",
    "snmp_v3_priv_protocol",
    "api_username",
    "ssh_username",
    "verify_tls",
    "api_https",
)


def read_secrets(profile: CredentialProfile, box: SecretBox) -> dict[str, str]:
    if not profile.secrets_encrypted:
        return {}
    data: dict[str, str] = json.loads(box.decrypt(profile.secrets_encrypted))
    return data


def secrets_set(profile: CredentialProfile, box: SecretBox) -> list[str]:
    """Names of the secrets that have a value (for display, values are never returned)."""
    return sorted(k for k, v in read_secrets(profile, box).items() if v)


def to_device_credentials(profile: CredentialProfile | None, box: SecretBox) -> DeviceCredentials:
    if profile is None:
        return DeviceCredentials()
    s = read_secrets(profile, box)
    return DeviceCredentials(
        snmp=SnmpCredentials(
            version=profile.snmp_version.value,
            community=s.get("snmp_community") or "public",
            v3_username=profile.snmp_v3_username,
            v3_auth_protocol=profile.snmp_v3_auth_protocol,
            v3_auth_password=s.get("snmp_v3_auth_password"),
            v3_priv_protocol=profile.snmp_v3_priv_protocol,
            v3_priv_password=s.get("snmp_v3_priv_password"),
        ),
        api=LoginCredentials(username=profile.api_username, password=s.get("api_password")),
        ssh=LoginCredentials(
            username=profile.ssh_username,
            password=s.get("ssh_password"),
            private_key=s.get("ssh_private_key"),
            enable_password=s.get("enable_password"),
        ),
        verify_tls=profile.verify_tls,
        api_https=profile.api_https,
    )


async def list_profiles(db: AsyncSession, caller: Caller) -> Sequence[CredentialProfile]:
    require_superadmin(caller.user)
    return (
        (await db.execute(select(CredentialProfile).order_by(CredentialProfile.name)))
        .scalars()
        .all()
    )


async def get_profile(db: AsyncSession, profile_id: int) -> CredentialProfile:
    profile = await db.get(CredentialProfile, profile_id)
    if profile is None:
        raise NotFoundError("Credential profile not found")
    return profile


async def save_profile(
    db: AsyncSession,
    caller: Caller,
    box: SecretBox,
    values: dict[str, Any],
    profile_id: int | None = None,
) -> CredentialProfile:
    """Create or update a profile.

    ``values`` may hold plain fields and secrets. A secret that is absent stays unchanged,
    an empty string clears it.
    """
    require_superadmin(caller.user)
    profile = (
        await get_profile(db, profile_id)
        if profile_id is not None
        else CredentialProfile(snmp_version=SnmpVersion.V2C, verify_tls=False, api_https=True)
    )
    changed_plain = {}
    for key in PLAIN_FIELDS:
        if key in values and getattr(profile, key, None) != values[key]:
            setattr(profile, key, values[key])
            changed_plain[key] = values[key]

    secrets = read_secrets(profile, box)
    changed_secrets = [k for k in SECRET_FIELDS if k in values and values[k] is not None]
    for key in changed_secrets:
        secrets[key] = values[key]
    profile.secrets_encrypted = box.encrypt(json.dumps(secrets))

    if profile_id is None:
        db.add(profile)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"Credential profile '{values.get('name')}' already exists") from exc

    await audit.record(
        db,
        caller.actor,
        "credentials.create" if profile_id is None else "credentials.update",
        f"Credential profile {profile.name} saved",
        new={**{k: str(v) for k, v in changed_plain.items()}, "secrets_changed": changed_secrets},
    )
    return profile


async def delete_profile(db: AsyncSession, caller: Caller, profile_id: int) -> None:
    require_superadmin(caller.user)
    profile = await get_profile(db, profile_id)
    await db.delete(profile)
    await audit.record(
        db, caller.actor, "credentials.delete", f"Credential profile {profile.name} deleted"
    )
