"""Port changes, site VLANs + sync, jobs, backups and SSH keys (simulator mode, no network)."""

from httpx import AsyncClient

from app.core.config import Settings
from app.models import Job, PollTask
from app.services import jobs
from app.services.context import Runtime
from app.services.polling import driver_factory_for, poll_device
from tests.conftest import RECORDINGS as FIXTURES
from tests.conftest import grant, recording

ED25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
RSA = (
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAgQC7vbqajDhA4zUxGdE7ftvEhdXzW1Npt7WqYi0ex1d7"
    "Wk3e5gV8Z3KXQ4P8kPZt0tF7gNnn3BgsUzB2oA8kfq3mUQHLsEh7JfF0d0pM5Pxp2E8Kx0g5Sx3Nc1hL"
    "5JdqvJ9kYp7Pq2T8RSo4bGJu3kM1vJmQv1QnB0d3o5bS3rL3NQ== test"
)


async def _simulated_app(app, settings: Settings) -> Settings:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    app.state.settings = settings
    return settings


async def _polled(alice: AsyncClient, app, settings: Settings, hostname: str, model: str) -> int:  # type: ignore[no-untyped-def]
    recording(hostname)
    sites = (await alice.get("/sites")).json()
    site = (
        sites[0]["id"] if sites else (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    )
    device_id = int(
        (
            await alice.post(
                "/devices",
                json={"name": hostname, "hostname": hostname, "model": model, "site_id": site},
            )
        ).json()["id"]
    )
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


async def _port(alice: AsyncClient, device_id: int, name: str) -> dict:  # type: ignore[type-arg]
    return next(
        p for p in (await alice.get(f"/devices/{device_id}/ports")).json() if p["name"] == name
    )


# --- Ports -----------------------------------------------------------------------------------


async def test_port_change_preview_and_apply(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    port = await _port(alice, device_id, "5")

    body = {"port_ids": [port["id"]], "description": "Drucker EG", "untagged": 515, "tagged": [520]}
    plan = (await alice.post(f"/devices/{device_id}/ports/plan", json=body)).json()
    # "tagged" is the complete wanted list: port 5 is tagged in 120 today, so 120 is removed
    assert plan["commands"] == [
        'PUT /ports/5 {"name": "Drucker EG"}',
        'POST /vlans-ports {"vlan_id": 520, "port_id": "5", "port_mode": "POM_TAGGED_STATIC"}',
        "DELETE /vlans-ports/120-5",
    ]
    assert plan["warnings"] == []

    result = await alice.post(f"/devices/{device_id}/ports/apply", json=body)
    assert result.status_code == 200, result.text
    assert all(line.startswith("[simulated]") for line in result.json()["log"])
    updated = await _port(alice, device_id, "5")
    assert updated["description"] == "Drucker EG" and updated["tagged_vlans"] == [520]

    entry = (await alice.get("/audit", params={"action": "port.update"})).json()["items"][0]
    assert entry["old_values"]["5"]["description"] == ""
    assert entry["new_values"]["5"]["tagged"] == [520]


async def test_disabling_an_uplink_warns(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    trk = await _port(alice, device_id, "Trk1")
    plan = (
        await alice.post(
            f"/devices/{device_id}/ports/plan",
            json={"port_ids": [trk["id"]], "enabled": False, "tagged": [4000]},
        )
    ).json()
    assert any(w.startswith("DANGER") for w in plan["warnings"])
    assert any("4000" in w for w in plan["warnings"])  # VLAN does not exist on the switch


async def test_viewer_cannot_change_ports(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    port = await _port(alice, device_id, "5")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    await grant(alice, "bob", {site_id: "viewer"})
    r = await bob.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [port["id"]], "enabled": False}
    )
    assert r.status_code == 403


# --- Site VLANs, sync job --------------------------------------------------------------------


async def test_vlan_import_sync_plan_and_job(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "dell-n1548p", "dell_n1500")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]

    assert (await alice.post(f"/sites/{site_id}/vlans/import")).json() == {"imported": 33}
    assert (
        await alice.post(f"/sites/{site_id}/vlans", json={"vid": 777, "name": "New"})
    ).status_code == 201
    assert (
        await alice.post(f"/sites/{site_id}/vlans", json={"vid": 777, "name": "Dup"})
    ).status_code == 409
    bad = await alice.post(
        f"/sites/{site_id}/vlans", json={"vid": 778, "name": "x", "ip_range": "nope"}
    )
    assert bad.status_code == 422

    vlans = (await alice.get(f"/sites/{site_id}/vlans")).json()
    assert next(v for v in vlans if v["vid"] == 777)["devices_with_vlan"] == 0

    [plan] = (await alice.post(f"/sites/{site_id}/vlans/sync/plan", json={})).json()
    assert plan["commands"] == ["vlan 777", 'name "New"', "exit"]

    # a switch that was never polled gets no changes, only a warning
    never = (
        await alice.post(
            "/devices",
            json={"name": "new", "hostname": "10.9.9.9", "model": "dell_n1500", "site_id": site_id},
        )
    ).json()
    plans = (await alice.post(f"/sites/{site_id}/vlans/sync/plan", json={})).json()
    unpolled = next(p for p in plans if p["device_id"] == never["id"])
    assert unpolled["operations"] == 0 and "not been polled" in unpolled["warnings"][0]
    await alice.delete(f"/devices/{never['id']}")

    job = (await alice.post("/jobs", json={"kind": "vlan_sync", "site_id": site_id})).json()
    async with app.state.database.sessionmaker() as db:
        pending = await jobs.next_pending(db)
        assert pending is not None and pending.id == job["id"]
        await jobs.run_job(db, pending, Runtime(settings, app.state.secret_box))
    done = (await alice.get(f"/jobs/{job['id']}")).json()
    assert done["status"] == "done", done
    assert "1 change(s) applied" in done["log"]


async def test_backup_job_download_and_diff(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "dell-os10", "dell_os10")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    runtime = Runtime(settings, app.state.secret_box)
    for _ in range(2):
        await alice.post("/jobs", json={"kind": "backup", "site_id": site_id})
        async with app.state.database.sessionmaker() as db:
            job = await jobs.next_pending(db)
            assert isinstance(job, Job)
            await jobs.run_job(db, job, runtime)

    listed = (await alice.get("/backups", params={"device_id": device_id})).json()
    assert [b["status"] for b in listed] == ["ok", "ok"]
    assert [b["changed"] for b in listed] == [False, True]  # newest first: unchanged

    download = await alice.get(f"/backups/{listed[0]['id']}/config")
    assert download.status_code == 200 and "simulated" in download.text
    assert "attachment" in download.headers["content-disposition"]
    diff = (
        await alice.get("/backups/diff", params={"old": listed[1]["id"], "new": listed[0]["id"]})
    ).json()
    assert diff["diff"] == ""  # identical

    await grant(alice, "bob", {site_id: "viewer"})
    assert (
        await bob.get(f"/backups/{listed[0]['id']}/config")
    ).status_code == 403  # contains secrets


# --- SSH keys --------------------------------------------------------------------------------


async def test_ssh_keys_need_two_and_valid_format(alice: AsyncClient) -> None:
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    assert (
        await alice.post("/ssh-keys", json={"description": "x", "key": "not a key at all, really"})
    ).status_code == 422
    first = await alice.post("/ssh-keys", json={"description": "Admin 1", "key": ED25519})
    assert first.status_code == 201 and first.json()["fingerprint"].startswith("SHA256:")
    assert (
        await alice.post("/ssh-keys", json={"description": "dup", "key": ED25519})
    ).status_code == 409

    too_few = await alice.post("/jobs", json={"kind": "ssh_keys", "site_id": site})
    assert too_few.status_code == 422
    assert (
        await alice.post("/ssh-keys", json={"description": "Admin 2", "key": RSA})
    ).status_code == 201
    assert (
        await alice.post("/jobs", json={"kind": "ssh_keys", "site_id": site})
    ).status_code == 202


async def test_tag_uplinks_only_adds_to_trunks(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    await alice.post(f"/sites/{site_id}/vlans/import")
    await alice.post(f"/sites/{site_id}/vlans", json={"vid": 777, "name": "New"})
    [plan] = (
        await alice.post(f"/sites/{site_id}/vlans/sync/plan", json={"tag_uplinks": True})
    ).json()
    tagged = [c for c in plan["commands"] if "POM_TAGGED_STATIC" in c]
    assert {('"port_id": "Trk1"' in c) or ('"port_id": "51"' in c) for c in tagged} == {True}
    assert any('"vlan_id": 777' in c and "Trk1" in c for c in tagged)
    assert not any(c.startswith("DELETE /vlans-ports") for c in plan["commands"])  # never removes
    assert any("Uplinks" in w for w in plan["warnings"])


async def test_rename_sets_hostname_on_switch_and_in_cesma(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    bad = await alice.post(f"/devices/{device_id}/rename/plan", json={"name": "mit leerzeichen"})
    assert bad.status_code == 422

    plan = (await alice.post(f"/devices/{device_id}/rename/plan", json={"name": "sw-og-07"})).json()
    assert plan["commands"] == ['PUT /system {"name": "sw-og-07"}']
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    await grant(alice, "bob", {site_id: "viewer"})
    assert (
        await bob.post(f"/devices/{device_id}/rename/apply", json={"name": "sw-og-07"})
    ).status_code == 403

    result = (
        await alice.post(f"/devices/{device_id}/rename/apply", json={"name": "sw-og-07"})
    ).json()
    assert result["log"][0].startswith("[simulated]")
    device = (await alice.get(f"/devices/{device_id}")).json()
    assert (device["name"], device["sys_name"]) == ("sw-og-07", "sw-og-07")
