"""Reading the audit log, restricted to what the caller may see."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEntry, AuditLevel
from app.services.access import visible_site_ids
from app.services.context import Caller


@dataclass(frozen=True)
class AuditFilter:
    site_id: int | None = None
    device_id: int | None = None
    level: AuditLevel | None = None
    action_prefix: str | None = None
    search: str | None = None
    limit: int = 100
    offset: int = 0


async def list_entries(
    db: AsyncSession, caller: Caller, flt: AuditFilter
) -> tuple[Sequence[AuditEntry], int]:
    """Entries visible to the caller. Global entries (no site) are for super admins only."""
    stmt = select(AuditEntry)
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(AuditEntry.site_id.in_(ids))
    if flt.site_id is not None:
        stmt = stmt.where(AuditEntry.site_id == flt.site_id)
    if flt.device_id is not None:
        stmt = stmt.where(AuditEntry.device_id == flt.device_id)
    if flt.level is not None:
        stmt = stmt.where(AuditEntry.level == flt.level)
    if flt.action_prefix:
        stmt = stmt.where(AuditEntry.action.startswith(flt.action_prefix))
    if flt.search:
        pattern = f"%{flt.search}%"
        stmt = stmt.where(AuditEntry.message.ilike(pattern) | AuditEntry.actor_name.ilike(pattern))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
        .limit(flt.limit)
        .offset(flt.offset)
    )
    return rows.scalars().all(), total
