"""Import the data of cesma-on-premise (Laravel/MySQL) into cesma-ng.

    pip install pymysql
    cesma import-legacy --mysql "mysql://user:pass@host/cesma" --app-key "base64:..." \
        --api-user admin [--with-backups]

Takes over sites, buildings, rooms, devices (with their passwords as credential profiles),
site VLANs, MAC types, SNMP gateways, SSH public keys and optionally backups. Users and
their roles are not imported: users log in once and a super admin assigns the sites.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretBox
from app.domain.mac import normalize_prefix
from app.models import (
    Backup,
    BackupStatus,
    Building,
    CredentialProfile,
    Device,
    DeviceModel,
    DeviceStatus,
    MacType,
    Room,
    Site,
    SiteVlan,
    SnmpGateway,
    SnmpVersion,
    SshPublicKey,
)
from app.services import audit
from app.services.audit import Actor
from app.services.ssh_keys import fingerprint

log = logging.getLogger(__name__)

MODEL_MAP = {
    "aruba-os": DeviceModel.ARUBA_OS_SWITCH,
    "aruba-cx": DeviceModel.ARUBA_CX,
    "dell-emc": DeviceModel.DELL_OS10,
    "dell-emc-powerswitch": DeviceModel.DELL_N1500,
}

ICON_KEYWORDS = (
    ("printer", "printer"),
    ("drucker", "printer"),
    ("phone", "phone"),
    ("telefon", "phone"),
    ("voip", "phone"),
    ("camera", "camera"),
    ("kamera", "camera"),
    ("cctv", "camera"),
    ("access", "wifi"),
    ("wlan", "wifi"),
    ("wifi", "wifi"),
    ("server", "server"),
    ("tv", "tv"),
    ("monitor", "tv"),
    ("pc", "computer"),
    ("computer", "computer"),
    ("laptop", "computer"),
    ("notebook", "computer"),
    ("iot", "iot"),
    ("sensor", "iot"),
)


# --- Laravel encryption ----------------------------------------------------------------------


class LaravelDecrypter:
    """Decrypts values written by Laravel's ``Crypt::encrypt`` (AES-256-CBC + HMAC-SHA256)."""

    def __init__(self, app_key: str) -> None:
        raw = app_key.removeprefix("base64:")
        self.key = base64.b64decode(raw) if app_key.startswith("base64:") else raw.encode()
        if len(self.key) != 32:
            raise ValueError("APP_KEY must be a 32 byte key (AES-256-CBC)")

    def decrypt(self, payload: str) -> str:
        data = json.loads(base64.b64decode(payload))
        iv, value = data["iv"], data["value"]
        expected = hmac.new(self.key, (iv + value).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, data.get("mac", "")):
            raise ValueError("MAC mismatch: wrong APP_KEY or modified value")
        decryptor = Cipher(algorithms.AES(self.key), modes.CBC(base64.b64decode(iv))).decryptor()
        padded = decryptor.update(base64.b64decode(value)) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        plain = (unpadder.update(padded) + unpadder.finalize()).decode()
        return php_unserialize_string(plain)


def php_unserialize_string(value: str) -> str:
    """``Crypt::encrypt`` serializes: 's:6:"public";' -> 'public' (other values unchanged)."""
    match = re.fullmatch(r's:(\d+):"(.*)";', value, re.DOTALL)
    if match and len(match.group(2).encode()) == int(match.group(1)):
        return match.group(2)
    return value


def icon_for(type_name: str) -> str:
    lowered = type_name.lower()
    return next((icon for keyword, icon in ICON_KEYWORDS if keyword in lowered), "device")


# --- Import ----------------------------------------------------------------------------------


@dataclass
class ImportResult:
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def add(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n


Rows = list[dict[str, Any]]


async def import_legacy(
    db: AsyncSession,
    tables: dict[str, Rows],
    decrypter: LaravelDecrypter,
    box: SecretBox,
    *,
    api_user: str = "admin",
    with_backups: bool = False,
) -> ImportResult:
    """``tables`` maps old table names to their rows (read from MySQL by the CLI)."""
    result = ImportResult()
    sites = await _import_org(db, tables, result)
    await _import_devices(db, tables, decrypter, box, sites, api_user, result, with_backups)
    await _import_reference(db, tables, decrypter, sites, result)
    await audit.record(
        db,
        Actor.system(),
        "legacy.import",
        "Import from cesma-on-premise: "
        + ", ".join(f"{k} {v}" for k, v in sorted(result.counts.items())),
    )
    return result


async def _import_org(
    db: AsyncSession, tables: dict[str, Rows], result: ImportResult
) -> dict[str, dict[int, int]]:
    """Returns old id -> new id per table ('sites', 'buildings', 'rooms')."""
    ids: dict[str, dict[int, int]] = {"sites": {}, "buildings": {}, "rooms": {}}
    existing = {s.name: s for s in (await db.execute(select(Site))).scalars()}
    for row in tables.get("sites", []):
        site = existing.get(row["name"]) or Site(name=row["name"], buildings=[])
        db.add(site)
        await db.flush()
        ids["sites"][row["id"]] = site.id
        result.add("sites")
    for row in tables.get("buildings", []):
        site_id = ids["sites"].get(row["site_id"])
        if site_id is None:
            continue
        building = await db.scalar(
            select(Building).where(Building.site_id == site_id, Building.name == row["name"])
        ) or Building(site_id=site_id, name=row["name"], rooms=[])
        db.add(building)
        await db.flush()
        ids["buildings"][row["id"]] = building.id
        result.add("buildings")
    for row in tables.get("rooms", []):
        building_id = ids["buildings"].get(row["building_id"])
        if building_id is None:
            continue
        room = await db.scalar(
            select(Room).where(Room.building_id == building_id, Room.name == row["name"])
        ) or Room(building_id=building_id, name=row["name"])
        db.add(room)
        await db.flush()
        ids["rooms"][row["id"]] = room.id
        result.add("rooms")
    return ids


async def _import_devices(
    db: AsyncSession,
    tables: dict[str, Rows],
    decrypter: LaravelDecrypter,
    box: SecretBox,
    ids: dict[str, dict[int, int]],
    api_user: str,
    result: ImportResult,
    with_backups: bool,
) -> None:
    profiles: dict[tuple[str, str], CredentialProfile] = {}
    known = set((await db.execute(select(Device.hostname))).scalars())
    device_ids: dict[int, int] = {}
    for row in tables.get("devices", []):
        model = MODEL_MAP.get(row.get("type", ""))
        site_id = ids["sites"].get(row["site_id"])
        if model is None or site_id is None:
            result.warnings.append(
                f"Device {row.get('name')}: unknown type {row.get('type')!r}, skipped"
            )
            continue
        if row["hostname"] in known:
            result.warnings.append(f"Device {row['name']}: already exists, skipped")
            continue
        try:
            password = decrypter.decrypt(row["password"])
        except (ValueError, KeyError) as exc:
            result.warnings.append(f"Device {row['name']}: password not readable ({exc})")
            password = ""
        username = row.get("username") or api_user
        key = (username, password)
        if key not in profiles:
            profile = CredentialProfile(
                name=f"Import {len(profiles) + 1} ({username})",
                snmp_version=SnmpVersion.V2C,
                api_username=username,
                ssh_username=username,
                verify_tls=False,
                api_https=True,
                secrets_encrypted=box.encrypt(
                    json.dumps(
                        {
                            "snmp_community": "public",
                            "api_password": password,
                            "ssh_password": password,
                        }
                    )
                ),
            )
            db.add(profile)
            await db.flush()
            profiles[key] = profile
            result.add("credential profiles")
        device = Device(
            site_id=site_id,
            room_id=ids["rooms"].get(row.get("room_id") or 0),
            credential_profile_id=profiles[key].id,
            name=row["name"],
            hostname=row["hostname"],
            model=model,
            status=DeviceStatus.UNKNOWN,
            location_note=str(row.get("location_description") or ""),
        )
        db.add(device)
        await db.flush()
        device_ids[row["id"]] = device.id
        known.add(device.hostname)
        result.add("devices")

    if with_backups:
        for row in tables.get("device_backups", []):
            device_id = device_ids.get(row["device_id"])
            if device_id is None or not row.get("data"):
                continue
            try:
                config = decrypter.decrypt(row["data"])
            except (ValueError, KeyError):
                result.warnings.append(f"Backup {row['id']}: not readable, skipped")
                continue
            db.add(
                Backup(
                    device_id=device_id,
                    created_at=row.get("created_at"),
                    status=BackupStatus.OK,
                    config_encrypted=box.encrypt(config),
                    sha256=hashlib.sha256(config.encode()).hexdigest(),
                    size=len(config.encode()),
                    changed=True,
                    created_by="import",
                )
            )
            result.add("backups")


async def _import_reference(
    db: AsyncSession,
    tables: dict[str, Rows],
    decrypter: LaravelDecrypter,
    ids: dict[str, dict[int, int]],
    result: ImportResult,
) -> None:
    for row in tables.get("vlans", []):
        site_id = ids["sites"].get(row["site_id"])
        exists = await db.scalar(
            select(SiteVlan.id).where(SiteVlan.site_id == site_id, SiteVlan.vid == row["vid"])
        )
        if site_id is None or exists:
            continue
        db.add(
            SiteVlan(
                site_id=site_id,
                vid=row["vid"],
                name=row["name"][:64],
                description=(row.get("description") or "")[:255],
                ip_range=row.get("ip_range") or None,
                is_client_vlan=bool(row.get("is_client_vlan", True)),
                scan_enabled=bool(row.get("is_scanned", False)),
                sync_enabled=bool(row.get("is_synced", True)),
            )
        )
        result.add("vlans")

    icons = {r["mac_type"]: r["mac_icon"] for r in tables.get("mac_type_icons", [])}
    known_prefixes = set((await db.execute(select(MacType.prefix))).scalars())
    for row in tables.get("mac_types", []):
        prefix = normalize_prefix(row.get("mac_prefix", ""))
        if prefix is None or prefix in known_prefixes:
            continue
        name = row.get("description") or row.get("type") or prefix
        db.add(
            MacType(
                prefix=prefix,
                name=name[:64],
                icon=icon_for(f"{row.get('type', '')} {icons.get(row.get('type'), '')}"),
            )
        )
        known_prefixes.add(prefix)
        result.add("mac types")

    known_gateways = set((await db.execute(select(SnmpGateway.hostname))).scalars())
    for row in tables.get("routers", []):
        if row["ip"] not in known_gateways:
            db.add(
                SnmpGateway(
                    name=(row.get("desc") or row["ip"])[:100], hostname=row["ip"], entries=0
                )
            )
            result.add("gateways")

    known_keys = set((await db.execute(select(SshPublicKey.fingerprint))).scalars())
    for row in tables.get("public_keys", []):
        try:
            key = " ".join(decrypter.decrypt(row["key"]).split())
            fp = fingerprint(key)
        except Exception as exc:
            result.warnings.append(f"SSH key {row.get('description')}: {exc}")
            continue
        if fp not in known_keys:
            db.add(SshPublicKey(description=row["description"][:100], key=key, fingerprint=fp))
            known_keys.add(fp)
            result.add("ssh keys")
    await db.flush()


LEGACY_TABLES = (
    "sites",
    "buildings",
    "rooms",
    "devices",
    "device_backups",
    "vlans",
    "mac_types",
    "mac_type_icons",
    "routers",
    "public_keys",
)


def read_mysql(url: str, with_backups: bool) -> dict[str, Rows]:
    """Read the old tables (needs ``pip install pymysql``)."""
    from urllib.parse import unquote, urlparse

    import pymysql  # type: ignore[import-untyped]
    import pymysql.cursors  # type: ignore[import-untyped]

    parsed = urlparse(url)
    conn = pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )
    tables: dict[str, Rows] = {}
    try:
        with conn.cursor() as cursor:
            for table in LEGACY_TABLES:
                if table == "device_backups" and not with_backups:
                    continue
                try:
                    cursor.execute(f"SELECT * FROM `{table}`")
                    tables[table] = list(cursor.fetchall())
                except pymysql.err.ProgrammingError:
                    log.warning("Table %s not found, skipped", table)
    finally:
        conn.close()
    return tables
