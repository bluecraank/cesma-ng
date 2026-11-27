"""Reports per site: firmware overview, free ports, PoE, port errors, backup status."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.db import ensure_utc, utcnow
from app.domain.switch import PoeStatus, PortKind
from app.models import Backup, BackupStatus, Device, Port, PortCounterSample
from app.services.access import require_site_access
from app.services.context import Caller
from app.services.uplinks import uplink_port_ids

UNUSED_AFTER_DAYS = 30
BACKUP_STALE_AFTER = timedelta(days=2)
ERRORS_LIMIT = 50


async def site_report(db: AsyncSession, caller: Caller, site_id: int) -> dict[str, Any]:
    require_site_access(caller.user, site_id)
    devices = (
        (await db.execute(select(Device).where(Device.site_id == site_id).order_by(Device.name)))
        .scalars()
        .all()
    )
    ids = [d.id for d in devices]
    names = {d.id: d.name for d in devices}
    # only the columns the reports read: whole Port objects would also load their VLANs
    ports = (
        (
            await db.execute(
                select(
                    Port.id,
                    Port.device_id,
                    Port.name,
                    Port.kind,
                    Port.oper_up,
                    Port.last_change_at,
                    Port.poe,
                ).where(Port.device_id.in_(ids))
            )
        ).all()
        if ids
        else []
    )
    uplinks = await uplink_port_ids(db, site_id=site_id)
    return {
        "firmware": _firmware(devices),
        "free_ports": _free_ports(ports, names, uplinks),
        "poe": _poe(ports, names),
        "errors": await _errors(db, site_id, names),
        "backups": await _backups(db, devices),
    }


def _firmware(devices: Any) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for d in devices:
        groups[(d.model_name or d.model.value, d.firmware or "?")].append(d.name)
    return [
        {"model": model, "firmware": firmware, "devices": sorted(names)}
        for (model, firmware), names in sorted(groups.items())
    ]


def _free_ports(ports: Any, names: dict[int, str], uplinks: set[int]) -> list[dict[str, Any]]:
    """Access ports that are down and have not been up for a month (or never while observed)."""
    cutoff = utcnow() - timedelta(days=UNUSED_AFTER_DAYS)
    per_device: dict[int, dict[str, Any]] = {}
    for p in ports:
        if p.kind is not PortKind.ETHERNET or p.id in uplinks:
            continue
        entry = per_device.setdefault(
            p.device_id,
            {"device_id": p.device_id, "device": names[p.device_id], "total": 0, "free": []},
        )
        entry["total"] += 1
        unused = not p.oper_up and (
            p.last_change_at is None or ensure_utc(p.last_change_at) < cutoff
        )
        if unused:
            entry["free"].append(p.name)
    return sorted(per_device.values(), key=lambda e: e["device"])


def _poe(ports: Any, names: dict[int, str]) -> list[dict[str, Any]]:
    per_device: dict[int, dict[str, Any]] = {}
    for p in ports:
        if p.poe is None:
            continue
        entry = per_device.setdefault(
            p.device_id,
            {
                "device_id": p.device_id,
                "device": names[p.device_id],
                "ports": 0,
                "delivering": 0,
                "faults": [],
            },
        )
        entry["ports"] += 1
        entry["delivering"] += p.poe is PoeStatus.DELIVERING
        if p.poe is PoeStatus.FAULT:
            entry["faults"].append(p.name)
    return sorted(per_device.values(), key=lambda e: e["device"])


async def _ports_with_error_growth(db: AsyncSession, site_id: int, since: datetime) -> list[int]:
    """Ports whose error counters may have grown since ``since``: only those need a closer look.

    Compares the first and the last sample of each port (two index lookups per port instead of
    reading every sample). Counters only grow, so equal error counters at both ends mean no
    errors - unless the switch restarted in between, which the octet counters going down show.
    """
    sample = PortCounterSample

    def end(newest: bool) -> Any:
        order = sample.sampled_at.desc() if newest else sample.sampled_at
        return (
            select(sample.id)
            .where(sample.port_id == Port.id, sample.sampled_at >= since)
            .order_by(order)
            .limit(1)
            .correlate(Port)
            .scalar_subquery()
        )

    ends = (
        select(Port.id.label("port_id"), end(False).label("first"), end(True).label("last"))
        .join(Device, Device.id == Port.device_id)
        .where(Device.site_id == site_id)
        .subquery()
    )
    first, last = aliased(sample), aliased(sample)
    rows = await db.execute(
        select(ends.c.port_id)
        .join(first, first.id == ends.c.first)
        .join(last, last.id == ends.c.last)
        .where(
            or_(
                last.in_errors + last.out_errors != first.in_errors + first.out_errors,
                last.in_octets < first.in_octets,
                last.out_octets < first.out_octets,
            )
        )
    )
    return list(rows.scalars())


async def _errors(db: AsyncSession, site_id: int, names: dict[int, str]) -> list[dict[str, Any]]:
    """Ports with interface errors in the last 24 hours.

    Summed up in the database (the counters of a big site are millions of samples): the
    growth between two samples of a port, skipping intervals with a counter reset.
    """
    sample = PortCounterSample
    since = utcnow() - timedelta(hours=24)
    candidates = await _ports_with_error_growth(db, site_id, since)
    if not candidates:
        return []

    def growth(column: Any) -> Any:
        previous = func.lag(column).over(partition_by=sample.port_id, order_by=sample.sampled_at)
        return column - previous

    deltas = (
        select(
            sample.port_id.label("port_id"),
            growth(sample.in_errors).label("in_errors"),
            growth(sample.out_errors).label("out_errors"),
            growth(sample.in_octets).label("in_octets"),
            growth(sample.out_octets).label("out_octets"),
        )
        .where(sample.port_id.in_(candidates), sample.sampled_at >= since)
        .subquery()
    )
    errors = func.sum(deltas.c.in_errors + deltas.c.out_errors)
    rows = await db.execute(
        select(Port.device_id, Port.name, errors)
        .join(Port, Port.id == deltas.c.port_id)
        .where(
            deltas.c.in_errors >= 0,  # NULL for the first sample of a port: no interval
            deltas.c.out_errors >= 0,
            deltas.c.in_octets >= 0,
            deltas.c.out_octets >= 0,
        )
        .group_by(deltas.c.port_id, Port.device_id, Port.name)
        .having(errors > 0)
        .order_by(errors.desc(), deltas.c.port_id)
        .limit(ERRORS_LIMIT)
    )
    return [
        {"device_id": device_id, "device": names[device_id], "port": name, "errors": int(count)}
        for device_id, name, count in rows
    ]


async def _backups(db: AsyncSession, devices: Any) -> list[dict[str, Any]]:
    """Devices whose last successful backup is missing or older than two days."""
    if not devices:
        return []
    last_ok = dict(
        (
            await db.execute(
                select(Backup.device_id, func.max(Backup.created_at))
                .where(
                    Backup.status == BackupStatus.OK, Backup.device_id.in_([d.id for d in devices])
                )
                .group_by(Backup.device_id)
            )
        )
        .tuples()
        .all()
    )
    stale = utcnow() - BACKUP_STALE_AFTER
    return [
        {"device_id": d.id, "device": d.name, "last_backup": last_ok.get(d.id)}
        for d in devices
        if last_ok.get(d.id) is None or ensure_utc(last_ok[d.id]) < stale
    ]
