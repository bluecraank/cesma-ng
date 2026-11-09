"""Turns what the poller noticed into notifications."""

from collections.abc import Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.errors import NotFoundError
from app.models import Device, Port
from app.models.notification import Notification, NotificationKind, NotificationSeverity
from app.services.access import require_site_access, visible_site_ids
from app.services.context import Caller
from app.services.inventory import InventoryChanges
from app.services.uplinks import uplink_port_ids

Kind = NotificationKind
Severity = NotificationSeverity


def notify(
    db: AsyncSession,
    device: Device,
    kind: NotificationKind,
    severity: NotificationSeverity,
    message: str,
    port_name: str | None = None,
) -> None:
    db.add(
        Notification(
            kind=kind,
            severity=severity,
            site_id=device.site_id,
            device_id=device.id,
            port_name=port_name,
            message=message,
        )
    )


async def uplink_port_names(db: AsyncSession, device_id: int) -> set[str]:
    ids = await uplink_port_ids(db, device_id)
    rows = await db.execute(select(Port.name).where(Port.id.in_(ids)))
    return set(rows.scalars())


async def port_changes(db: AsyncSession, device: Device, changes: InventoryChanges) -> None:
    if changes.rebooted:
        notify(db, device, Kind.DEVICE_REBOOTED, Severity.WARNING, f"{device.name} was restarted")
    if not (changes.links_up or changes.links_down or changes.speed_changed):
        return
    uplinks = await uplink_port_names(db, device.id)
    for name in changes.links_down:
        if name in uplinks:
            notify(db, device, Kind.UPLINK_DOWN, Severity.CRITICAL, f"Uplink {name} down", name)
    for name in changes.links_up:
        if name in uplinks:
            notify(db, device, Kind.UPLINK_UP, Severity.INFO, f"Uplink {name} up", name)
    for name, old, new in changes.speed_changed:
        if name in uplinks:
            notify(
                db,
                device,
                Kind.SPEED_CHANGED,
                Severity.WARNING,
                f"Uplink {name}: {old or '?'} → {new or '?'} Mbit/s",
                name,
            )


# --- Reading / acknowledging -----------------------------------------------------------------


async def list_notifications(
    db: AsyncSession, caller: Caller, *, site_id: int | None, include_acknowledged: bool, limit: int
) -> Sequence[Notification]:
    stmt = select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc())
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Notification.site_id.in_(ids))
    if site_id is not None:
        stmt = stmt.where(Notification.site_id == site_id)
    if not include_acknowledged:
        stmt = stmt.where(Notification.acknowledged_at.is_(None))
    return (await db.execute(stmt.limit(limit))).scalars().all()


async def count_open(db: AsyncSession, caller: Caller, site_id: int | None) -> int:
    stmt = (
        select(func.count()).select_from(Notification).where(Notification.acknowledged_at.is_(None))
    )
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Notification.site_id.in_(ids))
    if site_id is not None:
        stmt = stmt.where(Notification.site_id == site_id)
    return await db.scalar(stmt) or 0


async def acknowledge(db: AsyncSession, caller: Caller, notification_id: int) -> None:
    n = await db.get(Notification, notification_id)
    if n is None:
        raise NotFoundError("Notification not found")
    if n.site_id is not None:
        require_site_access(caller.user, n.site_id)
    n.acknowledged_at = utcnow()
    n.acknowledged_by = caller.user.username


async def acknowledge_all(db: AsyncSession, caller: Caller, site_id: int) -> None:
    require_site_access(caller.user, site_id)
    await db.execute(
        update(Notification)
        .where(and_(Notification.site_id == site_id, Notification.acknowledged_at.is_(None)))
        .values(acknowledged_at=utcnow(), acknowledged_by=caller.user.username)
    )
