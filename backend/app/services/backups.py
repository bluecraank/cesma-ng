"""Configuration backups: take, keep, compare, download, report by mail."""

import asyncio
import difflib
import hashlib
import logging
import smtplib
from collections.abc import Sequence
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import utcnow
from app.core.errors import NotFoundError
from app.drivers.writers import WriteError
from app.models import AuditLevel, Backup, BackupStatus, Device, DeviceStatus, SiteRole
from app.services import audit, events
from app.services.access import visible_site_ids
from app.services.audit import Actor
from app.services.context import Caller, Runtime
from app.services.device_access import device_writer
from app.services.devices import get_device

log = logging.getLogger(__name__)

BACKUP_TIMEOUT = 300
KEEP_NEWEST = 5


async def run_backup(db: AsyncSession, runtime: Runtime, device: Device, actor: Actor) -> Backup:
    writer = await device_writer(db, runtime, device)
    try:
        async with asyncio.timeout(BACKUP_TIMEOUT):
            config = await writer.running_config()
        if not config.strip():
            raise WriteError("empty configuration returned")
    except (WriteError, TimeoutError) as exc:
        message = str(exc) or "timeout"
        backup = Backup(
            device_id=device.id,
            status=BackupStatus.FAILED,
            error=message,
            created_by=actor.name,
            changed=False,
        )
        db.add(backup)
        events.notify(
            db,
            device,
            events.Kind.BACKUP_FAILED,
            events.Severity.WARNING,
            f"Backup of {device.name} failed: {message}",
        )
        await audit.record(
            db,
            actor,
            "backup.failed",
            f"Backup of {device.name} failed: {message}",
            level=AuditLevel.WARNING,
            site_id=device.site_id,
            device_id=device.id,
        )
        await db.flush()
        return backup

    digest = hashlib.sha256(config.encode()).hexdigest()
    previous = await db.scalar(
        select(Backup.sha256)
        .where(Backup.device_id == device.id, Backup.status == BackupStatus.OK)
        .order_by(Backup.created_at.desc(), Backup.id.desc())
        .limit(1)
    )
    backup = Backup(
        device_id=device.id,
        status=BackupStatus.OK,
        config_encrypted=runtime.box.encrypt(config),
        sha256=digest,
        size=len(config.encode()),
        changed=previous != digest,
        created_by=actor.name,
    )
    db.add(backup)
    await db.flush()
    return backup


async def backup_all(db: AsyncSession, runtime: Runtime) -> tuple[int, int]:
    devices = (
        (await db.execute(select(Device).where(Device.status != DeviceStatus.UNCONFIRMED)))
        .scalars()
        .all()
    )
    ok = failed = 0
    for device in devices:
        backup = await run_backup(db, runtime, device, Actor.system())
        await db.commit()
        if backup.status is BackupStatus.OK:
            ok += 1
        else:
            failed += 1
    log.info("Backups: %d ok, %d failed", ok, failed)
    return ok, failed


async def purge_old_backups(db: AsyncSession, days: int) -> None:
    """Delete backups older than ``days``, but always keep the newest ones of every device."""
    cutoff = utcnow() - timedelta(days=days)
    ranked = (
        select(
            Backup.id,
            func.row_number()
            .over(
                partition_by=Backup.device_id, order_by=(Backup.created_at.desc(), Backup.id.desc())
            )
            .label("rank"),
            Backup.created_at,
        )
    ).subquery()
    doomed = select(ranked.c.id).where(ranked.c.rank > KEEP_NEWEST, ranked.c.created_at < cutoff)
    await db.execute(delete(Backup).where(Backup.id.in_(doomed)))


# --- Reading ---------------------------------------------------------------------------------


async def list_backups(
    db: AsyncSession,
    caller: Caller,
    *,
    device_id: int | None = None,
    site_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = select(Backup, Device.name, Device.site_id).join(Device, Device.id == Backup.device_id)
    if device_id is not None:
        await get_device(db, caller, device_id)
        stmt = stmt.where(Backup.device_id == device_id)
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Device.site_id.in_(ids))
    if site_id is not None:
        stmt = stmt.where(Device.site_id == site_id)
    rows = await db.execute(stmt.order_by(Backup.created_at.desc(), Backup.id.desc()).limit(limit))
    return [
        {
            "id": b.id,
            "device_id": b.device_id,
            "device_name": name,
            "site_id": sid,
            "created_at": b.created_at,
            "status": b.status,
            "sha256": b.sha256,
            "size": b.size,
            "changed": b.changed,
            "error": b.error,
            "created_by": b.created_by,
        }
        for b, name, sid in rows.tuples()
    ]


async def backup_config(
    db: AsyncSession, caller: Caller, runtime: Runtime, backup_id: int
) -> tuple[Backup, Device, str]:
    """The configuration text. Admins only: it contains secrets of the switch."""
    backup = await db.get(Backup, backup_id)
    if backup is None or backup.config_encrypted is None:
        raise NotFoundError("Backup not found")
    device = await get_device(db, caller, backup.device_id, SiteRole.ADMIN)
    return backup, device, runtime.box.decrypt(backup.config_encrypted)


async def diff_backups(
    db: AsyncSession, caller: Caller, runtime: Runtime, old_id: int, new_id: int
) -> str:
    old, device_old, old_text = await backup_config(db, caller, runtime, old_id)
    new, device_new, new_text = await backup_config(db, caller, runtime, new_id)
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{device_old.name} {old.created_at:%Y-%m-%d %H:%M}",
            tofile=f"{device_new.name} {new.created_at:%Y-%m-%d %H:%M}",
        )
    )


# --- Weekly mail -----------------------------------------------------------------------------


async def weekly_report(db: AsyncSession) -> list[tuple[str, int, int, str | None]]:
    """(device, ok backups, failed backups, last error) for the last 7 days."""
    since = utcnow() - timedelta(days=7)
    devices = (await db.execute(select(Device).order_by(Device.name))).scalars().all()
    report = []
    for device in devices:
        rows: Sequence[Backup] = (
            (
                await db.execute(
                    select(Backup)
                    .where(Backup.device_id == device.id, Backup.created_at >= since)
                    .order_by(Backup.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        ok = sum(b.status is BackupStatus.OK for b in rows)
        failed = len(rows) - ok
        error = next((b.error for b in rows if b.status is BackupStatus.FAILED), None)
        report.append((device.name, ok, failed, error))
    return report


def render_report(report: Sequence[tuple[str, int, int, str | None]]) -> str:
    lines = ["cesma-ng: Backups der letzten 7 Tage", ""]
    for name, ok, failed, error in report:
        state = "OK" if ok and not failed else ("FEHLER" if not ok else "teilweise")
        lines.append(
            f"{state:10} {name:30} {ok} ok, {failed} fehlgeschlagen"
            + (f" ({error})" if error else "")
        )
    return "\n".join(lines) + "\n"


async def send_weekly_mail(db: AsyncSession, settings: Settings) -> bool:
    if not (settings.smtp_host and settings.backup_mail_to):
        return False
    body = render_report(await weekly_report(db))
    message = EmailMessage()
    message["Subject"] = "cesma-ng Backup-Bericht"
    message["From"] = settings.mail_from
    message["To"] = settings.backup_mail_to
    message.set_content(body)

    def send() -> None:
        with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    await asyncio.to_thread(send)
    return True
