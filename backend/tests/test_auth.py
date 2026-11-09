from httpx import AsyncClient

from tests.conftest import HEADERS


async def test_first_user_becomes_superadmin(alice: AsyncClient, bob: AsyncClient) -> None:
    assert (await alice.get("/auth/me")).json()["is_superadmin"] is True
    assert (await bob.get("/auth/me")).json()["is_superadmin"] is False


async def test_wrong_password_is_rejected_and_audited(make_client, alice: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    anonymous = await make_client()
    r = await anonymous.post("/auth/login", json={"username": "bob", "password": "wrong"})
    assert r.status_code == 401
    entries = (await alice.get("/audit", params={"action": "auth.login_failed"})).json()
    assert entries["total"] == 1
    assert entries["items"][0]["actor_name"] == "bob"


async def test_requests_without_session_are_unauthorized(make_client) -> None:  # type: ignore[no-untyped-def]
    anonymous = await make_client()
    assert (await anonymous.get("/auth/me")).status_code == 401
    assert (await anonymous.get("/devices")).status_code == 401


async def test_logout_invalidates_session(alice: AsyncClient) -> None:
    assert (await alice.post("/auth/logout")).status_code == 204
    assert (await alice.get("/auth/me")).status_code == 401


async def test_state_changing_requests_need_csrf_header(alice: AsyncClient) -> None:
    r = await alice.post("/sites", json={"name": "HQ"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403
    assert (await alice.post("/sites", json={"name": "HQ"}, headers=HEADERS)).status_code == 201


async def test_locale_can_be_changed(alice: AsyncClient) -> None:
    assert (await alice.put("/auth/me/locale", json={"locale": "en"})).status_code == 204
    assert (await alice.get("/auth/me")).json()["locale"] == "en"
    assert (await alice.put("/auth/me/locale", json={"locale": "xx"})).status_code == 422


async def test_sso_requires_trusted_proxy(app, make_client) -> None:  # type: ignore[no-untyped-def]
    app.state.settings = app.state.settings.model_copy(
        update={"sso_header": "X-Authentik-Username", "sso_trusted_proxies": ["10.0.0.0/24"]}
    )
    client = await make_client()
    # header from an untrusted address (as reported by the reverse proxy) is refused
    untrusted = await client.post(
        "/auth/sso", headers={"X-Authentik-Username": "alice", "X-Forwarded-For": "192.168.1.5"}
    )
    assert untrusted.status_code == 403
    # trusted proxy, DOMAIN\user form, user must exist in the directory
    ok = await client.post(
        "/auth/sso",
        headers={"X-Authentik-Username": r"CORP\alice", "X-Forwarded-For": "1.2.3.4, 10.0.0.7"},
    )
    assert ok.status_code == 200, ok.text
    assert (await client.get("/auth/me")).json()["username"] == "alice"
    unknown = await client.post(
        "/auth/sso", headers={"X-Authentik-Username": "mallory", "X-Forwarded-For": "10.0.0.7"}
    )
    assert unknown.status_code == 401


async def test_sso_disabled_by_default(make_client) -> None:  # type: ignore[no-untyped-def]
    client = await make_client()
    assert (
        await client.post("/auth/sso", headers={"X-Authentik-Username": "alice"})
    ).status_code == 404
