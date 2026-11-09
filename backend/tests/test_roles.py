"""Roles with permissions, per-user SSH keys, emergency login and single-VLAN tagging."""

from httpx import AsyncClient

from app.auth.authenticators import AuthBackendError, Identity
from app.core.config import Settings
from app.services.ssh_keys import keys_for_site
from tests.conftest import USERS, grant, user_id
from tests.test_config_changes import ED25519, RSA, _polled, _port, _simulated_app


async def _site(alice: AsyncClient) -> int:
    return int((await alice.post("/sites", json={"name": "HQ"})).json()["id"])


async def test_custom_role_allows_only_its_permissions(
    alice: AsyncClient, bob: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    site = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    role = await alice.post(
        "/roles", json={"name": "Ports", "description": "nur Ports", "permissions": ["ports.edit"]}
    )
    assert role.status_code == 201, role.text
    await grant(alice, "bob", {site: "Ports"})

    me = (await bob.get("/auth/me")).json()
    assert me["site_roles"] == [
        {
            "site_id": site,
            "role_id": role.json()["id"],
            "role_name": "Ports",
            "permissions": ["ports.edit"],
        }
    ]
    port = await _port(alice, device_id, "5")
    plan = await bob.post(
        f"/devices/{device_id}/ports/plan", json={"port_ids": [port["id"]], "description": "x"}
    )
    assert plan.status_code == 200
    # everything else is still forbidden
    assert (
        await bob.post(f"/sites/{site}/vlans", json={"vid": 99, "name": "x"})
    ).status_code == 403
    assert (
        await bob.post(f"/devices/{device_id}/console", json={"command": "show vlan"})
    ).status_code == 403
    assert (await bob.post("/jobs", json={"kind": "backup", "site_id": site})).status_code == 403


async def test_roles_are_managed_by_superadmins(alice: AsyncClient, bob: AsyncClient) -> None:
    site = await _site(alice)
    assert (await bob.post("/roles", json={"name": "x"})).status_code == 403
    roles = (await alice.get("/roles")).json()
    builtin = next(r for r in roles if r["builtin"] == "admin")
    assert (await alice.delete(f"/roles/{builtin['id']}")).status_code == 422

    custom = await alice.post("/roles", json={"name": "Backup", "permissions": ["backups.run"]})
    await grant(alice, "bob", {site: "Backup"})
    assert (await alice.delete(f"/roles/{custom.json()['id']}")).status_code == 409
    await grant(alice, "bob", {})
    assert (await alice.delete(f"/roles/{custom.json()['id']}")).status_code == 204
    assert (
        await alice.post("/roles", json={"name": "x", "permissions": ["nope"]})
    ).status_code == 422


async def test_ssh_keys_belong_to_users(alice: AsyncClient, bob: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    site = await _site(alice)
    assert (
        await bob.post("/ssh-keys", json={"description": "bob", "key": ED25519})
    ).status_code == 201
    assert (
        await alice.post("/ssh-keys", json={"description": "alice", "key": RSA})
    ).status_code == 201

    own = (await bob.get("/ssh-keys")).json()
    assert [k["description"] for k in own] == ["bob"]
    assert (await bob.get("/ssh-keys", params={"all_users": True})).status_code == 403
    everyone = (await alice.get("/ssh-keys", params={"all_users": True})).json()
    assert {k["owner"] for k in everyone} == {"alice", "bob"}
    # nobody deletes other people's keys, except super administrators
    alice_key = next(k for k in everyone if k["owner"] == "alice")
    assert (await bob.delete(f"/ssh-keys/{alice_key['id']}")).status_code == 403

    async def on_switches() -> set[str]:
        async with app.state.database.sessionmaker() as db:
            return {k.description for k in await keys_for_site(db, site)}

    await grant(alice, "bob", {site: "viewer"})  # "Lesen" has no SSH access
    assert await on_switches() == {"alice"}  # super administrators always
    await grant(alice, "bob", {site: "admin"})
    assert await on_switches() == {"alice", "bob"}


class _DirectoryDown:
    async def authenticate(self, username: str, password: str) -> Identity | None:
        raise AuthBackendError("domain controller not reachable (CESMA_LDAP_URL)")

    async def lookup(self, username: str) -> Identity | None:
        raise AuthBackendError("down")


async def test_emergency_password_only_while_directory_is_down(
    alice: AsyncClient, bob: AsyncClient, app, make_client
) -> None:  # type: ignore[no-untyped-def]
    bob_id = await user_id(alice, "bob")
    short = await alice.patch(f"/users/{bob_id}", json={"local_password": "kurz"})
    assert short.status_code == 422
    r = await alice.patch(f"/users/{bob_id}", json={"local_password": "notfall-passwort-1"})
    assert r.json()["has_local_password"] is True

    # LDAP works: the emergency password is not accepted
    client = await make_client()
    login = await client.post(
        "/auth/login", json={"username": "bob", "password": "notfall-passwort-1"}
    )
    assert login.status_code == 401
    assert USERS["bob"] != "notfall-passwort-1"

    app.state.authenticator = _DirectoryDown()
    wrong = await client.post("/auth/login", json={"username": "bob", "password": "falsch"})
    assert wrong.status_code == 503
    assert "CESMA_LDAP_URL" in wrong.json()["detail"]
    ok = await client.post(
        "/auth/login", json={"username": "bob", "password": "notfall-passwort-1"}
    )
    assert ok.status_code == 200, ok.text
    assert (await client.get("/auth/me")).json()["username"] == "bob"

    await alice.patch(f"/users/{bob_id}", json={"local_password": ""})
    gone = await client.post(
        "/auth/login", json={"username": "bob", "password": "notfall-passwort-1"}
    )
    assert gone.status_code == 503


async def test_tag_single_vlans_on_several_ports(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    settings = await _simulated_app(app, settings)
    device_id = await _polled(alice, app, settings, "hp-2530-48g", "aruba_os_switch")
    p5 = await _port(alice, device_id, "5")
    ports = (await alice.get(f"/devices/{device_id}/ports")).json()
    other = next(
        p
        for p in ports
        if p["kind"] == "ethernet"
        and not p["is_uplink"]
        and 120 not in p["tagged_vlans"]
        and 520 not in p["tagged_vlans"] + p["untagged_vlans"]
    )
    assert 120 in p5["tagged_vlans"]

    plan = (
        await alice.post(
            f"/devices/{device_id}/ports/plan",
            json={"port_ids": [p5["id"], other["id"]], "add_tagged": [520], "remove_tagged": [120]},
        )
    ).json()
    # 520 is added to both ports, 120 only removed where it was; nothing else is touched
    name = other["name"]
    assert plan["commands"] == [
        'POST /vlans-ports {"vlan_id": 520, "port_id": "5", "port_mode": "POM_TAGGED_STATIC"}',
        "DELETE /vlans-ports/120-5",
        f'POST /vlans-ports {{"vlan_id": 520, "port_id": "{name}", '
        '"port_mode": "POM_TAGGED_STATIC"}',
    ]
