"""Finding new switches, and ping sweeps that fill the ARP tables for client discovery."""

import asyncio
import ipaddress
import logging
import platform
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.core.errors import ValidationFailedError
from app.drivers.registry import Detection, detect
from app.models import (
    ArpEntry,
    CredentialProfile,
    Device,
    DeviceStatus,
    DiscoveredHost,
    SiteVlan,
)
from app.services import audit, events, polling
from app.services.audit import Actor
from app.services.clients import vendors_for
from app.services.context import Runtime
from app.services.credentials import to_device_credentials
from app.transports.snmp import SnmpError

log = logging.getLogger(__name__)

#: MAC vendors whose devices are worth probing as switches
SWITCH_VENDORS = ("dell", "hewlett", "hp ", "hpe", "aruba")
REPROBE_AFTER = timedelta(hours=24)
MAX_SCAN_HOSTS = 1024
PING_CONCURRENCY = 64

# --- Switch discovery ------------------------------------------------------------------------


async def discover_from_arp(db: AsyncSession, runtime: Runtime) -> int:
    """Probe IPs from the ARP tables whose MAC belongs to a switch vendor."""
    rows = (
        (await db.execute(select(ArpEntry.ip_address, ArpEntry.mac_address, ArpEntry.device_id)))
        .tuples()
        .all()
    )
    vendors = await vendors_for(db, [mac for _, mac, _ in rows])
    candidates: dict[str, int | None] = {}
    for ip, mac, source_device in rows:
        name = vendors.get(mac, "").lower()
        if any(v in name for v in SWITCH_VENDORS):
            candidates.setdefault(ip, source_device)
    return await _probe_all(db, runtime, candidates)


async def discover_range(
    db: AsyncSession, runtime: Runtime, cidr: str, site_id: int, profile_id: int | None
) -> int:
    """Probe every address of a network (manual scan)."""
    hosts = _hosts(cidr)
    return await _probe_all(
        db, runtime, dict.fromkeys(hosts), site_id=site_id, profile_id=profile_id, force=True
    )


def _hosts(cidr: str) -> list[str]:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValidationFailedError("Not a network, e.g. 10.0.10.0/24") from exc
    if network.num_addresses > MAX_SCAN_HOSTS + 2:
        raise ValidationFailedError(f"At most {MAX_SCAN_HOSTS} addresses (/22)")
    return [str(h) for h in network.hosts()]


async def _probe_all(
    db: AsyncSession,
    runtime: Runtime,
    candidates: dict[str, int | None],
    *,
    site_id: int | None = None,
    profile_id: int | None = None,
    force: bool = False,
) -> int:
    known = set((await db.execute(select(Device.hostname))).scalars())
    seen = {h.ip_address: h for h in (await db.execute(select(DiscoveredHost))).scalars()}
    now = utcnow()
    todo = []
    for ip, source in candidates.items():
        host = seen.get(ip)
        if ip in known or (host and host.ignored):
            continue
        if not force and host and ensure_utc(host.last_probe_at) > now - REPROBE_AFTER:
            continue
        todo.append((ip, source))

    # Database lookups first (one session must not be used concurrently), then probe in parallel.
    probes = []
    for ip, source in todo:
        target_site, profile = await _context(db, source, site_id, profile_id)
        probes.append(_Probe(ip, target_site, profile))

    semaphore = asyncio.Semaphore(32)

    async def run(probe: _Probe) -> None:
        async with semaphore:
            credentials = to_device_credentials(probe.profile, runtime.box)
            client = polling.snmp_client(runtime.settings, probe.ip, credentials, quick=True)
            try:
                probe.detection = await detect(client)
            except (SnmpError, OSError, TimeoutError):
                probe.detection = None

    await asyncio.gather(*(run(p) for p in probes))

    found = 0
    for probe in probes:
        host = seen.get(probe.ip) or DiscoveredHost(ip_address=probe.ip, ignored=False)
        host.last_probe_at = now
        db.add(host)
        detection = probe.detection
        if detection is None or probe.site_id is None:
            host.result = "no answer"
        elif detection.model is None:
            host.result = f"not supported ({detection.sys_object_id})"
        else:
            host.result = detection.model.value
            if await _add_device(db, probe.ip, probe.site_id, detection, probe.profile):
                found += 1
    await db.flush()
    return found


@dataclass
class _Probe:
    ip: str
    site_id: int | None
    profile: CredentialProfile | None
    detection: Detection | None = None


async def _context(
    db: AsyncSession, source: int | None, site_id: int | None, profile_id: int | None
) -> tuple[int | None, CredentialProfile | None]:
    """Site and credentials for a probe: given explicitly, or those of the reporting switch."""
    if source is not None and site_id is None:
        device = await db.get(Device, source)
        if device is not None:
            site_id = site_id or device.site_id
            profile_id = profile_id or device.credential_profile_id
    profile = await db.get(CredentialProfile, profile_id) if profile_id else None
    return site_id, profile


async def _add_device(
    db: AsyncSession,
    ip: str,
    site_id: int,
    detection: Detection,
    profile: CredentialProfile | None,
) -> bool:
    assert detection.model is not None
    name = (detection.sys_name or ip)[:100]
    if await db.scalar(select(Device.id).where(Device.name == name)):
        name = f"{name} ({ip})"[:100]
    device = Device(
        site_id=site_id,
        name=name,
        hostname=ip,
        model=detection.model,
        credential_profile_id=profile.id if profile else None,
        status=DeviceStatus.UNCONFIRMED,
        location_note="",
    )
    db.add(device)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    message = f"New switch found: {name} ({ip}, {detection.model_name or detection.model.value})"
    events.notify(db, device, events.Kind.DEVICE_DISCOVERED, events.Severity.INFO, message)
    await audit.record(
        db, Actor.system(), "device.discovered", message, site_id=site_id, device_id=device.id
    )
    return True


async def remember_ignored(db: AsyncSession, ip: str) -> None:
    """A deleted, never confirmed device should not be found again."""
    host = await db.get(DiscoveredHost, ip) or DiscoveredHost(ip_address=ip, last_probe_at=utcnow())
    host.ignored = True
    db.add(host)


# --- Ping sweep ------------------------------------------------------------------------------


async def ping(ip: str) -> bool:
    windows = platform.system() == "Windows"
    args = ["ping", "-n", "1", "-w", "1000", ip] if windows else ["ping", "-c", "1", "-W", "1", ip]
    try:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        return await process.wait() == 0
    except (OSError, FileNotFoundError):
        return False


async def ping_sweep(hosts: Iterable[str]) -> int:
    """Ping all hosts (the replies fill the ARP tables of the routers); returns answers."""
    semaphore = asyncio.Semaphore(PING_CONCURRENCY)

    async def one(ip: str) -> bool:
        async with semaphore:
            return await ping(ip)

    return sum(await asyncio.gather(*(one(ip) for ip in hosts)))


async def scan_client_vlans(db: AsyncSession) -> int:
    vlans = (
        (
            await db.execute(
                select(SiteVlan).where(SiteVlan.scan_enabled, SiteVlan.ip_range.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    answered = 0
    for vlan in vlans:
        try:
            answered += await ping_sweep(_hosts(vlan.ip_range or ""))
        except ValidationFailedError:
            log.info("VLAN %s: range %s too large for scanning", vlan.vid, vlan.ip_range)
    return answered
