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


async def test_ssh_key_upload_is_switched_off_by_default(alice: AsyncClient) -> None:
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    r = await alice.post("/jobs", json={"kind": "ssh_keys", "site_id": site})
    assert r.status_code == 422 and "switched off" in r.text
    assert (await alice.get("/features")).json() == {"ssh_key_push": False}


async def test_ssh_keys_need_two_and_valid_format(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    app.state.settings = settings.model_copy(update={"ssh_key_push_enabled": True})
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


# --- Port profiles bound to ports ------------------------------------------------------------


async def _run_jobs(app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    async with app.state.database.sessionmaker() as db:
        while (pending := await jobs.next_pending(db)) is not None:
            await jobs.run_job(db, pending, Runtime(settings, app.state.secret_box))


async def test_bound_ports_follow_their_profile(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    p5, p6 = await _port(alice, device_id, "5"), await _port(alice, device_id, "6")
    profile = (
        await alice.post(
            f"/sites/{site_id}/port-profiles",
            json={"name": "Office", "untagged_vid": 515, "tagged_vids": [520]},
        )
    ).json()
    assert profile["bound_ports"] == 0 and profile["job_id"] is None

    # apply and bind
    r = await alice.post(
        f"/devices/{device_id}/ports/apply",
        json={"port_ids": [p5["id"], p6["id"]], "profile_id": profile["id"], "bind": True},
    )
    assert r.status_code == 200, r.text
    port = await _port(alice, device_id, "5")
    assert port["port_profile_id"] == profile["id"]
    assert port["untagged_vlans"] == [515] and port["tagged_vlans"] == [520]
    listed = (await alice.get(f"/sites/{site_id}/port-profiles")).json()
    assert listed[0]["bound_ports"] == 2

    # 1. a bound port cannot be changed on its own ...
    r = await alice.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [p5["id"]], "tagged": [530]}
    )
    assert r.status_code == 422 and "Office" in r.text
    # ... switching it off is still possible (not part of a profile)
    r = await alice.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [p5["id"]], "enabled": False}
    )
    assert r.status_code == 200, r.text

    # 2. changing the profile rolls the change out to every bound port
    saved = (
        await alice.put(
            f"/sites/{site_id}/port-profiles/{profile['id']}",
            json={"name": "Office", "untagged_vid": 515, "tagged_vids": [520, 530]},
        )
    ).json()
    assert saved["job_id"] is not None and saved["bound_ports"] == 2
    await _run_jobs(app, settings)
    job = (await alice.get(f"/jobs/{saved['job_id']}")).json()
    assert job["status"] == "done", job
    for name in ("5", "6"):
        assert (await _port(alice, device_id, name))["tagged_vlans"] == [520, 530]

    # renaming only does not touch the switches
    renamed = (
        await alice.put(
            f"/sites/{site_id}/port-profiles/{profile['id']}",
            json={"name": "Büro", "untagged_vid": 515, "tagged_vids": [520, 530]},
        )
    ).json()
    assert renamed["job_id"] is None

    # unbinding releases the port, the configuration stays
    r = await alice.post(f"/devices/{device_id}/ports/unbind", json={"port_ids": [p5["id"]]})
    assert r.json() == {"released": 1}
    port = await _port(alice, device_id, "5")
    assert port["port_profile_id"] is None and port["tagged_vlans"] == [520, 530]
    r = await alice.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [p5["id"]], "tagged": [530]}
    )
    assert r.status_code == 200

    # deleting the profile releases the remaining ports
    await alice.delete(f"/sites/{site_id}/port-profiles/{profile['id']}")
    assert (await _port(alice, device_id, "6"))["port_profile_id"] is None


async def test_binding_needs_a_profile(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    p5 = await _port(alice, device_id, "5")
    r = await alice.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [p5["id"]], "bind": True}
    )
    assert r.status_code == 422


async def test_poll_during_apply_does_not_fail_the_change(
    alice: AsyncClient, app, settings: Settings, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The worker may poll the switch while the change is written (AOS-CX saves slowly).

    It then stores the new VLANs first; the change must still succeed and be audited.
    """
    from app.drivers.writers import SimulatedWriter
    from app.models import PortVlan

    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    port = await _port(alice, device_id, "5")
    original = SimulatedWriter.apply

    async def apply_while_polled(self, operations):  # type: ignore[no-untyped-def]
        # what the poller writes: the switch already reports VLAN 520 tagged on port 5
        async with app.state.database.sessionmaker() as worker_db:
            worker_db.add(PortVlan(port_id=port["id"], vid=520, tagged=True))
            await worker_db.commit()
        return await original(self, operations)

    monkeypatch.setattr(SimulatedWriter, "apply", apply_while_polled)
    r = await alice.post(
        f"/devices/{device_id}/ports/apply",
        json={"port_ids": [port["id"]], "add_tagged": [520]},
    )
    assert r.status_code == 200, r.text
    assert 520 in (await _port(alice, device_id, "5"))["tagged_vlans"]
    entry = (await alice.get("/audit", params={"action": "port.update"})).json()["items"][0]
    assert entry["new_values"]["5"]["tagged"] == [120, 520]


async def test_unexpected_switch_failure_is_reported_and_audited(
    alice: AsyncClient, app, settings: Settings, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.drivers.writers import SimulatedWriter

    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    port = await _port(alice, device_id, "5")

    async def broken(self, operations):  # type: ignore[no-untyped-def]
        raise RuntimeError("Authentication failed")

    monkeypatch.setattr(SimulatedWriter, "apply", broken)
    r = await alice.post(
        f"/devices/{device_id}/ports/apply", json={"port_ids": [port["id"]], "description": "x"}
    )
    assert r.status_code == 502
    assert "Authentication failed" in r.json()["detail"]
    entry = (await alice.get("/audit", params={"action": "port.update_failed"})).json()["items"]
    assert "Authentication failed" in entry[0]["message"]


async def test_failed_login_test_shows_a_hint(
    alice: AsyncClient, app, settings: Settings, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The worker tests the login like the SNMP poll; a wrong password becomes a hint."""
    from app.drivers.writers import SimulatedWriter, WriteError

    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    hints = (await alice.get(f"/sites/{site_id}/device-hints")).json()
    assert not any(h["code"] == "login_failed" for h in hints)  # the simulated login worked

    async def denied(self):  # type: ignore[no-untyped-def]
        raise WriteError("API login as admin failed: HTTP 401 Authentication failed")

    monkeypatch.setattr(SimulatedWriter, "test_login", denied)
    async with app.state.database.sessionmaker() as db:
        assert not await poll_device(
            db,
            device_id,
            PollTask.LOGIN,
            settings=settings,
            box=app.state.secret_box,
            driver_factory=driver_factory_for(settings),
        )
    hints = (await alice.get(f"/sites/{site_id}/device-hints")).json()
    [hint] = [h for h in hints if h["code"] == "login_failed"]
    assert "Authentication failed" in hint["detail"] and hint["device_id"] == device_id
    # the switch answers SNMP: a failed login does not make it offline
    assert (await alice.get(f"/devices/{device_id}")).json()["status"] == "online"


# --- Port changes and renames as background jobs (task list) ---------------------------------


async def test_port_change_as_job(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    p5, p6 = await _port(alice, device_id, "5"), await _port(alice, device_id, "6")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]

    # errors still come back right away, nothing is queued
    bad = await alice.post(f"/devices/{device_id}/ports/jobs", json={"port_ids": [999999]})
    assert bad.status_code == 404
    await grant(alice, "bob", {site_id: "viewer"})
    denied = await bob.post(
        f"/devices/{device_id}/ports/jobs", json={"port_ids": [p5["id"]], "enabled": False}
    )
    assert denied.status_code == 403

    r = await alice.post(
        f"/devices/{device_id}/ports/jobs",
        json={"port_ids": [p5["id"], p6["id"]], "description": "Drucker"},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert (job["kind"], job["status"], job["device_id"]) == ("port_change", "pending", device_id)
    assert job["summary"] == "hp-2530-48g: 5, 6"
    assert (await _port(alice, device_id, "5"))["description"] != "Drucker"  # not yet

    await _run_jobs(app, settings)
    done = (await alice.get(f"/jobs/{job['id']}")).json()
    assert done["status"] == "done", done
    assert "[simulated]" in done["log"]
    assert (await _port(alice, device_id, "6"))["description"] == "Drucker"
    # audited once, as the change itself (not as "job queued")
    actions = [e["action"] for e in (await alice.get("/audit")).json()["items"]]
    assert "port.update" in actions and "job.port_change" not in actions

    # the task list: all visible sites, newest first, limited
    listed = (await alice.get("/jobs", params={"limit": 1})).json()
    assert [j["id"] for j in listed] == [job["id"]]


async def test_rename_as_job(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    bad = await alice.post(f"/devices/{device_id}/rename/jobs", json={"name": "mit leerzeichen"})
    assert bad.status_code == 422
    job = (await alice.post(f"/devices/{device_id}/rename/jobs", json={"name": "sw-og-07"})).json()
    assert job["summary"] == "hp-2530-48g → sw-og-07"
    await _run_jobs(app, settings)
    assert (await alice.get(f"/jobs/{job['id']}")).json()["status"] == "done"
    assert (await alice.get(f"/devices/{device_id}")).json()["name"] == "sw-og-07"


async def test_quick_jobs_have_their_own_lane(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    p5 = await _port(alice, device_id, "5")
    backup = (await alice.post("/jobs", json={"kind": "backup", "site_id": site_id})).json()
    change = (
        await alice.post(
            f"/devices/{device_id}/ports/jobs", json={"port_ids": [p5["id"]], "enabled": False}
        )
    ).json()
    async with app.state.database.sessionmaker() as db:
        assert (await jobs.next_pending(db, quick=False)).id == backup["id"]  # type: ignore[union-attr]
        assert (await jobs.next_pending(db, quick=True)).id == change["id"]  # type: ignore[union-attr]
        # one job at a time per switch
        assert await jobs.next_pending(db, quick=True, busy_devices={device_id}) is None
        assert await jobs.next_pending(db, quick=True, exclude_ids={change["id"]}) is None


async def test_restore_is_not_possible(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    r = await alice.post("/jobs", json={"kind": "restore", "site_id": site_id, "backup_id": 1})
    assert r.status_code == 422


async def test_backup_of_one_switch_names_it(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    job = (
        await alice.post(
            "/jobs", json={"kind": "backup", "site_id": site_id, "device_ids": [device_id]}
        )
    ).json()
    assert (job["summary"], job["device_id"]) == ("hp-2530-48g", device_id)
