"""Server-side login sessions. The cookie holds a random token, the DB only its hash."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.models import User, UserSession


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionService:
    def __init__(self, db: AsyncSession, ttl: timedelta) -> None:
        self._db = db
        self._ttl = ttl

    async def create(self, user: User, ip_address: str | None) -> str:
        token = secrets.token_urlsafe(32)
        self._db.add(
            UserSession(
                token_hash=_hash(token),
                user_id=user.id,
                expires_at=utcnow() + self._ttl,
                ip_address=ip_address,
            )
        )
        await self._db.flush()
        return token

    async def resolve(self, token: str) -> User | None:
        result = await self._db.execute(
            select(UserSession).where(UserSession.token_hash == _hash(token))
        )
        session = result.scalar_one_or_none()
        if session is None or ensure_utc(session.expires_at) < utcnow():
            return None  # expired rows are removed by purge_expired()
        return session.user if session.user.is_active else None

    async def revoke(self, token: str) -> None:
        await self._db.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))

    async def revoke_all_for(self, user_id: int) -> None:
        await self._db.execute(delete(UserSession).where(UserSession.user_id == user_id))

    async def purge_expired(self) -> None:
        await self._db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
