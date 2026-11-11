"""Background jobs: queued by the API, executed one at a time by the worker."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.errors import ForbiddenError, NotFoundError, ValidationFailedError
from app.drivers.writers import WriteError
from app.models import (
    AuditLevel,
    BackupStatus,
    Device,
    DeviceStatus,
    Job,
    JobStatus,
    Permission,
    User,
)
from app.services import audit, backups, discovery, polling, site_config, ssh_keys
from app.services.access import require_permission, require_site_access, visible_site_ids
from app.services.context import Caller, Runtime
from app.services.credentials import public_key_of
from app.services.device_access import device_writer

log = logging.getLogger(__name__)

APPLY_TIMEOUT = 300
MIN_SSH_KEYS = 2

#: job kind -> permission needed on the job's site
JOB_KINDS: dict[str, Permission] = {
    "vlan_sync": Permission.VLANS_MANAGE,
    "backup": Permission.BACKUPS_RUN,
    "ssh_keys": Permission.SSH_KEYS_PUSH,
    "discover": Permission.DEVICES_MANAGE,
    "restore": Permission.BACKUPS_RESTORE,
}


# --- Queue -----------------------------------------------------------------------------------


async def enqueue(
    db: AsyncSession, caller: Caller, kind: str, site_id: int, payload: dict[str, Any]
) -> Job:
    if kind not in JOB_KINDS:
        raise ValidationFailedError(f"Unknown job kind {kind}")
    require_permission(caller.user, site_id, JOB_KINDS[kind])
    if kind == "ssh_keys":
        count = len(await ssh_keys.keys_to_push(db))
        if count < MIN_SSH_KEYS:
            raise ValidationFailedError(
                f"At least {MIN_SSH_KEYS} SSH keys are required, so a single wrong key cannot "
                "lock you out"
            )
    job = Job(
        kind=kind,
        site_id=site_id,
        created_by=caller.user.username,
        payload={**payload, "user_id": caller.user.id},
    )
    db.add(job)
    await db.flush()
    await audit.record(
        db, caller.actor, f"job.{kind}", f"Job {kind} #{job.id} queued", site_id=site_id
    )
    return job


async def list_jobs(
    db: AsyncSession, caller: Caller, site_id: int | None, limit: int = 50
) -> Sequence[Job]:
    stmt = select(Job).order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Job.site_id.in_(ids))
    if site_id is not None:
        stmt = stmt.where(Job.site_id == site_id)
    return (await db.execute(stmt)).scalars().all()


async def get_job(db: AsyncSession, caller: Caller, job_id: int) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    if job.site_id is not None:
        require_site_access(caller.user, job.site_id)
    return job


async def fail_interrupted(db: AsyncSession) -> None:
    """Jobs that were running when the worker stopped will not finish any more."""
    await db.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING)
        .values(
            status=JobStatus.FAILED, error="interrupted (worker restarted)", finished_at=utcnow()
        )
    )


# --- Execution -------------------------------------------------------------------------------


class JobContext:
    def __init__(self, db: AsyncSession, job: Job, caller: Caller, runtime: Runtime) -> None:
        self.db = db
        self.job = job
        self.caller = caller
        self.runtime = runtime

    async def say(self, line: str, progress: int | None = None) -> None:
        self.job.log += f"{utcnow():%H:%M:%S} {line}\n"
        if progress is not None:
            self.job.progress = progress
        await self.db.commit()  # progress is visible in the UI while the job runs


async def next_pending(db: AsyncSession) -> Job | None:
    return await db.scalar(
        select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.created_at, Job.id).limit(1)
    )


async def run_job(db: AsyncSession, job: Job, runtime: Runtime) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()
    await db.commit()
    try:
        user = await db.get(User, job.payload.get("user_id"))
        if user is None or not user.is_active:
            raise ForbiddenError("The user who started the job no longer exists or is disabled")
        caller = Caller(user)
        if job.site_id is not None:
            # permissions may have changed since the job was queued
            require_permission(user, job.site_id, JOB_KINDS[job.kind])
        ctx = JobContext(db, job, caller, runtime)
        await RUNNERS[job.kind](ctx)
        job.status = JobStatus.DONE
    except Exception as exc:  # the job fails, the worker continues
        log.exception("Job %s #%d failed", job.kind, job.id)
        await db.rollback()
        job = await db.get(Job, job.id) or job
        job.status = JobStatus.FAILED
        job.error = str(exc) or exc.__class__.__name__
    job.progress = 100
    job.finished_at = utcnow()
    await db.commit()


async def _devices(ctx: JobContext) -> list[Device]:
    ids = ctx.job.payload.get("device_ids") or []
    stmt = select(Device).where(
        Device.site_id == ctx.job.site_id, Device.status != DeviceStatus.UNCONFIRMED
    )
    if ids:
        stmt = stmt.where(Device.id.in_(ids))
    return list((await ctx.db.execute(stmt.order_by(Device.name))).scalars())


async def _run_vlan_sync(ctx: JobContext) -> None:
    assert ctx.job.site_id is not None
    plans = await site_config.plan_vlan_sync(
        ctx.db,
        ctx.caller,
        ctx.runtime,
        ctx.job.site_id,
        device_ids=ctx.job.payload.get("device_ids"),
        delete_extra=bool(ctx.job.payload.get("delete_extra")),
        tag_uplinks=bool(ctx.job.payload.get("tag_uplinks")),
    )
    failures = 0
    for index, plan in enumerate(plans, 1):
        progress = int(index / max(len(plans), 1) * 100)
        if plan.empty:
            await ctx.say(f"{plan.device_name}: nothing to do", progress)
            continue
        device = await ctx.db.get(Device, plan.device_id)
        assert device is not None
        try:
            writer = await device_writer(ctx.db, ctx.runtime, device)
            async with asyncio.timeout(APPLY_TIMEOUT):
                applied = await writer.apply(plan.operations)
            await audit.record(
                ctx.db,
                ctx.caller.actor,
                "vlan.sync",
                f"{device.name}: {len(plan.operations)} VLAN change(s) applied",
                site_id=device.site_id,
                device_id=device.id,
                new={"commands": applied},
            )
            await polling.request_poll(ctx.db, device.id)
            await ctx.say(f"{device.name}: {len(plan.operations)} change(s) applied", progress)
        except (WriteError, TimeoutError) as exc:
            failures += 1
            await ctx.say(f"{device.name}: FAILED - {exc}", progress)
    if failures:
        raise WriteError(f"{failures} of {len(plans)} switch(es) failed, see log")


async def _run_backup(ctx: JobContext) -> None:
    devices = await _devices(ctx)
    failed = 0
    for index, device in enumerate(devices, 1):
        backup = await backups.run_backup(ctx.db, ctx.runtime, device, ctx.caller.actor)
        state = "ok" if backup.status is BackupStatus.OK else f"FAILED - {backup.error}"
        failed += backup.status is not BackupStatus.OK
        await ctx.say(f"{device.name}: {state}", int(index / max(len(devices), 1) * 100))
    if failed:
        raise WriteError(f"{failed} backup(s) failed, see log")


async def _run_ssh_keys(ctx: JobContext) -> None:
    assert ctx.job.site_id is not None
    keys = [k.key for k in await ssh_keys.keys_to_push(ctx.db)]
    await ctx.say(f"{len(keys)} key(s) from the SSH key list")
    if len(keys) < MIN_SSH_KEYS:
        raise WriteError(f"At least {MIN_SSH_KEYS} SSH keys are required")
    devices = await _devices(ctx)
    failed = 0
    for index, device in enumerate(devices, 1):
        progress = int(index / max(len(devices), 1) * 100)
        writer = await device_writer(ctx.db, ctx.runtime, device)
        if not writer.supports_ssh_keys:
            await ctx.say(f"{device.name}: skipped (not supported for this model)", progress)
            continue
        own_key = public_key_of(writer.credentials.ssh.private_key)
        device_keys = ssh_keys.with_own_key(keys, own_key)
        if len(device_keys) > len(keys) and not writer.ssh_keys_own_only:
            await ctx.say(f"{device.name}: Cesma's own key from the credential profile added")
        try:
            async with asyncio.timeout(APPLY_TIMEOUT):
                uploaded = await writer.push_ssh_keys(device_keys)
            await audit.record(
                ctx.db,
                ctx.caller.actor,
                "ssh_keys.push",
                f"{uploaded} SSH keys uploaded to {device.name}",
                site_id=device.site_id,
                device_id=device.id,
            )
            note = (
                " (Cesma's own key, this model holds one key per user)"
                if (writer.ssh_keys_own_only)
                else ""
            )
            await ctx.say(f"{device.name}: {uploaded} key(s) uploaded{note}", progress)
        except (WriteError, TimeoutError) as exc:
            failed += 1
            await ctx.say(f"{device.name}: FAILED - {exc}", progress)
    if failed:
        raise WriteError(f"{failed} switch(es) failed, see log")


async def _run_discover(ctx: JobContext) -> None:
    assert ctx.job.site_id is not None
    cidr = str(ctx.job.payload.get("cidr") or "")
    await ctx.say(f"Scanning {cidr} ...", 5)
    found = await discovery.discover_range(
        ctx.db, ctx.runtime, cidr, ctx.job.site_id, ctx.job.payload.get("credential_profile_id")
    )
    await ctx.say(f"{found} new switch(es) found", 100)


async def _run_restore(ctx: JobContext) -> None:
    backup_id = int(ctx.job.payload.get("backup_id") or 0)
    backup, device, config = await backups.backup_config(ctx.db, ctx.caller, ctx.runtime, backup_id)
    if device.site_id != ctx.job.site_id:
        raise ForbiddenError("Backup belongs to another site")
    writer = await device_writer(ctx.db, ctx.runtime, device)
    if not writer.supports_restore:
        raise WriteError(f"Restore is not supported for {device.name}")
    await ctx.say(f"{device.name}: restoring backup of {backup.created_at:%Y-%m-%d %H:%M} ...", 10)
    async with asyncio.timeout(APPLY_TIMEOUT + 60):
        await writer.restore(config)
    await audit.record(
        ctx.db,
        ctx.caller.actor,
        "backup.restore",
        f"{device.name}: backup of {backup.created_at:%Y-%m-%d %H:%M} restored",
        level=AuditLevel.WARNING,
        site_id=device.site_id,
        device_id=device.id,
    )
    await polling.request_poll(ctx.db, device.id)
    await ctx.say(f"{device.name}: restored", 100)


RUNNERS: dict[str, Callable[[JobContext], Awaitable[None]]] = {
    "vlan_sync": _run_vlan_sync,
    "backup": _run_backup,
    "ssh_keys": _run_ssh_keys,
    "discover": _run_discover,
    "restore": _run_restore,
}
