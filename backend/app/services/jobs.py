"""Background jobs: queued by the API, executed one at a time by the worker."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.errors import DeviceError, ForbiddenError, NotFoundError, ValidationFailedError
from app.drivers.writers import WriteError
from app.models import (
    BackupStatus,
    Device,
    DeviceStatus,
    Job,
    JobStatus,
    Permission,
    Port,
    PortProfile,
    User,
)
from app.services import (
    audit,
    backups,
    device_rename,
    discovery,
    polling,
    port_config,
    site_config,
    ssh_keys,
)
from app.services.access import require_permission, require_site_access, visible_site_ids
from app.services.context import Caller, Runtime
from app.services.credentials import public_key_of
from app.services.device_access import device_writer
from app.services.devices import get_device

log = logging.getLogger(__name__)

APPLY_TIMEOUT = 300
MIN_SSH_KEYS = 2

#: job kind -> permission needed on the job's site
JOB_KINDS: dict[str, Permission] = {
    "vlan_sync": Permission.VLANS_MANAGE,
    "backup": Permission.BACKUPS_RUN,
    "ssh_keys": Permission.SSH_KEYS_PUSH,
    "discover": Permission.DEVICES_MANAGE,
    # whoever may change a port profile rolls it out to the ports bound to it
    "port_profile": Permission.VLANS_MANAGE,
    "port_change": Permission.PORTS_EDIT,
    "rename": Permission.DEVICES_MANAGE,
}

#: short changes of one switch: they run next to the long jobs (one at a time per switch),
#: so a port change does not wait for the nightly backup of 300 switches
QUICK_KINDS = frozenset({"port_change", "rename"})
SUMMARY_LENGTH = 255


#: failed switches named in the job's error (the log has all of them, with the reason)
FAILED_NAMES = 10


def _failure(failed: list[str], total: int) -> WriteError:
    """``3 of 29 switch(es) failed: sw01, sw07, sw12`` - visible without opening the log."""
    names = ", ".join(failed[:FAILED_NAMES])
    if len(failed) > FAILED_NAMES:
        names += f" (+{len(failed) - FAILED_NAMES} more)"
    return WriteError(f"{len(failed)} of {total} switch(es) failed: {names}")


def _clip(text: str) -> str:
    return text if len(text) <= SUMMARY_LENGTH else text[: SUMMARY_LENGTH - 1] + "…"


# --- Queue -----------------------------------------------------------------------------------


async def enqueue(
    db: AsyncSession,
    caller: Caller,
    kind: str,
    site_id: int,
    payload: dict[str, Any],
    *,
    device_id: int | None = None,
    summary: str = "",
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
    if not summary and (ids := payload.get("device_ids")):
        names = await db.scalars(
            select(Device.name).where(Device.id.in_(ids)).order_by(Device.name)
        )
        summary = ", ".join(names)
        if len(ids) == 1:
            device_id = device_id or ids[0]
    job = Job(
        kind=kind,
        site_id=site_id,
        device_id=device_id,
        summary=_clip(summary),
        created_by=caller.user.username,
        payload={**payload, "user_id": caller.user.id},
    )
    db.add(job)
    await db.flush()
    if kind not in QUICK_KINDS:  # quick changes are audited when they are applied
        await audit.record(
            db, caller.actor, f"job.{kind}", f"Job {kind} #{job.id} queued", site_id=site_id
        )
    return job


async def enqueue_port_change(
    db: AsyncSession, caller: Caller, runtime: Runtime, device_id: int, data: dict[str, Any]
) -> Job:
    """Check the change now (errors show up in the dialog), apply it in the background."""
    device = await get_device(db, caller, device_id, Permission.PORTS_EDIT)
    change = await port_config.build_change(db, device.site_id, data)
    result = await port_config.plan_port_change(
        db, caller, runtime, device_id, data["port_ids"], change
    )
    ports = ", ".join(p.name for p in result.ports)
    return await enqueue(
        db,
        caller,
        "port_change",
        device.site_id,
        {"change": data},
        device_id=device.id,
        summary=f"{device.name}: {ports}",
    )


async def enqueue_rename(
    db: AsyncSession, caller: Caller, runtime: Runtime, device_id: int, name: str
) -> Job:
    await device_rename.plan_rename(db, caller, runtime, device_id, name)  # validates the name
    device = await get_device(db, caller, device_id, Permission.DEVICES_MANAGE)
    return await enqueue(
        db,
        caller,
        "rename",
        device.site_id,
        {"name": name.strip()},
        device_id=device.id,
        summary=f"{device.name} → {name.strip()}",
    )


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


async def next_pending(
    db: AsyncSession,
    *,
    quick: bool | None = None,
    busy_devices: Collection[int] = (),
    exclude_ids: Collection[int] = (),
) -> Job | None:
    """The oldest waiting job; ``quick`` picks one lane (see ``QUICK_KINDS``), ``None`` any.

    Quick jobs for a switch in ``busy_devices`` wait until the switch is free again.
    """
    stmt = select(Job).where(Job.status == JobStatus.PENDING)
    if quick is True:
        stmt = stmt.where(Job.kind.in_(QUICK_KINDS))
        if busy_devices:
            stmt = stmt.where(or_(Job.device_id.is_(None), Job.device_id.not_in(busy_devices)))
    elif quick is False:
        stmt = stmt.where(Job.kind.not_in(QUICK_KINDS))
    if exclude_ids:
        stmt = stmt.where(Job.id.not_in(exclude_ids))
    return await db.scalar(stmt.order_by(Job.created_at, Job.id).limit(1))


async def run_job(db: AsyncSession, job: Job, runtime: Runtime) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()
    await db.commit()
    try:
        user = await db.get(User, job.payload.get("user_id"))
        if user is None or not user.is_active:
            raise ForbiddenError("The user who started the job no longer exists or is disabled")
        caller = Caller(user)
        if job.kind == "ssh_keys" and not runtime.settings.ssh_key_push_enabled:
            raise ValidationFailedError("Uploading SSH keys is switched off")
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
    failed: list[str] = []
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
            failed.append(device.name)
            await ctx.say(
                f"{device.name}: FAILED - {port_config.describe_failure(exc, APPLY_TIMEOUT)}",
                progress,
            )
    if failed:
        raise _failure(failed, len(plans))


async def _run_backup(ctx: JobContext) -> None:
    devices = await _devices(ctx)
    failed: list[str] = []
    for index, device in enumerate(devices, 1):
        backup = await backups.run_backup(ctx.db, ctx.runtime, device, ctx.caller.actor)
        state = "ok" if backup.status is BackupStatus.OK else f"FAILED - {backup.error}"
        if backup.status is not BackupStatus.OK:
            failed.append(device.name)
        await ctx.say(f"{device.name}: {state}", int(index / max(len(devices), 1) * 100))
    if failed:
        raise _failure(failed, len(devices))


async def _run_ssh_keys(ctx: JobContext) -> None:
    assert ctx.job.site_id is not None
    keys = [k.key for k in await ssh_keys.keys_to_push(ctx.db)]
    await ctx.say(f"{len(keys)} key(s) from the SSH key list")
    if len(keys) < MIN_SSH_KEYS:
        raise WriteError(f"At least {MIN_SSH_KEYS} SSH keys are required")
    devices = await _devices(ctx)
    failed: list[str] = []
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
            failed.append(device.name)
            await ctx.say(
                f"{device.name}: FAILED - {port_config.describe_failure(exc, APPLY_TIMEOUT)}",
                progress,
            )
    if failed:
        raise _failure(failed, len(devices))


async def _run_discover(ctx: JobContext) -> None:
    assert ctx.job.site_id is not None
    cidr = str(ctx.job.payload.get("cidr") or "")
    await ctx.say(f"Scanning {cidr} ...", 5)
    found = await discovery.discover_range(
        ctx.db, ctx.runtime, cidr, ctx.job.site_id, ctx.job.payload.get("credential_profile_id")
    )
    await ctx.say(f"{found} new switch(es) found", 100)


async def _run_port_profile(ctx: JobContext) -> None:
    """Apply a port profile to every port bound to it, switch by switch."""
    profile_id = int(ctx.job.payload.get("profile_id") or 0)
    profile = await ctx.db.get(PortProfile, profile_id)
    if profile is None or profile.site_id != ctx.job.site_id:
        await ctx.say("Port profile no longer exists, nothing to do", 100)
        return
    change = port_config.profile_change(profile)
    rows = await ctx.db.execute(
        select(Port.device_id, Port.id)
        .join(Device, Device.id == Port.device_id)
        .where(Port.port_profile_id == profile.id, Device.status != DeviceStatus.UNCONFIRMED)
    )
    by_device: dict[int, list[int]] = {}
    for device_id, port_id in rows:
        by_device.setdefault(device_id, []).append(port_id)
    await ctx.say(f"Port profile {profile.name}: {sum(map(len, by_device.values()))} port(s)")
    failed: list[str] = []
    for index, (device_id, port_ids) in enumerate(sorted(by_device.items()), 1):
        progress = int(index / len(by_device) * 100)
        device = await ctx.db.get(Device, device_id)
        assert device is not None
        name = device.name
        try:
            plan, _ = await port_config.apply_port_change(
                ctx.db,
                ctx.caller,
                ctx.runtime,
                device_id,
                port_ids,
                change,
                Permission.VLANS_MANAGE,
            )
            done = "nothing to do" if plan.empty else f"{len(plan.operations)} change(s) applied"
            await ctx.say(f"{name}: {done}", progress)
        except DeviceError as exc:
            failed.append(name)
            await ctx.say(f"{name}: FAILED - {exc}", progress)
    if failed:
        raise _failure(failed, len(by_device))


async def _job_device(ctx: JobContext) -> Device:
    device = await ctx.db.get(Device, ctx.job.device_id) if ctx.job.device_id else None
    if device is None:
        raise NotFoundError("The switch no longer exists")
    return device


async def _run_port_change(ctx: JobContext) -> None:
    """A port change from the port dialog, applied like ``ports/apply``."""
    device = await _job_device(ctx)
    data = ctx.job.payload.get("change") or {}
    change = await port_config.build_change(ctx.db, device.site_id, data)
    await ctx.say(f"{device.name}: writing the configuration ...", 10)
    plan, lines = await port_config.apply_port_change(
        ctx.db, ctx.caller, ctx.runtime, device.id, data.get("port_ids") or [], change
    )
    if plan.empty:
        await ctx.say(f"{device.name}: nothing to change on the switch", 100)
        return
    ctx.job.log += "".join(f"    {line}\n" for line in lines)
    await ctx.say(f"{device.name}: {len(plan.operations)} change(s) applied", 100)


async def _run_rename(ctx: JobContext) -> None:
    device = await _job_device(ctx)
    old = device.name
    name = str(ctx.job.payload.get("name") or "")
    await ctx.say(f"{old}: setting the hostname {name} ...", 10)
    _, lines = await device_rename.apply_rename(ctx.db, ctx.caller, ctx.runtime, device.id, name)
    ctx.job.log += "".join(f"    {line}\n" for line in lines)
    await ctx.say(f"{old} renamed to {name}", 100)


RUNNERS: dict[str, Callable[[JobContext], Awaitable[None]]] = {
    "vlan_sync": _run_vlan_sync,
    "backup": _run_backup,
    "ssh_keys": _run_ssh_keys,
    "discover": _run_discover,
    "port_profile": _run_port_profile,
    "port_change": _run_port_change,
    "rename": _run_rename,
}
