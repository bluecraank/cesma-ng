"""Housekeeping: delete data older than its retention period."""

import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionService
from app.core.config import Settings
from app.core.db import utcnow
from app.models import AuditEntry, Notification

log = logging.getLogger(__name__)


async def cleanup(db: AsyncSession, settings: Settings) -> None:
    now = utcnow()
    audit = await db.execute(
        delete(AuditEntry).where(
            AuditEntry.created_at < now - timedelta(days=settings.retention_audit_days)
        )
    )
    notes = await db.execute(
        delete(Notification).where(
            Notification.created_at < now - timedelta(days=settings.retention_notification_days)
        )
    )
    log.info("Cleanup: %s audit entries, %s notifications removed", audit.rowcount, notes.rowcount)  # type: ignore[attr-defined]


async def purge_sessions(db: AsyncSession) -> None:
    await SessionService(db, timedelta(0)).purge_expired()
