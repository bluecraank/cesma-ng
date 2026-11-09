"""End devices: build the client list from MAC/ARP tables, enrich it, search it."""

import asyncio
import csv
import io
import logging
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.domain.mac import mac_like_patterns, normalize_mac, vendor_prefix
from app.domain.switch import PortKind
from app.models import ArpEntry, Client, Device, FdbEntry, MacType, MacVendor, Port
from app.services.access import visible_site_ids
from app.services.context import Caller
from app.services.uplinks import uplink_port_ids

log = logging.getLogger(__name__)

# --- Building the client list ----------------------------------------------------------------


@dataclass(frozen=True)
class _Location:
    device_id: int
    site_id: int
    port_id: int
    port_name: str
    vid: int | None
    seen_at: Any


async def update_clients(db: AsyncSession) -> int:
    """Locate every MAC on its access port (never on an uplink) and store/refresh it."""
    uplinks = await uplink_port_ids(db)
    rows = await db.execute(
        select(
            FdbEntry.mac_address,
            FdbEntry.vid,
            FdbEntry.seen_at,
            Port.id,
            Port.name,
            Device.id,
            Device.site_id,
        )
        .join(Port, Port.id == FdbEntry.port_id)
        .join(Device, Device.id == FdbEntry.device_id)
        .where(Port.kind == PortKind.ETHERNET)
    )
    locations: dict[str, _Location] = {}
    for mac, vid, seen_at, port_id, port_name, device_id, site_id in rows.tuples():
        if port_id in uplinks:
            continue
        current = locations.get(mac)
        if current is None or ensure_utc(seen_at) > ensure_utc(current.seen_at):
            locations[mac] = _Location(device_id, site_id, port_id, port_name, vid, seen_at)

    ips = await _latest_ips(db)
    existing = (
        {
            c.mac_address: c
            for c in (
                await db.execute(select(Client).where(Client.mac_address.in_(list(locations))))
            ).scalars()
        }
        if locations
        else {}
    )
    now = utcnow()
    for mac, loc in locations.items():
        client = existing.get(mac)
        if client is None:
            client = Client(mac_address=mac, first_seen_at=now)
            db.add(client)
        new_ip = ips.get(mac)
        if new_ip and new_ip != client.ip_address:
            client.ip_address = new_ip
            client.dns_checked_at = None  # new address: resolve the name again
        client.vid = loc.vid
        client.site_id = loc.site_id
        client.device_id = loc.device_id
        client.port_id = loc.port_id
        client.port_name = loc.port_name
        client.last_seen_at = now
    await db.flush()
    return len(locations)


async def _latest_ips(db: AsyncSession) -> dict[str, str]:
    rows = await db.execute(
        select(ArpEntry.mac_address, ArpEntry.ip_address).order_by(ArpEntry.seen_at)
    )
    return {mac: ip for mac, ip in rows.tuples()}  # later rows (newer) win


async def purge_old_clients(db: AsyncSession, days: int) -> None:
    await db.execute(delete(Client).where(Client.last_seen_at < utcnow() - timedelta(days=days)))


# --- DNS -------------------------------------------------------------------------------------


async def resolve_hostnames(db: AsyncSession, *, batch: int = 200, recheck_hours: int = 24) -> int:
    """Reverse DNS for clients whose address is new or whose name is older than a day."""
    due_before = utcnow() - timedelta(hours=recheck_hours)
    clients = (
        (
            await db.execute(
                select(Client)
                .where(
                    Client.ip_address.is_not(None),
                    or_(Client.dns_checked_at.is_(None), Client.dns_checked_at < due_before),
                )
                .limit(batch)
            )
        )
        .scalars()
        .all()
    )
    semaphore = asyncio.Semaphore(20)

    async def lookup(client: Client) -> None:
        async with semaphore:
            client.hostname = await reverse_dns(client.ip_address or "") or client.hostname
            client.dns_checked_at = utcnow()

    await asyncio.gather(*(lookup(c) for c in clients))
    await db.flush()
    return len(clients)


DNS_TIMEOUT = 2.0


async def reverse_dns(ip: str) -> str | None:
    try:
        async with asyncio.timeout(DNS_TIMEOUT):
            name, _, _ = await asyncio.to_thread(socket.gethostbyaddr, ip)
            return name
    except (OSError, TimeoutError):
        return None


# --- Vendors and types -----------------------------------------------------------------------


def parse_oui_csv(text: str) -> dict[str, str]:
    """IEEE oui.csv: Registry,Assignment,Organization Name,Organization Address."""
    result = {}
    for row in csv.DictReader(io.StringIO(text)):
        assignment = (row.get("Assignment") or "").strip().lower()
        name = (row.get("Organization Name") or "").strip()
        if len(assignment) == 6 and name:
            result[":".join(assignment[i : i + 2] for i in range(0, 6, 2))] = name[:255]
    return result


async def replace_vendors(db: AsyncSession, vendors: dict[str, str]) -> int:
    if not vendors:
        return 0
    await db.execute(delete(MacVendor))
    db.add_all(MacVendor(prefix=p, vendor=v) for p, v in vendors.items())
    await db.flush()
    return len(vendors)


async def vendor_count(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(MacVendor)) or 0


async def vendors_for(db: AsyncSession, macs: Sequence[str]) -> dict[str, str]:
    prefixes = {vendor_prefix(m) for m in macs}
    if not prefixes:
        return {}
    rows = await db.execute(select(MacVendor).where(MacVendor.prefix.in_(prefixes)))
    by_prefix = {v.prefix: v.vendor for v in rows.scalars()}
    return {m: by_prefix[vendor_prefix(m)] for m in macs if vendor_prefix(m) in by_prefix}


def match_type(mac: str, types: Sequence[MacType]) -> MacType | None:
    """Longest matching prefix wins."""
    candidates = [t for t in types if mac.startswith(t.prefix)]
    return max(candidates, key=lambda t: len(t.prefix), default=None)


# --- Search ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientFilter:
    query: str | None = None
    site_id: int | None = None
    vid: int | None = None
    device_id: int | None = None
    active_only: bool = False
    limit: int = 100
    offset: int = 0


ACTIVE_WINDOW = timedelta(minutes=30)


async def search_clients(
    db: AsyncSession, caller: Caller, flt: ClientFilter
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Client, Device.name).outerjoin(Device, Device.id == Client.device_id)
    if (ids := visible_site_ids(caller.user)) is not None:
        stmt = stmt.where(Client.site_id.in_(ids))
    if flt.site_id is not None:
        stmt = stmt.where(Client.site_id == flt.site_id)
    if flt.vid is not None:
        stmt = stmt.where(Client.vid == flt.vid)
    if flt.device_id is not None:
        stmt = stmt.where(Client.device_id == flt.device_id)
    if flt.active_only:
        stmt = stmt.where(Client.last_seen_at >= utcnow() - ACTIVE_WINDOW)
    if q := (flt.query or "").strip():
        conditions = [
            Client.ip_address.startswith(q),
            Client.hostname.ilike(f"%{q}%"),
            Client.port_name == q,
            Device.name.ilike(f"%{q}%"),
        ]
        if (mac := normalize_mac(q)) is not None:
            conditions.append(Client.mac_address == mac)
        conditions += [Client.mac_address.like(p) for p in mac_like_patterns(q)]
        if q.isdigit():
            conditions.append(Client.vid == int(q))
        stmt = stmt.where(or_(*conditions))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        (
            await db.execute(
                stmt.order_by(Client.last_seen_at.desc(), Client.mac_address)
                .limit(flt.limit)
                .offset(flt.offset)
            )
        )
        .tuples()
        .all()
    )

    macs = [c.mac_address for c, _ in rows]
    vendors = await vendors_for(db, macs)
    types = (await db.execute(select(MacType))).scalars().all()
    active_since = utcnow() - ACTIVE_WINDOW
    items = []
    for client, device_name in rows:
        mac_type = match_type(client.mac_address, types)
        items.append(
            {
                "id": client.id,
                "mac_address": client.mac_address,
                "ip_address": client.ip_address,
                "hostname": client.hostname,
                "vid": client.vid,
                "site_id": client.site_id,
                "device_id": client.device_id,
                "device_name": device_name,
                "port_id": client.port_id,
                "port_name": client.port_name,
                "vendor": vendors.get(client.mac_address),
                "type_name": mac_type.name if mac_type else None,
                "type_icon": mac_type.icon if mac_type else None,
                "first_seen_at": client.first_seen_at,
                "last_seen_at": client.last_seen_at,
                "active": ensure_utc(client.last_seen_at) >= active_since,
            }
        )
    return items, total
