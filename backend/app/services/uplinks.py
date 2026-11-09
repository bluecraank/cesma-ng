"""Which ports are uplinks (trunks to other switches)? One rule for the whole application.

A port is an uplink if it is a LAG, if its LLDP neighbour is a switch managed by cesma-ng,
or if it carries a large share of the switch's VLANs tagged.
"""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.switch import PortKind
from app.models import DeviceVlan, LldpNeighbor, Port, PortVlan

#: a port tagged in at least this share of the switch's VLANs is treated as uplink/trunk
UPLINK_VLAN_SHARE = 0.5
UPLINK_MIN_VLANS = 4


def is_uplink(kind: PortKind, tagged_count: int, device_vlan_count: int, to_switch: bool) -> bool:
    if kind is PortKind.LAG or to_switch:
        return True
    return tagged_count >= max(UPLINK_MIN_VLANS, device_vlan_count * UPLINK_VLAN_SHARE)


async def uplink_port_ids(db: AsyncSession, device_id: int | None = None) -> set[int]:
    """Ids of all uplink ports (of one device or of all devices)."""
    ports = select(Port.id, Port.device_id, Port.kind)
    tagged = (
        select(PortVlan.port_id, func.count()).where(PortVlan.tagged).group_by(PortVlan.port_id)
    )
    vlans = select(DeviceVlan.device_id, func.count()).group_by(DeviceVlan.device_id)
    to_switch = select(LldpNeighbor.port_id).where(LldpNeighbor.remote_device_id.is_not(None))
    if device_id is not None:
        ports = ports.where(Port.device_id == device_id)
        vlans = vlans.where(DeviceVlan.device_id == device_id)
        to_switch = to_switch.where(LldpNeighbor.device_id == device_id)

    tagged_counts = Counter({pid: n for pid, n in (await db.execute(tagged)).tuples()})
    vlan_counts = {did: n for did, n in (await db.execute(vlans)).tuples()}
    switch_ports = set((await db.execute(to_switch)).scalars())
    return {
        pid
        for pid, did, kind in (await db.execute(ports)).tuples()
        if is_uplink(kind, tagged_counts[pid], vlan_counts.get(did, 0), pid in switch_ports)
    }
