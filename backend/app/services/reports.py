"""Reports per site: firmware overview, free ports, PoE, port errors, backup status."""

from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.domain.switch import PoeStatus, PortKind
from app.models import Backup, BackupStatus, Device, Port, PortCounterSample
from app.services.access import require_site_access
from app.services.context import Caller
from app.services.port_stats import rates
from app.services.uplinks import uplink_port_ids

UNUSED_AFTER_DAYS = 30
BACKUP_STALE_AFTER = timedelta(days=2)


async def site_report(db: AsyncSession, caller: Caller, site_id: int) -> dict[str, Any]:
    require_site_access(caller.user, site_id)
    devices = (
        (await db.execute(select(Device).where(Device.site_id == site_id).order_by(Device.name)))
        .scalars()
        .all()
    )
    ids = [d.id for d in devices]
    names = {d.id: d.name for d in devices}
    ports = (
        (await db.execute(select(Port).where(Port.device_id.in_(ids)))).scalars().all()
        if ids
        else []
    )
    uplinks = await uplink_port_ids(db)
    return {
        "firmware": _firmware(devices),
        "free_ports": _free_ports(ports, names, uplinks),
        "poe": _poe(ports, names),
        "errors": await _errors(db, ports, names),
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


async def _errors(db: AsyncSession, ports: Any, names: dict[int, str]) -> list[dict[str, Any]]:
    """Ports with interface errors in the last 24 hours."""
    by_id = {p.id: p for p in ports}
    if not by_id:
        return []
    since = utcnow() - timedelta(hours=24)
    samples = (
        (
            await db.execute(
                select(PortCounterSample)
                .where(
                    PortCounterSample.port_id.in_(list(by_id)),
                    PortCounterSample.sampled_at >= since,
                )
                .order_by(PortCounterSample.port_id, PortCounterSample.sampled_at)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[int, list[PortCounterSample]] = defaultdict(list)
    for s in samples:
        grouped[s.port_id].append(s)
    result = []
    for port_id, series in grouped.items():
        errors = sum(p["in_errors"] + p["out_errors"] for p in rates(series))
        if errors:
            port = by_id[port_id]
            result.append(
                {
                    "device_id": port.device_id,
                    "device": names[port.device_id],
                    "port": port.name,
                    "errors": errors,
                }
            )
    return sorted(result, key=lambda e: -e["errors"])[:50]


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
