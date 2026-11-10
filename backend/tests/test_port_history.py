"""Port history, free ports and configuration rules."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import delete, select, update

from app.core.config import Settings
from app.core.db import utcnow
from app.models import Backup, BackupStatus, FdbEntry, PollTask, Port, PortMacSighting
from app.services import link_watch
from app.services.polling import driver_factory_for, poll_device
from app.services.uplinks import uplink_port_ids
from tests.conftest import grant
from tests.test_config_changes import _polled, _port, _simulated_app


async def _poll(app, settings: Settings, device_id: int, task: PollTask) -> None:  # type: ignore[no-untyped-def]
    async with app.state.database.sessionmaker() as db:
        assert await poll_device(
            db,
            device_id,
            task,
            settings=settings,
            box=app.state.secret_box,
            driver_factory=driver_factory_for(settings),
        )


async def test_history_records_link_outside_changes_and_cesma_changes(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    port = await _port(alice, device_id, "5")

    # Pretend the switch looked different before: the next poll sees link and description changes.
    async with app.state.database.sessionmaker() as db:
        await db.execute(
            update(Port)
            .where(Port.id == port["id"])
            .values(oper_up=not port["oper_up"], description="alt")
        )
        await db.commit()
    await _poll(app, settings, device_id, PollTask.INVENTORY)

    body = {"port_ids": [port["id"]], "description": "Drucker EG"}
    assert (await alice.post(f"/devices/{device_id}/ports/apply", json=body)).status_code == 200

    history = (await alice.get(f"/devices/{device_id}/ports/{port['id']}/history")).json()
    kinds = [e["kind"] for e in history["events"]]
    assert kinds[0] == "configured" and history["events"][0]["actor"] == "alice"
    assert history["events"][0]["new"] == {"description": "Drucker EG"}
    assert "changed" in kinds and ("link_up" in kinds or "link_down" in kinds)
    changed = next(e for e in history["events"] if e["kind"] == "changed")
    assert changed["old"]["description"] == "alt"


async def test_devices_seen_only_on_access_ports(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    async with app.state.database.sessionmaker() as db:
        sightings = (await db.execute(select(PortMacSighting))).scalars().all()
        uplinks = await uplink_port_ids(db, device_id)
    assert sightings
    assert not {s.port_id for s in sightings} & uplinks

    port_id = sightings[0].port_id
    history = (await alice.get(f"/devices/{device_id}/ports/{port_id}/history")).json()
    assert sightings[0].mac_address in {d["mac_address"] for d in history["devices"]}


async def test_switchports_mark_free_ports(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    assert (await bob.get(f"/sites/{site}/switchports")).status_code == 403
    await grant(alice, "bob", {site: "viewer"})

    panel = (await bob.get(f"/sites/{site}/switchports", params={"min_days": 0})).json()[0]
    assert panel["model"] == "aruba_os_switch"
    ports = {p["name"]: p for p in panel["ports"]}
    assert len(ports) >= 48  # all ethernet ports, not only the free ones
    free = {n for n, p in ports.items() if p["free"]}
    assert free and all(not ports[n]["oper_up"] and not ports[n]["uplink"] for n in free)
    assert not any(p["free"] for p in ports.values() if p["oper_up"] or p["uplink"])
    # the tooltip shows what is connected: MAC table entries on access ports, LLDP neighbours
    with_devices = [p for p in ports.values() if p["connected"]]
    assert with_devices and all(p["mac_count"] >= len(p["connected"]) > 0 for p in with_devices)
    assert not any(p["connected"] for p in ports.values() if p["uplink"])

    # a port that went down yesterday is not free when 30 days are required
    one = next(iter(free))
    async with app.state.database.sessionmaker() as db:
        await db.execute(
            update(Port)
            .where(Port.id == ports[one]["id"])
            .values(last_change_at=utcnow() - timedelta(days=1))
        )
        await db.commit()
    panel = (await bob.get(f"/sites/{site}/switchports", params={"min_days": 30})).json()[0]
    assert not next(p for p in panel["ports"] if p["name"] == one)["free"]


async def test_compliance_rules(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    config = 'hostname "sw"\nntp server 10.0.0.1\ntelnet-server\npassword manager plaintext x\n'
    async with app.state.database.sessionmaker() as db:
        db.add(
            Backup(
                device_id=device_id,
                status=BackupStatus.OK,
                config_encrypted=app.state.secret_box.encrypt(config),
                size=len(config),
            )
        )
        await db.commit()

    bad = await alice.post(
        "/compliance-rules", json={"name": "x", "mode": "require", "pattern": "(unclosed"}
    )
    assert bad.status_code == 422
    for rule in (
        {"name": "NTP", "mode": "require", "pattern": r"^ntp server"},
        {"name": "Kein Telnet", "mode": "forbid", "pattern": "telnet-server"},
        {"name": "Nur Dell", "mode": "require", "pattern": "x", "models": ["dell_os10"]},
    ):
        assert (await alice.post("/compliance-rules", json=rule)).status_code == 201
    assert (
        await bob.post("/compliance-rules", json={"name": "y", "mode": "forbid", "pattern": "y"})
    ).status_code == 403

    result = (await alice.get(f"/sites/{site}/compliance")).json()
    rules = {r["id"]: r["name"] for r in result["rules"]}
    by_name = {rules[r["rule_id"]]: r for r in result["devices"][0]["results"]}
    assert set(by_name) == {"NTP", "Kein Telnet"}  # "Nur Dell" does not apply to HP
    assert by_name["NTP"]["passed"] is True
    assert by_name["Kein Telnet"] == {
        "rule_id": by_name["Kein Telnet"]["rule_id"],
        "passed": False,
        "lines": ["telnet-server"],
    }

    # viewers see the result, but not the configuration lines
    await grant(alice, "bob", {site: "viewer"})
    seen = (await bob.get(f"/sites/{site}/compliance")).json()["devices"][0]["results"]
    assert all(r["lines"] == [] for r in seen)


async def test_link_watch_finds_the_port_that_just_came_up(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    await _poll(app, settings, device_id, PollTask.FDB)
    site = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    ports = {p["name"]: p for p in (await alice.get(f"/devices/{device_id}/ports")).json()}
    async with app.state.database.sessionmaker() as db:
        with_mac = set((await db.execute(select(FdbEntry.port_id))).scalars())
    target = next(
        p for p in ports.values() if p["oper_up"] and not p["is_uplink"] and p["id"] in with_mac
    )
    # the switch says "up", cesma still thinks "down" and has no MAC entry yet: a device was
    # just plugged in
    async with app.state.database.sessionmaker() as db:
        await db.execute(update(Port).where(Port.id == target["id"]).values(oper_up=False))
        await db.execute(delete(FdbEntry).where(FdbEntry.port_id == target["id"]))
        await db.commit()
    link_watch._sites.clear()
    link_watch._last_fdb.clear()

    since = (utcnow() - timedelta(seconds=5)).isoformat()
    assert (await bob.post(f"/sites/{site}/link-watch", json={"since": since})).status_code == 403
    result = (await alice.post(f"/sites/{site}/link-watch", json={"since": since})).json()
    assert result["unreachable"] == []
    found = [e for e in result["events"] if e["port_id"] == target["id"]]
    assert len(found) == 1 and found[0]["still_up"] and found[0]["device_name"]
    assert found[0]["connected"] and found[0]["mac_count"] >= 1  # MAC table was read again

    # nothing new happened: no new events after now, and the scan is throttled
    later = utcnow().isoformat()
    assert (await alice.post(f"/sites/{site}/link-watch", json={"since": later})).json()[
        "events"
    ] == []
    history = (await alice.get(f"/devices/{device_id}/ports/{target['id']}/history")).json()
    assert history["events"][0]["kind"] == "link_up"

    # the link flaps (down, up again): still one entry for the port, with the count
    async with app.state.database.sessionmaker() as db:
        await db.execute(update(Port).where(Port.id == target["id"]).values(oper_up=False))
        await db.commit()
    link_watch._sites.clear()
    result = (await alice.post(f"/sites/{site}/link-watch", json={"since": since})).json()
    found = [e for e in result["events"] if e["port_id"] == target["id"]]
    assert len(found) == 1 and found[0]["link_ups"] == 2
