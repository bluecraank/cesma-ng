from httpx import AsyncClient

from tests.conftest import grant, user_id


async def _site(admin: AsyncClient, name: str) -> int:
    r = await admin.post("/sites", json={"name": name})
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_user_sees_only_assigned_sites(alice: AsyncClient, bob: AsyncClient) -> None:
    hq = await _site(alice, "HQ")
    await _site(alice, "Branch")
    assert (await bob.get("/sites")).json() == []

    await grant(alice, "bob", {hq: "viewer"})
    names = [s["name"] for s in (await bob.get("/sites")).json()]
    assert names == ["HQ"]


async def test_viewer_cannot_change_but_site_admin_can(
    alice: AsyncClient, bob: AsyncClient
) -> None:
    hq = await _site(alice, "HQ")
    await grant(alice, "bob", {hq: "viewer"})
    assert (await bob.post(f"/sites/{hq}/buildings", json={"name": "A"})).status_code == 403

    await grant(alice, "bob", {hq: "admin"})
    building = await bob.post(f"/sites/{hq}/buildings", json={"name": "A"})
    assert building.status_code == 201
    room = await bob.post(f"/buildings/{building.json()['id']}/rooms", json={"name": "Server"})
    assert room.status_code == 201

    tree = (await bob.get(f"/sites/{hq}")).json()
    assert tree["buildings"][0]["rooms"][0]["name"] == "Server"


async def test_only_superadmin_creates_sites_and_manages_users(
    alice: AsyncClient, bob: AsyncClient
) -> None:
    hq = await _site(alice, "HQ")
    await grant(alice, "bob", {hq: "admin"})
    assert (await bob.post("/sites", json={"name": "X"})).status_code == 403
    assert (await bob.get("/users")).status_code == 403
    assert (await bob.delete(f"/sites/{hq}")).status_code == 403


async def test_superadmin_cannot_lock_themselves_out(alice: AsyncClient) -> None:
    me = await user_id(alice, "alice")
    r = await alice.patch(f"/users/{me}", json={"is_superadmin": False})
    assert r.status_code == 422


async def test_duplicate_site_name_conflicts(alice: AsyncClient) -> None:
    await _site(alice, "HQ")
    assert (await alice.post("/sites", json={"name": "HQ"})).status_code == 409


async def test_role_changes_are_audited(alice: AsyncClient, bob: AsyncClient) -> None:
    hq = await _site(alice, "HQ")
    await grant(alice, "bob", {hq: "admin"})
    entries = (await alice.get("/audit", params={"action": "user.update"})).json()["items"]
    assert entries[0]["new_values"] == {"site_roles": {str(hq): "Administrator"}}
