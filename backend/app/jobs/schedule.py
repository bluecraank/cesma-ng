"""The scheduled maintenance jobs (the cron table of cesma-ng)."""

import logging
from datetime import time, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.jobs.worker import ScheduledJob
from app.services import backups, clients, discovery, gateways, maintenance, port_stats
from app.services.context import Runtime

log = logging.getLogger(__name__)


def default_jobs(settings: Settings, box: SecretBox) -> list[ScheduledJob]:
    runtime = Runtime(settings, box)

    async def cleanup(db: AsyncSession) -> None:
        await maintenance.cleanup(db, settings)
        await clients.purge_old_clients(db, settings.retention_client_days)
        await backups.purge_old_backups(db, settings.retention_backup_days)
        await port_stats.purge_old_samples(db, settings.retention_port_stats_days)

    async def backup_all(db: AsyncSession) -> None:
        await backups.backup_all(db, runtime)

    async def discover_switches(db: AsyncSession) -> None:
        found = await discovery.discover_from_arp(db, runtime)
        if found:
            log.info("Discovery: %d new switch(es)", found)

    async def scan_vlans(db: AsyncSession) -> None:
        await discovery.scan_client_vlans(db)

    async def backup_mail(db: AsyncSession) -> None:
        await backups.send_weekly_mail(db, settings)

    async def poll_gateways(db: AsyncSession) -> None:
        await gateways.poll_gateways(db, settings, box)

    async def update_clients(db: AsyncSession) -> None:
        count = await clients.update_clients(db)
        log.info("Clients updated: %d located", count)

    async def resolve_hostnames(db: AsyncSession) -> None:
        await clients.resolve_hostnames(db)

    async def update_vendors(db: AsyncSession) -> None:
        await download_oui(db, settings.oui_url)

    async def init_vendors(db: AsyncSession) -> None:
        if await clients.vendor_count(db) == 0:
            await download_oui(db, settings.oui_url)

    jobs = [
        ScheduledJob("cleanup", cleanup, at=time(4, 0)),
        ScheduledJob("purge-sessions", maintenance.purge_sessions, every=timedelta(hours=1)),
        ScheduledJob("poll-gateways", poll_gateways, every=timedelta(minutes=1)),
        ScheduledJob("update-clients", update_clients, every=timedelta(minutes=5)),
        ScheduledJob("backup-all", backup_all, at=time.fromisoformat(settings.backup_time)),
        ScheduledJob("backup-mail", backup_mail, at=time(22, 0), weekday=6),
        ScheduledJob("discover-switches", discover_switches, every=timedelta(minutes=15)),
        ScheduledJob("scan-client-vlans", scan_vlans, every=timedelta(minutes=5)),
    ]
    if settings.dns_lookup_enabled:
        jobs.append(
            ScheduledJob("resolve-hostnames", resolve_hostnames, every=timedelta(minutes=5))
        )
    if settings.oui_auto_update:
        jobs.append(ScheduledJob("update-mac-vendors", update_vendors, at=time(5, 0), weekday=6))
        jobs.append(ScheduledJob("init-mac-vendors", init_vendors))
    return jobs


async def download_oui(db: AsyncSession, url: str) -> int:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        response = await http.get(url, headers={"User-Agent": "cesma-ng"})
        response.raise_for_status()
    count = await clients.replace_vendors(db, clients.parse_oui_csv(response.text))
    log.info("MAC vendor list updated: %d prefixes", count)
    return count
