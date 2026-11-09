"""Writes audit log entries. Every state-changing service call records one."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEntry, AuditLevel, User

log = logging.getLogger("cesma.audit")


@dataclass(frozen=True)
class Actor:
    """Who triggered an action: a user (with request IP) or the system itself."""

    user_id: int | None
    name: str
    ip_address: str | None = None

    @classmethod
    def system(cls) -> "Actor":
        return cls(user_id=None, name="system")

    @classmethod
    def of(cls, user: User, ip_address: str | None) -> "Actor":
        return cls(user_id=user.id, name=user.username, ip_address=ip_address)


async def record(
    db: AsyncSession,
    actor: Actor,
    action: str,
    message: str = "",
    *,
    level: AuditLevel = AuditLevel.INFO,
    site_id: int | None = None,
    device_id: int | None = None,
    old: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEntry(
            level=level,
            action=action,
            message=message,
            actor_user_id=actor.user_id,
            actor_name=actor.name,
            ip_address=actor.ip_address,
            site_id=site_id,
            device_id=device_id,
            old_values=old,
            new_values=new,
        )
    )
    log.log(
        {AuditLevel.INFO: logging.INFO, AuditLevel.WARNING: logging.WARNING}.get(
            level, logging.ERROR
        ),
        "%s by %s: %s",
        action,
        actor.name,
        message,
    )


def changes(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return only the fields that differ, as (old, new)."""
    keys = [k for k in after if before.get(k) != after[k]]
    return {k: before.get(k) for k in keys}, {k: after[k] for k in keys}
