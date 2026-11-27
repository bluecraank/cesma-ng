"""Global search (command palette): devices, ports, clients and VLANs in one query."""

from typing import Any

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, DeviceVlan, Port, SiteVlan
from app.services.access import visible_site_ids
from app.services.clients import ClientFilter, search_clients
from app.services.context import Caller

PER_KIND = 6


async def search(db: AsyncSession, caller: Caller, query: str) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < 2:
        return []
    sites = visible_site_ids(caller.user)
    hits: list[dict[str, Any]] = []

    devices = select(Device).where(
        or_(
            Device.name.ilike(f"%{q}%"),
            Device.hostname.ilike(f"%{q}%"),
            Device.ip_address.ilike(f"%{q}%"),
            Device.dns_name.ilike(f"%{q}%"),
            Device.sys_name.ilike(f"%{q}%"),
            Device.serial_number.ilike(f"%{q}%"),
            Device.mac_address == q.lower(),
        )
    )
    if sites is not None:
        devices = devices.where(Device.site_id.in_(sites))
    for d in (await db.execute(devices.order_by(Device.name).limit(PER_KIND))).scalars():
        hits.append(
            {
                "kind": "device",
                "title": d.name,
                "subtitle": f"{d.hostname} · {d.model_name or d.model}",
                "device_id": d.id,
                "site_id": d.site_id,
            }
        )

    ports = (
        select(Port, Device.name, Device.site_id)
        .join(Device, Device.id == Port.device_id)
        .where(Port.description.ilike(f"%{q}%"))
    )
    if sites is not None:
        ports = ports.where(Device.site_id.in_(sites))
    for port, device_name, site_id in (await db.execute(ports.limit(PER_KIND))).tuples():
        hits.append(
            {
                "kind": "port",
                "title": f"{device_name} {port.name}",
                "subtitle": port.description,
                "device_id": port.device_id,
                "port_id": port.id,
                "site_id": site_id,
            }
        )

    clients, _ = await search_clients(db, caller, ClientFilter(query=q, limit=PER_KIND))
    for c in clients:
        where = f"{c['device_name']} {c['port_name']}" if c["device_name"] else ""
        hits.append(
            {
                "kind": "client",
                "title": c["hostname"] or c["ip_address"] or c["mac_address"],
                "subtitle": " · ".join(x for x in (c["mac_address"], c["ip_address"], where) if x),
                "device_id": c["device_id"],
                "port_id": c["port_id"],
                "site_id": c["site_id"],
                "query": c["mac_address"],
            }
        )

    vlans = await _vlans(db, q, sites)
    # a plain number is most likely a VLAN: show those first
    return vlans + hits if q.isdigit() else hits + vlans


async def _vlans(db: AsyncSession, q: str, sites: set[int] | None) -> list[dict[str, Any]]:
    """One hit per VLAN and site, by number, name or description.

    The site's VLAN list (page "VLANs") and VLANs only found on its switches, with the
    number of switches that have them.
    """
    like = f"%{q}%"
    number = int(q) if q.isdigit() else None
    found: dict[tuple[int, int], dict[str, Any]] = {}

    wanted = select(SiteVlan).where(
        or_(
            SiteVlan.vid == number if number is not None else false(),
            SiteVlan.name.ilike(like),
            SiteVlan.description.ilike(like),
        )
    )
    if sites is not None:
        wanted = wanted.where(SiteVlan.site_id.in_(sites))
    for v in (await db.execute(wanted.order_by(SiteVlan.vid).limit(PER_KIND))).scalars():
        found[(v.site_id, v.vid)] = _vlan_hit(v.site_id, v.vid, v.name, v.description)

    on_switches = (
        select(
            Device.site_id,
            DeviceVlan.vid,
            func.max(DeviceVlan.name),
            func.count(),
            func.min(DeviceVlan.device_id),
        )
        .join(Device, Device.id == DeviceVlan.device_id)
        .where(
            or_(
                DeviceVlan.vid == number if number is not None else false(),
                DeviceVlan.name.ilike(like),
            )
        )
        .group_by(Device.site_id, DeviceVlan.vid)
        .order_by(DeviceVlan.vid)
        .limit(PER_KIND)
    )
    if sites is not None:
        on_switches = on_switches.where(Device.site_id.in_(sites))
    for site_id, vid, name, count, device_id in (await db.execute(on_switches)).tuples():
        hit = found.get((site_id, vid))
        if hit is None:  # not in the site's list: the result opens a switch that has it
            hit = found[(site_id, vid)] = _vlan_hit(site_id, vid, name or "", "")
            hit["device_id"] = device_id
        hit["switches"] = count
    hits = sorted(found.values(), key=lambda h: (h["vid"], h["site_id"]))
    return hits[:PER_KIND]


def _vlan_hit(site_id: int, vid: int, name: str, description: str) -> dict[str, Any]:
    return {
        "kind": "vlan",
        "title": f"VLAN {vid} {name}".strip(),
        "subtitle": description,
        "site_id": site_id,
        "vid": vid,
        "switches": 0,
    }
