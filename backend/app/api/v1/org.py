from fastapi import APIRouter, Depends, status

from app.api.deps import CallerDep, Db, csrf_guard
from app.schemas import BuildingOut, NameIn, RoomOut, SiteOut
from app.services import org

router = APIRouter(tags=["organisation"], dependencies=[Depends(csrf_guard)])


@router.get("/sites", response_model=list[SiteOut])
async def list_sites(db: Db, caller: CallerDep) -> object:
    return await org.list_sites(db, caller)


@router.post("/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
async def create_site(body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.create_site(db, caller, body.name)


@router.get("/sites/{site_id}", response_model=SiteOut)
async def get_site(site_id: int, db: Db, caller: CallerDep) -> object:
    return await org.get_site(db, caller, site_id)


@router.patch("/sites/{site_id}", response_model=SiteOut)
async def rename_site(site_id: int, body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.rename_site(db, caller, site_id, body.name)


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(site_id: int, db: Db, caller: CallerDep) -> None:
    await org.delete_site(db, caller, site_id)


@router.post(
    "/sites/{site_id}/buildings", response_model=BuildingOut, status_code=status.HTTP_201_CREATED
)
async def create_building(site_id: int, body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.create_building(db, caller, site_id, body.name)


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
async def rename_building(building_id: int, body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.rename_building(db, caller, building_id, body.name)


@router.delete("/buildings/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_building(building_id: int, db: Db, caller: CallerDep) -> None:
    await org.delete_building(db, caller, building_id)


@router.post(
    "/buildings/{building_id}/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED
)
async def create_room(building_id: int, body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.create_room(db, caller, building_id, body.name)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def rename_room(room_id: int, body: NameIn, db: Db, caller: CallerDep) -> object:
    return await org.rename_room(db, caller, room_id, body.name)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: int, db: Db, caller: CallerDep) -> None:
    await org.delete_room(db, caller, room_id)
