from httpx import AsyncClient

from tests.conftest import grant


async def _setup(alice: AsyncClient) -> dict[str, int]:
    hq = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    branch = (await alice.post("/sites", json={"name": "Branch"})).json()["id"]
    building = (await alice.post(f"/sites/{hq}/buildings", json={"name": "A"})).json()["id"]
    room = (await alice.post(f"/buildings/{building}/rooms", json={"name": "Server"})).json()["id"]
    return {"hq": hq, "branch": branch, "room": room}


def _device(site_id: int, **extra: object) -> dict[str, object]:
    return {
        "name": "sw-01",
        "hostname": "10.0.0.1",
        "model": "dell_n1500",
        "site_id": site_id,
        **extra,
    }


async def test_create_and_list_device(alice: AsyncClient) -> None:
    ids = await _setup(alice)
    r = await alice.post("/devices", json=_device(ids["hq"], room_id=ids["room"]))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "unknown"
    listed = (await alice.get("/devices", params={"search": "sw-"})).json()
    assert [d["name"] for d in listed] == ["sw-01"]


async def test_room_must_belong_to_device_site(alice: AsyncClient) -> None:
    ids = await _setup(alice)
    r = await alice.post("/devices", json=_device(ids["branch"], room_id=ids["room"]))
    assert r.status_code == 422


async def test_duplicate_hostname_conflicts(alice: AsyncClient) -> None:
    ids = await _setup(alice)
    await alice.post("/devices", json=_device(ids["hq"]))
    r = await alice.post("/devices", json=_device(ids["hq"], name="sw-02"))
    assert r.status_code == 409


async def test_device_access_is_site_scoped(alice: AsyncClient, bob: AsyncClient) -> None:
    ids = await _setup(alice)
    device = (await alice.post("/devices", json=_device(ids["hq"]))).json()

    await grant(alice, "bob", {ids["branch"]: "admin"})
    assert (await bob.get("/devices")).json() == []
    assert (await bob.get(f"/devices/{device['id']}")).status_code == 403
    assert (
        await bob.post("/devices", json=_device(ids["hq"], name="x", hostname="x"))
    ).status_code == 403
    # moving into a site the user administers is not enough, the source site counts too
    r = await bob.patch(f"/devices/{device['id']}", json={"site_id": ids["branch"]})
    assert r.status_code == 403


async def test_device_update_is_audited_with_diff(alice: AsyncClient) -> None:
    ids = await _setup(alice)
    device = (await alice.post("/devices", json=_device(ids["hq"]))).json()
    r = await alice.patch(f"/devices/{device['id']}", json={"location_note": "Rack 3"})
    assert r.status_code == 200
    entry = (await alice.get("/audit", params={"action": "device.update"})).json()["items"][0]
    assert entry["old_values"] == {"location_note": ""}
    assert entry["new_values"] == {"location_note": "Rack 3"}
    assert entry["device_id"] == device["id"]


async def test_site_with_devices_cannot_be_deleted(alice: AsyncClient) -> None:
    ids = await _setup(alice)
    await alice.post("/devices", json=_device(ids["hq"]))
    assert (await alice.delete(f"/sites/{ids['hq']}")).status_code == 409


async def test_enums_are_stored_by_value(alice: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    ids = await _setup(alice)
    await alice.post("/devices", json=_device(ids["hq"], model="aruba_cx"))
    async with app.state.database.engine.connect() as conn:
        row = (await conn.exec_driver_sql("SELECT model, status FROM devices")).one()
    assert tuple(row) == ("aruba_cx", "unknown")


async def test_device_own_api_login_overrides_profile(alice: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    from app.models import CredentialProfile, Device
    from app.services.credentials import to_device_credentials

    ids = await _setup(alice)
    pid = (
        await alice.post(
            "/credential-profiles",
            json={"name": "shared", "api_username": "admin", "api_password": "profile-pw"},
        )
    ).json()["id"]
    r = await alice.post(
        "/devices",
        json=_device(
            ids["hq"], model="aruba_cx", credential_profile_id=pid, api_password="switch-pw"
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_password_set"] is True and body["api_username"] is None
    assert "switch-pw" not in r.text

    async def creds():  # type: ignore[no-untyped-def]
        async with app.state.database.sessionmaker() as db:
            device = await db.get(Device, body["id"])
            profile = await db.get(CredentialProfile, pid)
            assert device is not None and "switch-pw" not in (device.api_password_encrypted or "")
            return to_device_credentials(profile, app.state.secret_box, device)

    # own password, user name from the profile
    api = (await creds()).api
    assert (api.username, api.password) == ("admin", "switch-pw")

    # omitted password stays, own user name applies
    r = await alice.patch(f"/devices/{body['id']}", json={"api_username": "ops"})
    assert r.json()["api_password_set"] is True
    api = (await creds()).api
    assert (api.username, api.password) == ("ops", "switch-pw")

    # empty values fall back to the profile
    r = await alice.patch(f"/devices/{body['id']}", json={"api_username": "", "api_password": ""})
    assert r.json()["api_password_set"] is False and r.json()["api_username"] is None
    api = (await creds()).api
    assert (api.username, api.password) == ("admin", "profile-pw")

    entries = (await alice.get("/audit", params={"action": "device.update"})).json()["items"]
    assert all("switch-pw" not in str(e) for e in entries)


async def test_only_superadmin_sets_device_api_login(alice: AsyncClient, bob: AsyncClient) -> None:
    ids = await _setup(alice)
    device = (await alice.post("/devices", json=_device(ids["hq"]))).json()
    await grant(alice, "bob", {ids["hq"]: "admin"})
    r = await bob.patch(f"/devices/{device['id']}", json={"api_password": "x"})
    assert r.status_code == 403
    # other fields stay editable for site administrators
    r = await bob.patch(f"/devices/{device['id']}", json={"location_note": "Rack 1"})
    assert r.status_code == 200
