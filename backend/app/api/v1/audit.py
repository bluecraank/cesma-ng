from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CallerDep, Db
from app.models import AuditLevel
from app.schemas import AuditEntryOut, Page
from app.services.audit_query import AuditFilter, list_entries

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditEntryOut])
async def list_audit(
    db: Db,
    caller: CallerDep,
    site_id: int | None = None,
    device_id: int | None = None,
    level: AuditLevel | None = None,
    action: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> object:
    items, total = await list_entries(
        db,
        caller,
        AuditFilter(site_id, device_id, level, action, search, limit, offset),
    )
    return {"items": items, "total": total}
