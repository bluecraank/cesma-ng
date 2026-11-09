from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CallerDep, Db, csrf_guard
from app.schemas import NotificationOut
from app.services import events

router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(csrf_guard)]
)


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    db: Db,
    caller: CallerDep,
    site_id: int | None = None,
    include_acknowledged: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> object:
    return await events.list_notifications(
        db, caller, site_id=site_id, include_acknowledged=include_acknowledged, limit=limit
    )


@router.get("/count")
async def count(db: Db, caller: CallerDep, site_id: int | None = None) -> dict[str, int]:
    return {"open": await events.count_open(db, caller, site_id)}


@router.post("/{notification_id}/acknowledge", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge(notification_id: int, db: Db, caller: CallerDep) -> None:
    await events.acknowledge(db, caller, notification_id)


@router.post("/acknowledge-all", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_all(site_id: int, db: Db, caller: CallerDep) -> None:
    await events.acknowledge_all(db, caller, site_id)
