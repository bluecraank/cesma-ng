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
