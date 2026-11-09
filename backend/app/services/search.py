"""Global search (command palette): devices, ports, clients and VLANs in one query."""

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, DeviceVlan, Port
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

    if q.isdigit():
        vlans = (
            select(DeviceVlan, Device.name, Device.site_id)
            .join(Device, Device.id == DeviceVlan.device_id)
            .where(DeviceVlan.vid == int(q))
        )
        if sites is not None:
            vlans = vlans.where(Device.site_id.in_(sites))
        for vlan, device_name, site_id in (await db.execute(vlans.limit(PER_KIND))).tuples():
            hits.append(
                {
                    "kind": "vlan",
                    "title": f"VLAN {vlan.vid} {vlan.name}",
                    "subtitle": device_name,
                    "device_id": vlan.device_id,
                    "site_id": site_id,
                }
            )
    return hits
