from fastapi import APIRouter, Depends, status

from app.api.deps import CallerDep, Db, csrf_guard
from app.models import DeviceStatus
from app.schemas import DeviceIn, DeviceOut, DeviceUpdate
from app.services import devices

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(csrf_guard)])


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: Db,
    caller: CallerDep,
    site_id: int | None = None,
    status: DeviceStatus | None = None,
    search: str | None = None,
) -> object:
    return await devices.list_devices(db, caller, site_id=site_id, status=status, search=search)


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceIn, db: Db, caller: CallerDep) -> object:
    return await devices.create_device(db, caller, body.model_dump())


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, db: Db, caller: CallerDep) -> object:
    return await devices.get_device(db, caller, device_id)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(device_id: int, body: DeviceUpdate, db: Db, caller: CallerDep) -> object:
    return await devices.update_device(db, caller, device_id, body.model_dump(exclude_unset=True))


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, db: Db, caller: CallerDep) -> None:
    await devices.delete_device(db, caller, device_id)
