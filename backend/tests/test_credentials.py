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


async def test_only_superadmin_manages_credentials(bob: AsyncClient) -> None:
    assert (await bob.get("/credential-profiles")).status_code == 403
