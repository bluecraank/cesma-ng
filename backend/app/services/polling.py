"""Run one poll task for one device: read via driver, store, update status and schedule."""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.core.db import ensure_utc, utcnow
from app.domain.credentials import DeviceCredentials
from app.drivers.base import SnmpSwitchDriver
from app.drivers.registry import driver_for, writer_for
from app.drivers.writers import ConfigWriter, SimulatedWriter
from app.models import (
    AuditLevel,
    CredentialProfile,
    Device,
    DevicePollState,
    DeviceStatus,
    PollTask,
)
from app.services import audit, events, inventory
from app.services.audit import Actor
from app.services.credentials import to_device_credentials
from app.services.events import Kind, Severity
from app.transports.snmp import PysnmpClient, RecordedSnmpClient, SnmpClient

log = logging.getLogger(__name__)

DriverFactory = Callable[[Device, DeviceCredentials], SnmpSwitchDriver]
MAX_BACKOFF = timedelta(minutes=30)


def snmp_client(
    settings: Settings, hostname: str, credentials: DeviceCredentials, *, quick: bool = False
) -> SnmpClient:
    """Live SNMP client, or a recording when the simulator directory has one for the host."""
    if (recording := recording_for(settings, hostname)) is not None:
        return RecordedSnmpClient.from_file(recording)
    if quick:  # interactive use (detection): fail fast
        return PysnmpClient(hostname, credentials.snmp, timeout=2, retries=1)
    return PysnmpClient(hostname, credentials.snmp)


def recording_for(settings: Settings, hostname: str) -> Path | None:
    """The simulator recording of a host, if the simulator is enabled and has one."""
    if not settings.snmp_simulator_dir:
        return None
    path = Path(settings.snmp_simulator_dir) / f"{hostname}.snmprec"
    return path if path.is_file() else None


def config_writer(
    settings: Settings, device: Device, credentials: DeviceCredentials
) -> ConfigWriter:
    """Writer for a device; simulated (no network) for simulator hosts."""
    writer = writer_for(device.model, device.hostname, credentials)
    if recording_for(settings, device.hostname) is not None:
        return SimulatedWriter(writer, _simulated_config(device))
    return writer


def _simulated_config(device: Device) -> str:
    return "\n".join(
        [
            f"! {device.model_name or device.model} {device.firmware or ''}",
            f"hostname {device.sys_name or device.name}",
            "! (simulated backup - cesma-ng simulator mode)",
            "",
        ]
    )


def driver_factory_for(settings: Settings) -> DriverFactory:
    def factory(device: Device, credentials: DeviceCredentials) -> SnmpSwitchDriver:
        return driver_for(device.model, snmp_client(settings, device.hostname, credentials))

    return factory


def interval(settings: Settings, task: PollTask) -> timedelta:
    seconds = {
        PollTask.INVENTORY: settings.poll_inventory_interval,
        PollTask.FDB: settings.poll_fdb_interval,
        PollTask.ARP: settings.poll_arp_interval,
        PollTask.LLDP: settings.poll_lldp_interval,
        PollTask.COUNTERS: settings.poll_counters_interval,
    }[task]
    return timedelta(seconds=seconds)


def _jitter(delta: timedelta) -> timedelta:
    """±10 % so that devices added together do not stay in lockstep."""
    return delta * random.uniform(0.9, 1.1)


async def get_state(db: AsyncSession, device_id: int, task: PollTask) -> DevicePollState:
    state = await db.get(DevicePollState, (device_id, task))
    if state is None:
        state = DevicePollState(device_id=device_id, task=task, next_due_at=utcnow(), failures=0)
        db.add(state)
    return state


async def request_poll(db: AsyncSession, device_id: int) -> None:
    """Make every task of a device due now ("refresh" button)."""
    for task in PollTask:
        state = await get_state(db, device_id, task)
        state.next_due_at = utcnow()
    await db.flush()


async def poll_device(
    db: AsyncSession,
    device_id: int,
    task: PollTask,
    *,
    settings: Settings,
    box: SecretBox,
    driver_factory: DriverFactory,
) -> bool:
    """Run one task; returns success. Commits its own transaction."""
    device = await db.get(Device, device_id)
    if device is None:
        return False
    state = await get_state(db, device_id, task)
    credentials = to_device_credentials(await _profile(db, device), box)
    driver = driver_factory(device, credentials)

    started = time.monotonic()
    state.last_run_at = utcnow()
    try:
        async with asyncio.timeout(settings.poll_timeout):
            await _run(db, device, task, driver)
    except Exception as exc:  # any failure of one device must not stop the worker
        await db.rollback()
        device = await db.get(Device, device_id)
        state = await get_state(db, device_id, task)
        if device is None:
            return False
        await _record_failure(db, device, state, task, exc, settings)
        await db.commit()
        return False

    state.failures = 0
    state.last_error = None
    state.last_success_at = utcnow()
    state.last_duration_ms = int((time.monotonic() - started) * 1000)
    state.next_due_at = utcnow() + _jitter(interval(settings, task))
    await db.commit()
    return True


async def _profile(db: AsyncSession, device: Device) -> CredentialProfile | None:
    if device.credential_profile_id is None:
        return None
    return await db.get(CredentialProfile, device.credential_profile_id)


async def _run(db: AsyncSession, device: Device, task: PollTask, driver: SnmpSwitchDriver) -> None:
    match task:
        case PollTask.INVENTORY:
            inv = await driver.read_inventory()
            changes = await inventory.apply_inventory(db, device, inv)
            await _mark_online(db, device)
            if changes.rebooted:
                await audit.record(
                    db,
                    Actor.system(),
                    "device.rebooted",
                    f"{device.name} was restarted",
                    level=AuditLevel.WARNING,
                    site_id=device.site_id,
                    device_id=device.id,
                )
            await events.port_changes(db, device, changes)
        case PollTask.FDB:
            await inventory.apply_fdb(db, device, await driver.read_fdb())
        case PollTask.ARP:
            await inventory.apply_arp(db, device, await driver.read_arp())
        case PollTask.LLDP:
            await inventory.apply_lldp(db, device, await driver.read_lldp())
        case PollTask.COUNTERS:
            await inventory.apply_counters(db, device, await driver.read_counters())


async def _mark_online(db: AsyncSession, device: Device) -> None:
    previous = device.status
    device.status = DeviceStatus.ONLINE
    if previous is DeviceStatus.OFFLINE:
        await audit.record(
            db,
            Actor.system(),
            "device.online",
            f"{device.name} is reachable again",
            site_id=device.site_id,
            device_id=device.id,
        )
        events.notify(
            db, device, Kind.DEVICE_ONLINE, Severity.INFO, f"{device.name} is reachable again"
        )


async def _record_failure(
    db: AsyncSession,
    device: Device,
    state: DevicePollState,
    task: PollTask,
    exc: BaseException,
    settings: Settings,
) -> None:
    message = str(exc) or exc.__class__.__name__
    log.info("Poll %s of %s failed: %s", task, device.name, message)
    state.failures += 1
    state.last_error = message[:2000]
    backoff = min(interval(settings, task) * (2 ** min(state.failures - 1, 6)), MAX_BACKOFF)
    state.next_due_at = utcnow() + _jitter(backoff)

    if (
        task is PollTask.INVENTORY
        and state.failures >= settings.offline_after_failures
        and device.status is not DeviceStatus.OFFLINE
    ):
        device.status = DeviceStatus.OFFLINE
        await audit.record(
            db,
            Actor.system(),
            "device.offline",
            f"{device.name} is not reachable: {message}",
            level=AuditLevel.ERROR,
            site_id=device.site_id,
            device_id=device.id,
        )
        events.notify(
            db, device, Kind.DEVICE_OFFLINE, Severity.CRITICAL, f"{device.name} is not reachable"
        )


async def due_tasks(db: AsyncSession, limit: int) -> list[tuple[int, PollTask]]:
    """Devices/tasks that should run now. Devices without a state row are due immediately."""
    now = utcnow()
    devices = (
        (
            await db.execute(
                select(Device.id)
                .where(Device.status != DeviceStatus.UNCONFIRMED)
                .order_by(Device.id)
            )
        )
        .scalars()
        .all()
    )
    states = {
        (s.device_id, s.task): s for s in (await db.execute(select(DevicePollState))).scalars()
    }
    due: list[tuple[int, PollTask, float]] = []
    for device_id in devices:
        for task in PollTask:
            state = states.get((device_id, task))
            next_due = state.next_due_at if state else None
            if next_due is None:
                due.append((device_id, task, 0.0))
            elif ensure_utc(next_due) <= now:
                due.append((device_id, task, ensure_utc(next_due).timestamp()))
    due.sort(key=lambda d: (d[2], d[1] is not PollTask.INVENTORY))
    return [(d, t) for d, t, _ in due[:limit]]
