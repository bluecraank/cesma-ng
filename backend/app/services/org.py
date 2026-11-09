"""Sites, buildings and rooms."""

from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models import Building, Device, Room, Site, SiteRole
from app.services import audit
from app.services.access import require_site_role, require_superadmin, visible_site_ids
from app.services.context import Caller

# --- Sites -----------------------------------------------------------------------------------


async def list_sites(db: AsyncSession, caller: Caller) -> Sequence[Site]:
    """Sites visible to the caller, with buildings and rooms."""
    stmt = (
        select(Site)
        .options(selectinload(Site.buildings).selectinload(Building.rooms))
        .order_by(Site.name)
    )
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Site.id.in_(ids))
    return (await db.execute(stmt)).scalars().all()


async def get_site(db: AsyncSession, caller: Caller, site_id: int) -> Site:
    require_site_role(caller.user, site_id, SiteRole.VIEWER)
    site = await db.get(
        Site, site_id, options=[selectinload(Site.buildings).selectinload(Building.rooms)]
    )
    if site is None:
        raise NotFoundError("Site not found")
    return site


async def create_site(db: AsyncSession, caller: Caller, name: str) -> Site:
    require_superadmin(caller.user)
    site = Site(name=name, buildings=[])
    db.add(site)
    await _flush_unique(db, f"Site '{name}' already exists")
    await audit.record(db, caller.actor, "site.create", f"Site {name} created", site_id=site.id)
    return site


async def rename_site(db: AsyncSession, caller: Caller, site_id: int, name: str) -> Site:
    site = await get_site(db, caller, site_id)
    require_site_role(caller.user, site_id, SiteRole.ADMIN)
    old = site.name
    site.name = name
    await _flush_unique(db, f"Site '{name}' already exists")
    await audit.record(
        db,
        caller.actor,
        "site.update",
        f"Site renamed to {name}",
        site_id=site.id,
        old={"name": old},
        new={"name": name},
    )
    return site


async def delete_site(db: AsyncSession, caller: Caller, site_id: int) -> None:
    require_superadmin(caller.user)
    site = await get_site(db, caller, site_id)
    if await db.scalar(select(exists().where(Device.site_id == site_id))):
        raise ConflictError("Site still has devices")
    await db.delete(site)
    await audit.record(db, caller.actor, "site.delete", f"Site {site.name} deleted")


# --- Buildings -------------------------------------------------------------------------------


async def create_building(db: AsyncSession, caller: Caller, site_id: int, name: str) -> Building:
    await get_site(db, caller, site_id)
    require_site_role(caller.user, site_id, SiteRole.ADMIN)
    building = Building(site_id=site_id, name=name, rooms=[])
    db.add(building)
    await _flush_unique(db, f"Building '{name}' already exists")
    await audit.record(
        db, caller.actor, "building.create", f"Building {name} created", site_id=site_id
    )
    return building


async def _get_building(db: AsyncSession, caller: Caller, building_id: int) -> Building:
    building = await db.get(Building, building_id, options=[selectinload(Building.rooms)])
    if building is None:
        raise NotFoundError("Building not found")
    require_site_role(caller.user, building.site_id, SiteRole.ADMIN)
    return building


async def rename_building(
    db: AsyncSession, caller: Caller, building_id: int, name: str
) -> Building:
    building = await _get_building(db, caller, building_id)
    old = building.name
    building.name = name
    await _flush_unique(db, f"Building '{name}' already exists")
    await audit.record(
        db,
        caller.actor,
        "building.update",
        f"Building renamed to {name}",
        site_id=building.site_id,
        old={"name": old},
        new={"name": name},
    )
    return building


async def delete_building(db: AsyncSession, caller: Caller, building_id: int) -> None:
    building = await _get_building(db, caller, building_id)
    await db.delete(building)
    await audit.record(
        db,
        caller.actor,
        "building.delete",
        f"Building {building.name} deleted",
        site_id=building.site_id,
    )


# --- Rooms -----------------------------------------------------------------------------------


async def create_room(db: AsyncSession, caller: Caller, building_id: int, name: str) -> Room:
    building = await _get_building(db, caller, building_id)
    room = Room(building_id=building.id, name=name)
    db.add(room)
    await _flush_unique(db, f"Room '{name}' already exists")
    await audit.record(
        db, caller.actor, "room.create", f"Room {name} created", site_id=building.site_id
    )
    return room


async def _get_room(db: AsyncSession, caller: Caller, room_id: int) -> tuple[Room, int]:
    row = (
        await db.execute(select(Room, Building.site_id).join(Building).where(Room.id == room_id))
    ).one_or_none()
    if row is None:
        raise NotFoundError("Room not found")
    room, site_id = row
    require_site_role(caller.user, site_id, SiteRole.ADMIN)
    return room, site_id


async def rename_room(db: AsyncSession, caller: Caller, room_id: int, name: str) -> Room:
    room, site_id = await _get_room(db, caller, room_id)
    old = room.name
    room.name = name
    await _flush_unique(db, f"Room '{name}' already exists")
    await audit.record(
        db,
        caller.actor,
        "room.update",
        f"Room renamed to {name}",
        site_id=site_id,
        old={"name": old},
        new={"name": name},
    )
    return room


async def delete_room(db: AsyncSession, caller: Caller, room_id: int) -> None:
    room, site_id = await _get_room(db, caller, room_id)
    await db.delete(room)
    await audit.record(
        db, caller.actor, "room.delete", f"Room {room.name} deleted", site_id=site_id
    )


async def room_site_id(db: AsyncSession, room_id: int) -> int:
    site_id = await db.scalar(select(Building.site_id).join(Room).where(Room.id == room_id))
    if site_id is None:
        raise NotFoundError("Room not found")
    return site_id


async def _flush_unique(db: AsyncSession, message: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(message) from exc
