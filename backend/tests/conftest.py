from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.authenticators import StaticAuthenticator
from app.core.config import AuthBackend, Environment, Settings
from app.core.db import Base
from app.main import create_app
from app.services.users import ensure_builtin_roles

USERS = {"alice": "pw-alice", "bob": "pw-bob", "carol": "pw-carol"}
HEADERS = {"X-Requested-With": "cesma"}

#: Anonymised switch recordings. They stay local and are not part of the repository, so tests
#: that need one are skipped where it is missing (e.g. in CI).
RECORDINGS = Path(__file__).parent / "fixtures" / "snmp"


def recording(name: str) -> Path:
    """Path of the recording ``<name>.snmprec``; skips the calling test if it is not there."""
    path = RECORDINGS / f"{name}.snmprec"
    if not path.is_file():
        pytest.skip(f"recording {path.name} not available (kept locally, not in the repository)")
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        secret_key="test-secret",  # type: ignore[arg-type]
        auth_backend=AuthBackend.DEV,
        cookie_secure=False,
    )


@pytest.fixture
async def app(settings: Settings):  # type: ignore[no-untyped-def]
    application = create_app(settings, StaticAuthenticator(USERS))
    async with application.state.database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with application.state.database.sessionmaker() as session:
        await ensure_builtin_roles(session)
        await session.commit()
    yield application
    await application.state.database.dispose()


@pytest.fixture
async def make_client(app):  # type: ignore[no-untyped-def]
    clients: list[AsyncClient] = []

    async def factory(username: str | None = None) -> AsyncClient:
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test/api/v1", headers=HEADERS
        )
        clients.append(client)
        if username:
            r = await client.post(
                "/auth/login", json={"username": username, "password": USERS[username]}
            )
            assert r.status_code == 200, r.text
        return client

    yield factory
    for client in clients:
        await client.aclose()


@pytest.fixture
async def alice(make_client) -> AsyncClient:  # type: ignore[no-untyped-def]
    """First user to log in, therefore super administrator."""
    return await make_client("alice")  # type: ignore[no-any-return]


@pytest.fixture
async def bob(alice, make_client) -> AsyncClient:  # type: ignore[no-untyped-def]
    """Regular user (logs in after alice)."""
    return await make_client("bob")  # type: ignore[no-any-return]


async def user_id(admin: AsyncClient, username: str) -> int:
    users = (await admin.get("/users")).json()
    return next(u["id"] for u in users if u["username"] == username)


async def role_id(admin: AsyncClient, role: str) -> int:
    """Id of a built-in ("viewer", "admin") or custom role (by name)."""
    roles = (await admin.get("/roles")).json()
    return next(r["id"] for r in roles if role in (r["builtin"], r["name"]))


async def grant(admin: AsyncClient, username: str, roles: dict[int, str]) -> None:
    uid = await user_id(admin, username)
    ids = {str(site): await role_id(admin, role) for site, role in roles.items()}
    r = await admin.patch(f"/users/{uid}", json={"site_roles": ids})
    assert r.status_code == 200, r.text
