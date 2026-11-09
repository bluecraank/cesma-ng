import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AppSettings,
    CurrentUser,
    Db,
    client_ip,
    csrf_guard,
    get_authenticator,
    get_session_service,
)
from app.auth.authenticators import AuthBackendError, Authenticator
from app.auth.sessions import SessionService
from app.core.config import Settings
from app.models import AuditLevel, User
from app.schemas import LocaleUpdate, LoginRequest, UserOut
from app.services import audit, users
from app.services.audit import Actor

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(csrf_guard)])

Sessions = Annotated[SessionService, Depends(get_session_service)]


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: AppSettings,
    sessions: Sessions,
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
) -> object:
    ip = client_ip(request)
    try:
        identity = await authenticator.authenticate(body.username, body.password)
    except AuthBackendError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Directory not reachable") from exc

    if identity is None:
        await audit.record(
            db,
            Actor(None, body.username, ip),
            "auth.login_failed",
            "Login failed",
            level=AuditLevel.WARNING,
        )
        await db.commit()  # keep the audit entry although the request fails
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    user = await users.provision_on_login(db, identity)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is disabled")

    await _start_session(db, response, settings, sessions, user, ip, "Login")
    return user


async def _start_session(
    db: AsyncSession,
    response: Response,
    settings: Settings,
    sessions: SessionService,
    user: User,
    ip: str | None,
    message: str,
) -> None:
    token = await sessions.create(user, ip)
    await audit.record(db, Actor.of(user, ip), "auth.login", message)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def sso_peer(request: Request) -> str | None:
    """Address that connected to the reverse proxy: last X-Forwarded-For entry, else the peer."""
    forwarded = [
        a.strip() for a in request.headers.get("x-forwarded-for", "").split(",") if a.strip()
    ]
    return forwarded[-1] if forwarded else client_ip(request)


def is_trusted(address: str | None, trusted: list[str]) -> bool:
    if address is None:
        return False
    try:
        ip = ipaddress.ip_address(address)
        return any(ip in ipaddress.ip_network(net, strict=False) for net in trusted)
    except ValueError:
        return False


def sso_username(raw: str, strip_domain: bool) -> str:
    name = raw.strip()
    if strip_domain:
        name = name.split("\\")[-1].split("@")[0]
    return name


@router.post("/sso", response_model=UserOut)
async def sso_login(
    request: Request,
    response: Response,
    db: Db,
    settings: AppSettings,
    sessions: Sessions,
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
) -> object:
    """Log in with the user name a trusted reverse proxy (e.g. Authentik) put into a header."""
    if not settings.sso_header:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SSO is not enabled")
    peer = sso_peer(request)
    raw = request.headers.get(settings.sso_header)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No SSO user")
    if not is_trusted(peer, settings.sso_trusted_proxies):
        await audit.record(
            db,
            Actor(None, raw, client_ip(request)),
            "auth.sso_rejected",
            f"SSO header from untrusted address {peer}",
            level=AuditLevel.WARNING,
        )
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SSO header from an untrusted address")
    try:
        identity = await authenticator.lookup(sso_username(raw, settings.sso_strip_domain))
    except AuthBackendError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Directory not reachable") from exc
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not allowed")
    user = await users.provision_on_login(db, identity)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is disabled")
    await _start_session(db, response, settings, sessions, user, client_ip(request), "Login (SSO)")
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, settings: AppSettings, sessions: Sessions
) -> None:
    if token := request.cookies.get(settings.session_cookie_name):
        await sessions.revoke(token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> object:
    return user


@router.put("/me/locale", status_code=status.HTTP_204_NO_CONTENT)
async def set_locale(body: LocaleUpdate, user: CurrentUser, db: Db) -> None:
    await users.set_locale(db, user, body.locale)
