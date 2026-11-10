"""Key figures of a site for the dashboard (one request instead of many)."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.domain.switch import PoeStatus, PortKind
from app.models import (
    Backup,
    BackupStatus,
    Client,
    Device,
    Notification,
    Port,
    PortEvent,
    PortEventKind,
    SiteVlan,
)
from app.services.access import require_site_access
from app.services.clients import ACTIVE_WINDOW
from app.services.context import Caller
from app.services.reports import BACKUP_STALE_AFTER, UNUSED_AFTER_DAYS
from app.services.uplinks import uplink_port_ids


async def site_overview(db: AsyncSession, caller: Caller, site_id: int) -> dict[str, Any]:
    require_site_access(caller.user, site_id)
    now = utcnow()
    day_ago = now - timedelta(days=1)
    device_ids = list(
        (await db.execute(select(Device.id).where(Device.site_id == site_id))).scalars()
    )

    ports = (
        (
            await db.execute(
                select(Port).where(Port.device_id.in_(device_ids), Port.kind == PortKind.ETHERNET)
            )
        )
        .scalars()
        .all()
        if device_ids
        else []
    )
    uplinks = await uplink_port_ids(db)
    unused_since = now - timedelta(days=UNUSED_AFTER_DAYS)
    access = [p for p in ports if p.id not in uplinks]
    free = sum(
        1
        for p in access
        if not p.oper_up
        and p.admin_up
        and (p.last_change_at is None or ensure_utc(p.last_change_at) < unused_since)
    )
    poe = [p for p in ports if p.poe is not None]

    async def count(stmt: Any) -> int:
        return int((await db.execute(stmt)).scalar_one())

    last_ok = (
        dict(
            (
                await db.execute(
                    select(Backup.device_id, func.max(Backup.created_at))
                    .where(Backup.status == BackupStatus.OK, Backup.device_id.in_(device_ids))
                    .group_by(Backup.device_id)
                )
            )
            .tuples()
            .all()
        )
        if device_ids
        else {}
    )
    stale_before = now - BACKUP_STALE_AFTER

    return {
        "ports": {
            "total": len(ports),
            "up": sum(1 for p in ports if p.oper_up),
            "free": free,
            "uplinks": sum(1 for p in ports if p.id in uplinks),
            "uplinks_down": sum(
                1 for p in ports if p.id in uplinks and p.admin_up and not p.oper_up
            ),
        },
        "poe": {
            "ports": len(poe),
            "delivering": sum(1 for p in poe if p.poe is PoeStatus.DELIVERING),
            "faults": sum(1 for p in poe if p.poe is PoeStatus.FAULT),
        },
        "clients_active": await count(
            select(func.count(Client.id)).where(
                Client.site_id == site_id, Client.last_seen_at >= now - ACTIVE_WINDOW
            )
        ),
        "vlans": await count(select(func.count(SiteVlan.id)).where(SiteVlan.site_id == site_id)),
        "notifications_open": await count(
            select(func.count(Notification.id)).where(
                Notification.site_id == site_id, Notification.acknowledged_at.is_(None)
            )
        ),
        "link_changes_24h": await count(
            select(func.count(PortEvent.id))
            .join(Port, Port.id == PortEvent.port_id)
            .where(
                Port.device_id.in_(device_ids),
                PortEvent.kind.in_([PortEventKind.LINK_UP, PortEventKind.LINK_DOWN]),
                PortEvent.at >= day_ago,
            )
        )
        if device_ids
        else 0,
        "backups": {
            "ok_24h": await count(
                select(func.count(Backup.id)).where(
                    Backup.device_id.in_(device_ids),
                    Backup.status == BackupStatus.OK,
                    Backup.created_at >= day_ago,
                )
            )
            if device_ids
            else 0,
            "failed_24h": await count(
                select(func.count(Backup.id)).where(
                    Backup.device_id.in_(device_ids),
                    Backup.status == BackupStatus.FAILED,
                    Backup.created_at >= day_ago,
                )
            )
            if device_ids
            else 0,
            "stale": sum(
                1
                for d in device_ids
                if last_ok.get(d) is None or ensure_utc(last_ok[d]) < stale_before
            ),
        },
    }
