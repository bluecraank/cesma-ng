"""Network map from LLDP: managed switches as nodes, LLDP links as edges."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, LldpNeighbor, Port, SiteRole
from app.services.access import require_site_role
from app.services.context import Caller


async def site_topology(
    db: AsyncSession, caller: Caller, site_id: int, *, include_external: bool = False
) -> dict[str, list[dict[str, Any]]]:
    require_site_role(caller.user, site_id, SiteRole.VIEWER)
    devices = {
        d.id: d
        for d in (await db.execute(select(Device).where(Device.site_id == site_id))).scalars()
    }
    nodes: list[dict[str, Any]] = [
        {
            "id": f"d{d.id}",
            "device_id": d.id,
            "label": d.name,
            "kind": "switch",
            "status": d.status.value,
            "model": d.model_name or d.model.value,
        }
        for d in devices.values()
    ]
    if not devices:
        return {"nodes": [], "edges": []}

    rows = await db.execute(
        select(LldpNeighbor, Port.oper_up, Port.speed_mbps)
        .outerjoin(Port, Port.id == LldpNeighbor.port_id)
        .where(LldpNeighbor.device_id.in_(devices))
    )
    edges: dict[frozenset[str], dict[str, Any]] = {}
    external: dict[str, dict[str, Any]] = {}
    for neighbor, oper_up, speed in rows.tuples():
        source = f"d{neighbor.device_id}"
        remote_id = neighbor.remote_device_id
        if remote_id is not None and remote_id in devices:
            target = f"d{remote_id}"
        elif include_external and (neighbor.system_name or neighbor.chassis_id):
            target = f"x{neighbor.chassis_id}"
            external.setdefault(
                target,
                {
                    "id": target,
                    "device_id": None,
                    "label": neighbor.system_name or neighbor.chassis_id,
                    "kind": "external",
                    "status": "unknown",
                    "model": (neighbor.system_description or "").split("\n")[0][:60],
                },
            )
        else:
            continue
        # Both switches report the same link: keep one edge per unordered pair of ports.
        remote_port = neighbor.remote_port_description or neighbor.remote_port
        key = frozenset({f"{source}:{neighbor.local_port_name}", f"{target}:{remote_port}"})
        if key in edges:
            continue
        edges[key] = {
            "id": f"e{neighbor.id}",
            "source": source,
            "target": target,
            "source_port": neighbor.local_port_name,
            "target_port": neighbor.remote_port_description or neighbor.remote_port,
            "up": oper_up if oper_up is not None else True,
            "speed_mbps": speed,
        }
    return {"nodes": nodes + list(external.values()), "edges": list(edges.values())}
