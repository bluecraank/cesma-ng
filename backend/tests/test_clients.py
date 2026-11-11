import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.domain.mac import mac_like_patterns, normalize_mac, normalize_prefix
from app.models import Client, MacType, PollTask
from app.services import clients
from app.services.polling import driver_factory_for, poll_device
from app.services.uplinks import uplink_port_ids
from tests.conftest import RECORDINGS as FIXTURES
from tests.conftest import recording


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
        ("aabb.ccdd.eeff", "aa:bb:cc:dd:ee:ff"),
        ("aa-bb-cc-dd-ee-ff", "aa:bb:cc:dd:ee:ff"),
        ("aabbccddeeff", "aa:bb:cc:dd:ee:ff"),
        ("aabbccddee", None),
        ("not a mac", None),
    ],
)
def test_normalize_mac(raw: str, expected: str | None) -> None:
    assert normalize_mac(raw) == expected


def test_mac_fragments_match_both_alignments() -> None:
    mac = "aa:bb:cc:dd:ee:ff"
    for fragment in ("bbcc", "bccd", "bb:cc", "ccdd.ee"):
        patterns = mac_like_patterns(fragment)
        assert any(_like(mac, p) for p in patterns), fragment
    assert mac_like_patterns("printer") == []


def _like(value: str, pattern: str) -> bool:
    return pattern.strip("%") in value


def test_prefix_and_type_matching() -> None:
    assert normalize_prefix("000B82") == "00:0b:82"
    assert normalize_prefix("000B8") is None
    types = [MacType(prefix="00:0b", name="short"), MacType(prefix="00:0b:82", name="phone")]
    assert clients.match_type("00:0b:82:11:22:33", types).name == "phone"  # type: ignore[union-attr]
    assert clients.match_type("00:0b:99:11:22:33", types).name == "short"  # type: ignore[union-attr]
    assert clients.match_type("11:22:33:44:55:66", types) is None


def test_parse_ieee_oui_csv() -> None:
    text = (
        "Registry,Assignment,Organization Name,Organization Address\n"
        'MA-L,000B82,"Grandstream Networks, Inc.",Boston US\n'
        "MA-L,BAD,Ignored,\n"
    )
    assert clients.parse_oui_csv(text) == {"00:0b:82": "Grandstream Networks, Inc."}


async def _polled_switch(
    alice: AsyncClient, app, settings: Settings, hostname: str, model: str
) -> int:  # type: ignore[no-untyped-def]
    recording(hostname)
    sites = (await alice.get("/sites")).json()
    site = (
        sites[0]["id"] if sites else (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    )
    body = {"name": hostname, "hostname": hostname, "model": model, "site_id": site}
    device_id = int((await alice.post("/devices", json=body)).json()["id"])
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    for task in PollTask:
        async with app.state.database.sessionmaker() as db:
            assert await poll_device(
                db,
                device_id,
                task,
                settings=settings,
                box=app.state.secret_box,
                driver_factory=driver_factory_for(settings),
            )
    return device_id


async def test_clients_are_located_on_access_ports(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    device_id = await _polled_switch(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    async with app.state.database.sessionmaker() as db:
        count = await clients.update_clients(db)
        await db.commit()
        uplinks = await uplink_port_ids(db)
        rows = (await db.execute(select(Client))).scalars().all()
    assert count == len(rows) > 0
    assert all(c.port_id not in uplinks for c in rows)  # never on Trk1 / port 51
    assert all(c.device_id == device_id for c in rows)

    some = rows[0]
    page = (
        await alice.get("/clients", params={"q": some.mac_address.replace(":", "")[2:8]})
    ).json()
    assert any(c["mac_address"] == some.mac_address for c in page["items"])
    assert page["items"][0]["active"] is True

    with_ip = next((c for c in rows if c.ip_address), None)
    if with_ip is not None:
        found = (await alice.get("/clients", params={"q": with_ip.ip_address})).json()["items"]
        assert found[0]["mac_address"] == with_ip.mac_address


async def test_macs_behind_uplinks_are_no_clients(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    # In this recording all 496 MACs of the N1548P are learned on its uplink Te1/0/1.
    await _polled_switch(alice, app, settings, "dell-n1548p", "dell_n1500")
    async with app.state.database.sessionmaker() as db:
        assert await clients.update_clients(db) == 0


async def test_client_first_seen_is_kept(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    await _polled_switch(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    async with app.state.database.sessionmaker() as db:
        await clients.update_clients(db)
        await db.commit()
        first = (await db.execute(select(Client).limit(1))).scalar_one()
        first_seen = first.first_seen_at
        # second run keeps first_seen_at
        await clients.update_clients(db)
        await db.commit()
        again = await db.get(Client, first.id)
        assert again is not None and again.first_seen_at == first_seen


async def test_global_search_finds_devices_and_vlans(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    await _polled_switch(alice, app, settings, "dell-os10", "dell_os10")
    hits = (await alice.get("/search", params={"q": "dell-os"})).json()["hits"]
    assert hits[0]["kind"] == "device" and hits[0]["title"] == "dell-os10"
    vlan_hits = (await alice.get("/search", params={"q": "120"})).json()["hits"]
    assert any(h["kind"] == "vlan" for h in vlan_hits)


async def test_mac_types_need_valid_prefix(alice: AsyncClient, bob: AsyncClient) -> None:
    ok = await alice.post(
        "/mac-types", json={"prefix": "00-0B-82", "name": "Phone", "icon": "phone"}
    )
    assert ok.status_code == 201 and ok.json()["prefix"] == "00:0b:82"
    assert (await alice.post("/mac-types", json={"prefix": "xyz", "name": "x"})).status_code == 422
    assert (
        await alice.post("/mac-types", json={"prefix": "000b82", "name": "dup"})
    ).status_code == 409
    assert (await bob.post("/mac-types", json={"prefix": "aabbcc", "name": "x"})).status_code == 403
