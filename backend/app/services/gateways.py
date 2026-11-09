"""SNMP gateways (routers/firewalls) as source of IP <-> MAC, and MAC type definitions."""

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.core.db import utcnow
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain.mac import normalize_prefix
from app.drivers import mib
from app.models import ArpEntry, CredentialProfile, MacType, SnmpGateway
from app.services import audit
from app.services.access import require_superadmin
from app.services.context import Caller
from app.services.credentials import to_device_credentials
from app.services.polling import snmp_client

log = logging.getLogger(__name__)

# --- Gateways --------------------------------------------------------------------------------

GATEWAY_FIELDS = ("name", "hostname", "credential_profile_id", "enabled")


async def list_gateways(db: AsyncSession, caller: Caller) -> Sequence[SnmpGateway]:
    require_superadmin(caller.user)
    return (await db.execute(select(SnmpGateway).order_by(SnmpGateway.name))).scalars().all()


async def save_gateway(
    db: AsyncSession, caller: Caller, values: dict[str, Any], gateway_id: int | None = None
) -> SnmpGateway:
    require_superadmin(caller.user)
    gateway = await _gateway(db, gateway_id) if gateway_id else SnmpGateway(entries=0)
    for key in GATEWAY_FIELDS:
        if key in values:
            setattr(gateway, key, values[key])
    if gateway_id is None:
        db.add(gateway)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A gateway with this hostname already exists") from exc
    await audit.record(
        db, caller.actor, "gateway.save", f"SNMP gateway {gateway.name} ({gateway.hostname}) saved"
    )
    return gateway


async def delete_gateway(db: AsyncSession, caller: Caller, gateway_id: int) -> None:
    require_superadmin(caller.user)
    gateway = await _gateway(db, gateway_id)
    await db.delete(gateway)
    await audit.record(db, caller.actor, "gateway.delete", f"SNMP gateway {gateway.name} deleted")


async def _gateway(db: AsyncSession, gateway_id: int) -> SnmpGateway:
    gateway = await db.get(SnmpGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Gateway not found")
    return gateway


async def poll_gateways(db: AsyncSession, settings: Settings, box: SecretBox) -> None:
    """Read the ARP table of every enabled gateway (replaces its previous entries)."""
    gateways = (await db.execute(select(SnmpGateway).where(SnmpGateway.enabled))).scalars().all()
    for gateway in gateways:
        profile = (
            await db.get(CredentialProfile, gateway.credential_profile_id)
            if gateway.credential_profile_id
            else None
        )
        client = snmp_client(settings, gateway.hostname, to_device_credentials(profile, box))
        try:
            rows = {}
            for base in (mib.IP_NET_TO_PHYSICAL_PHYS, mib.IP_NET_TO_MEDIA_PHYS):
                rows.update(await client.walk(base))
            entries = mib.parse_arp(rows)
        except Exception as exc:  # one broken gateway must not stop the others
            gateway.last_error = str(exc)[:500]
            log.info("Gateway %s failed: %s", gateway.hostname, exc)
            continue
        await db.execute(delete(ArpEntry).where(ArpEntry.gateway_id == gateway.id))
        now = utcnow()
        db.add_all(
            ArpEntry(
                gateway_id=gateway.id,
                ip_address=e.ip_address,
                mac_address=e.mac_address,
                if_index=e.if_index,
                seen_at=now,
            )
            for e in entries
        )
        gateway.entries = len(entries)
        gateway.last_polled_at = now
        gateway.last_error = None
    await db.flush()


# --- MAC types -------------------------------------------------------------------------------

MAC_TYPE_ICONS = ("device", "phone", "printer", "computer", "camera", "wifi", "server", "tv", "iot")


async def list_mac_types(db: AsyncSession) -> Sequence[MacType]:
    return (await db.execute(select(MacType).order_by(MacType.prefix))).scalars().all()


async def save_mac_type(
    db: AsyncSession, caller: Caller, values: dict[str, Any], type_id: int | None = None
) -> MacType:
    require_superadmin(caller.user)
    prefix = normalize_prefix(values.get("prefix", ""))
    if prefix is None:
        raise ValidationFailedError("Prefix must be 1 to 6 bytes in hex, e.g. 00:0B:82")
    if values.get("icon", "device") not in MAC_TYPE_ICONS:
        raise ValidationFailedError(f"Unknown icon; allowed: {', '.join(MAC_TYPE_ICONS)}")
    mac_type = await db.get(MacType, type_id) if type_id else MacType()
    if mac_type is None:
        raise NotFoundError("MAC type not found")
    mac_type.prefix = prefix
    mac_type.name = values["name"]
    mac_type.icon = values.get("icon", "device")
    if type_id is None:
        db.add(mac_type)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"Prefix {prefix} already has a type") from exc
    await audit.record(db, caller.actor, "mac_type.save", f"MAC type {prefix} = {mac_type.name}")
    return mac_type


async def delete_mac_type(db: AsyncSession, caller: Caller, type_id: int) -> None:
    require_superadmin(caller.user)
    mac_type = await db.get(MacType, type_id)
    if mac_type is None:
        raise NotFoundError("MAC type not found")
    await db.delete(mac_type)
    await audit.record(db, caller.actor, "mac_type.delete", f"MAC type {mac_type.prefix} deleted")
