"""Import from cesma-on-premise: Laravel decryption and mapping."""

import base64
import hashlib
import hmac
import json
import os

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from sqlalchemy import select

from app.legacy_import import LaravelDecrypter, icon_for, import_legacy, php_unserialize_string
from app.models import CredentialProfile, Device, MacType, SiteVlan, SnmpGateway, SshPublicKey
from app.services.credentials import to_device_credentials

KEY = os.urandom(32)
APP_KEY = "base64:" + base64.b64encode(KEY).decode()
SSH_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl admin"


def laravel_encrypt(value: str) -> str:
    """What Laravel's Crypt::encrypt() produces (serialize + AES-256-CBC + HMAC)."""
    plain = f's:{len(value.encode())}:"{value}";'.encode()
    iv = os.urandom(16)
    padder = PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY), modes.CBC(iv)).encryptor()
    value_b64 = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()
    iv_b64 = base64.b64encode(iv).decode()
    mac = hmac.new(KEY, (iv_b64 + value_b64).encode(), hashlib.sha256).hexdigest()
    return base64.b64encode(
        json.dumps({"iv": iv_b64, "value": value_b64, "mac": mac, "tag": ""}).encode()
    ).decode()


def test_decrypts_laravel_values() -> None:
    assert LaravelDecrypter(APP_KEY).decrypt(laravel_encrypt("geheim!")) == "geheim!"
    assert LaravelDecrypter(APP_KEY).decrypt(laravel_encrypt('Grüße "x"')) == 'Grüße "x"'


def test_wrong_key_is_detected() -> None:
    other = "base64:" + base64.b64encode(os.urandom(32)).decode()
    with pytest.raises(ValueError, match="MAC"):
        LaravelDecrypter(other).decrypt(laravel_encrypt("x"))


def test_unserialize_and_icons() -> None:
    assert php_unserialize_string('s:6:"public";') == "public"
    assert php_unserialize_string("plain") == "plain"
    assert icon_for("Drucker Etage 2") == "printer"
    assert icon_for("VoIP") == "phone"
    assert icon_for("something") == "device"


async def test_import_maps_old_data(app) -> None:  # type: ignore[no-untyped-def]
    password = laravel_encrypt("sw-pass")
    tables = {
        "sites": [{"id": 7, "name": "Zentrale"}],
        "buildings": [{"id": 3, "site_id": 7, "name": "Haus A"}],
        "rooms": [{"id": 9, "building_id": 3, "name": "Serverraum"}],
        "devices": [
            {
                "id": 1,
                "name": "sw1",
                "hostname": "10.0.0.1",
                "type": "aruba-os",
                "site_id": 7,
                "room_id": 9,
                "username": "admin",
                "password": password,
                "location_description": 4,
            },
            {
                "id": 2,
                "name": "sw2",
                "hostname": "10.0.0.2",
                "type": "dell-emc-powerswitch",
                "site_id": 7,
                "room_id": 9,
                "username": "admin",
                "password": laravel_encrypt("sw-pass"),
            },
            {
                "id": 3,
                "name": "old",
                "hostname": "10.0.0.3",
                "type": "cisco",
                "site_id": 7,
                "room_id": 9,
                "username": "admin",
                "password": password,
            },
        ],
        "vlans": [
            {
                "vid": 10,
                "name": "Office",
                "site_id": 7,
                "ip_range": "10.1.10.0/24",
                "is_client_vlan": 1,
                "is_synced": 1,
                "is_scanned": 1,
            }
        ],
        "mac_types": [{"mac_prefix": "00:0B:82", "type": "phone", "description": "Grandstream"}],
        "mac_type_icons": [{"mac_type": "phone", "mac_icon": "mdi-phone"}],
        "routers": [{"ip": "10.0.0.254", "desc": "Core router"}],
        "public_keys": [{"description": "Admin", "key": laravel_encrypt(SSH_KEY)}],
    }
    async with app.state.database.sessionmaker() as db:
        result = await import_legacy(db, tables, LaravelDecrypter(APP_KEY), app.state.secret_box)
        await db.commit()
        devices = {d.name: d for d in (await db.execute(select(Device))).scalars()}
        assert set(devices) == {"sw1", "sw2"}
        assert devices["sw1"].model.value == "aruba_os_switch"
        assert devices["sw2"].model.value == "dell_n1500"
        # same user + password -> one shared credential profile
        [profile] = (await db.execute(select(CredentialProfile))).scalars().all()
        assert to_device_credentials(profile, app.state.secret_box).api.password == "sw-pass"
        vlan = (await db.execute(select(SiteVlan))).scalar_one()
        assert (vlan.vid, vlan.scan_enabled) == (10, True)
        mac_type = (await db.execute(select(MacType))).scalar_one()
        assert (mac_type.prefix, mac_type.icon) == ("00:0b:82", "phone")
        assert (await db.execute(select(SnmpGateway))).scalar_one().hostname == "10.0.0.254"
        assert (await db.execute(select(SshPublicKey))).scalar_one().key == SSH_KEY
    assert any("cisco" in w for w in result.warnings)
    assert result.counts["devices"] == 2
