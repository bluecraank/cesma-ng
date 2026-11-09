"""FastAPI dependencies: DB session, current user, caller context and CSRF guard."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authenticators import Authenticator
from app.auth.sessions import SessionService
from app.core.config import Settings
from app.core.crypto import SecretBox
from app.core.db import Database
from app.models import User
from app.services.context import Caller, Runtime

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "cesma"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_secret_box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secret_box
    return box


def get_authenticator(request: Request) -> Authenticator:
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request: committed on success, rolled back on error."""
    database: Database = request.app.state.database
    async with database.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


Db = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_session_service(db: Db, settings: AppSettings) -> SessionService:
    return SessionService(db, timedelta(hours=settings.session_ttl_hours))


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def csrf_guard(request: Request) -> None:
    """Cookie-authenticated, state-changing requests must carry a custom header.

    Browsers cannot add custom headers to cross-site form posts, and CORS is disabled,
    so this blocks CSRF in addition to the SameSite=Strict cookie.
    """
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header")


async def get_current_user(
    request: Request,
    settings: AppSettings,
    sessions: Annotated[SessionService, Depends(get_session_service)],
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    user = await sessions.resolve(token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_caller(request: Request, user: CurrentUser) -> Caller:
    return Caller(user=user, ip_address=client_ip(request))


CallerDep = Annotated[Caller, Depends(get_caller)]


def get_runtime(request: Request) -> Runtime:
    return Runtime(request.app.state.settings, request.app.state.secret_box)


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
