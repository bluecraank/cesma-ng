from httpx import AsyncClient
from sqlalchemy import select

from app.models import CredentialProfile
from app.services.credentials import to_device_credentials


async def test_secrets_are_never_returned(alice: AsyncClient) -> None:
    r = await alice.post(
        "/credential-profiles",
        json={
            "name": "default",
            "api_username": "admin",
            "api_password": "s3cret",
            "snmp_community": "private",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "s3cret" not in r.text and "private" not in r.text
    assert body["secrets_set"] == ["api_password", "snmp_community"]


async def test_omitted_secrets_are_kept_empty_ones_cleared(alice: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    pid = (
        await alice.post(
            "/credential-profiles",
            json={"name": "p", "api_password": "a", "ssh_password": "b"},
        )
    ).json()["id"]
    r = await alice.put(f"/credential-profiles/{pid}", json={"name": "p", "ssh_password": ""})
    assert r.json()["secrets_set"] == ["api_password"]

    async with app.state.database.sessionmaker() as db:
        profile = (await db.execute(select(CredentialProfile))).scalar_one()
        creds = to_device_credentials(profile, app.state.secret_box)
    assert creds.api.password == "a"
    assert "api_password" not in profile.secrets_encrypted  # stored encrypted


async def test_cesma_gets_its_own_rsa_key(alice: AsyncClient, bob: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    pid = (await alice.post("/credential-profiles", json={"name": "dell"})).json()["id"]
    assert (await bob.post(f"/credential-profiles/{pid}/ssh-key")).status_code == 403
    r = await alice.post(f"/credential-profiles/{pid}/ssh-key")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ssh_public_key"].startswith("ssh-rsa ") and "PRIVATE" not in r.text
    assert body["secrets_set"] == ["ssh_private_key"]
    # the private key is used for Cesma's own SSH logins
    async with app.state.database.sessionmaker() as db:
        profile = (await db.execute(select(CredentialProfile))).scalar_one()
        creds = to_device_credentials(profile, app.state.secret_box)
    assert creds.ssh.private_key and "OPENSSH PRIVATE KEY" in creds.ssh.private_key
    listed = (await alice.get("/credential-profiles")).json()[0]
    assert listed["ssh_public_key"] == body["ssh_public_key"]


async def test_only_superadmin_manages_credentials(bob: AsyncClient) -> None:
    assert (await bob.get("/credential-profiles")).status_code == 403


async def test_device_hints_name_missing_credentials(alice: AsyncClient) -> None:
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    profile = (
        await alice.post(
            "/credential-profiles",
            json={"name": "nur SNMP", "snmp_community": "geheim"},
        )
    ).json()["id"]

    async def add(name: str, model: str, profile_id: int | None) -> int:
        body = {"name": name, "hostname": name, "model": model, "site_id": site}
        if profile_id:
            body["credential_profile_id"] = profile_id
        return int((await alice.post("/devices", json=body)).json()["id"])

    bare = await add("sw-a", "dell_n1500", None)
    dell = await add("sw-b", "dell_n1500", profile)
    hp = await add("sw-c", "aruba_os_switch", profile)
    hints = {
        (h["device_id"], h["code"]) for h in (await alice.get(f"/sites/{site}/device-hints")).json()
    }
    assert hints == {(bare, "no_profile"), (dell, "no_ssh_login"), (hp, "no_api_login")}
