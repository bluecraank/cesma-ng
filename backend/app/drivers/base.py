"""Driver capabilities and the SNMP based driver that all supported switches share.

A driver turns protocol data into domain objects. It never touches the database. Vendor
differences are small overridable hooks instead of copied methods.
"""

from typing import ClassVar, Protocol, runtime_checkable

from app.domain.switch import (
    ArpEntry,
    FdbEntry,
    Inventory,
    LldpNeighbor,
    PoeStatus,
    Port,
    PortKind,
    SystemInfo,
    Vlan,
)
from app.drivers import mib
from app.drivers.mib import RawInterface, VlanTable
from app.models.device import DeviceModel
from app.transports.snmp import Oid, SnmpClient, SnmpError, SnmpValue, column, parse_oid

# --- Capabilities ----------------------------------------------------------------------------


@runtime_checkable
class InventoryReader(Protocol):
    async def read_inventory(self) -> Inventory: ...


@runtime_checkable
class FdbReader(Protocol):
    async def read_fdb(self) -> list[FdbEntry]: ...


@runtime_checkable
class ArpReader(Protocol):
    async def read_arp(self) -> list[ArpEntry]: ...


@runtime_checkable
class LldpReader(Protocol):
    async def read_lldp(self) -> list[LldpNeighbor]: ...


# --- SNMP driver -----------------------------------------------------------------------------


class SnmpSwitchDriver:
    """Reads a switch via standard MIBs. Subclasses set the model and override hooks."""

    model: ClassVar[DeviceModel]
    #: sysObjectID prefixes used for automatic model detection
    sys_object_ids: ClassVar[tuple[str, ...]] = ()

    def __init__(self, snmp: SnmpClient) -> None:
        self.snmp = snmp

    # -- reading ------------------------------------------------------------------------------

    async def read_system(self) -> SystemInfo:
        values = await self.snmp.get(
            [mib.SYS_DESCR, mib.SYS_OBJECT_ID, mib.SYS_UPTIME, mib.SYS_NAME]
        )
        if not values:
            raise SnmpError("No answer to system group")
        get = {".".join(map(str, k)): v for k, v in values.items()}  # by OID text
        entity = mib.parse_entity(await self.snmp.walk(mib.ENT_PHYSICAL))
        bridge = await self.snmp.get([mib.BRIDGE_BASE_ADDRESS])
        base_mac = mib.mac(bridge.get(parse_oid(mib.BRIDGE_BASE_ADDRESS)))
        uptime = mib.integer(get.get(mib.SYS_UPTIME))
        descr = mib.text(get.get(mib.SYS_DESCR))
        return SystemInfo(
            sys_name=mib.text(get.get(mib.SYS_NAME)),
            sys_descr=descr,
            sys_object_id=mib.text(get.get(mib.SYS_OBJECT_ID)),
            uptime_seconds=uptime // 100 if uptime is not None else None,
            base_mac=base_mac,
            model_name=entity.model_name,
            serial_number=entity.serial_number,
            firmware=entity.software_revision or self.firmware_from_descr(descr),
        )

    async def _walk_all(self, *bases: str) -> dict[Oid, SnmpValue]:
        rows: dict[Oid, SnmpValue] = {}
        for base in bases:
            rows.update(await self.snmp.walk(base))
        return rows

    async def _interfaces(self) -> dict[int, RawInterface]:
        return mib.parse_interfaces(await self._walk_all(mib.IF_TABLE, mib.IFX_TABLE))

    async def _bridge_ports(self) -> dict[int, int]:
        return mib.parse_bridge_ports(await self.snmp.walk(mib.BRIDGE_PORT_IF_INDEX))

    async def read_inventory(self) -> Inventory:
        system = await self.read_system()
        interfaces = await self._interfaces()
        bridge_ports = await self._bridge_ports()
        q_rows = await self._walk_all(
            mib.DOT1Q_STATIC_NAME,
            mib.DOT1Q_STATIC_EGRESS,
            mib.DOT1Q_STATIC_UNTAGGED,
            mib.DOT1Q_PVID,
        )
        if not column(q_rows, mib.DOT1Q_STATIC_EGRESS):  # no static table: use current
            q_rows.update(
                await self._walk_all(mib.DOT1Q_CURRENT_EGRESS, mib.DOT1Q_CURRENT_UNTAGGED)
            )
        vlan_table = mib.parse_vlans(q_rows, bridge_ports)
        pvids = mib.parse_pvids(q_rows, bridge_ports)
        poe_rows = await self._walk_all(mib.PETH_PORT_ADMIN, mib.PETH_PORT_DETECTION)
        poe = mib.parse_poe(poe_rows)

        ports = self._build_ports(interfaces, vlan_table, pvids, poe)
        vlans = [
            Vlan(vid, self.vlan_name(vid, vlan_table.names[vid], interfaces))
            for vid in sorted(vlan_table.names)
        ]
        return Inventory(system=system, ports=ports, vlans=vlans)

    def _build_ports(
        self,
        interfaces: dict[int, RawInterface],
        vlans: VlanTable,
        pvids: dict[int, int],
        poe: dict[tuple[int, int], PoeStatus],
    ) -> list[Port]:
        poe_by_if = {
            if_index: status
            for (group, port), status in poe.items()
            if (if_index := self.poe_if_index(group, port, interfaces)) is not None
        }
        ports = []
        for iface in sorted(interfaces.values(), key=lambda i: i.if_index):
            kind = self.port_kind(iface)
            if kind is None:
                continue
            untagged = frozenset(
                v for v, members in vlans.untagged.items() if iface.if_index in members
            )
            tagged = frozenset(
                v for v, members in vlans.tagged.items() if iface.if_index in members
            )
            if kind is PortKind.LAG and not self.lag_in_use(iface):
                continue
            pvid = pvids.get(iface.if_index)
            if pvid not in untagged | tagged:
                # HP reports PVID 1 for tagged-only ports; OS10 reports no PVID at all.
                pvid = next(iter(untagged)) if len(untagged) == 1 else None
            ports.append(
                Port(
                    if_index=iface.if_index,
                    name=iface.name,
                    kind=kind,
                    description=iface.alias,
                    admin_up=iface.admin_up,
                    oper_up=iface.oper_up,
                    speed_mbps=iface.speed_mbps,
                    mac_address=iface.mac_address,
                    pvid=pvid,
                    untagged_vlans=untagged,
                    tagged_vlans=tagged,
                    poe=poe_by_if.get(iface.if_index),
                )
            )
        return ports

    async def read_link_states(self) -> dict[int, bool]:
        """Only the link state per ifIndex: one small walk, for the live port finder."""
        rows = await self.snmp.walk(mib.IF_OPER)
        return {
            idx[0]: mib.integer(v) == 1
            for idx, v in column(rows, mib.IF_OPER).items()
            if len(idx) == 1
        }

    async def read_fdb(self) -> list[FdbEntry]:
        rows = await self._walk_all(mib.DOT1Q_VLAN_FDB_ID, mib.DOT1Q_FDB_PORT, mib.DOT1Q_FDB_STATUS)
        if not column(rows, mib.DOT1Q_FDB_PORT):  # no Q-BRIDGE: plain BRIDGE-MIB
            rows.update(await self._walk_all(mib.DOT1D_FDB_PORT, mib.DOT1D_FDB_STATUS))
        return mib.parse_fdb(rows, await self._bridge_ports())

    async def read_arp(self) -> list[ArpEntry]:
        rows = await self._walk_all(mib.IP_NET_TO_PHYSICAL_PHYS, mib.IP_NET_TO_MEDIA_PHYS)
        return mib.parse_arp(rows)

    async def read_lldp(self) -> list[LldpNeighbor]:
        rows = await self._walk_all(
            mib.LLDP_LOC_PORT_ID, mib.LLDP_LOC_PORT_DESC, mib.LLDP_REM, mib.LLDP_REM_MAN_ADDR_IF_ID
        )
        return mib.parse_lldp(rows, await self._interfaces())

    async def read_counters(self) -> dict[int, mib.Counters]:
        rows = await self._walk_all(
            mib.IF_HC_IN_OCTETS, mib.IF_HC_OUT_OCTETS, mib.IF_IN_ERRORS, mib.IF_OUT_ERRORS
        )
        if not column(rows, mib.IF_HC_IN_OCTETS):  # old agents without ifXTable counters
            rows.update(await self._walk_all(mib.IF_IN_OCTETS, mib.IF_OUT_OCTETS))
        return mib.parse_counters(rows)

    # -- vendor hooks -------------------------------------------------------------------------

    @classmethod
    def matches(cls, sys_object_id: str, sys_descr: str) -> bool:
        return any(
            sys_object_id == p or sys_object_id.startswith(p + ".") for p in cls.sys_object_ids
        )

    def port_kind(self, iface: RawInterface) -> PortKind | None:
        """Which interfaces are switch ports. Default: Ethernet and LAG interfaces."""
        if iface.if_type == mib.IF_TYPE_ETHERNET:
            return PortKind.ETHERNET
        if iface.if_type == mib.IF_TYPE_LAG:
            return PortKind.LAG
        return None

    def lag_in_use(self, iface: RawInterface) -> bool:
        """Many switches list every possible LAG; hide unconfigured ones."""
        return iface.oper_up or bool(iface.alias)

    def vlan_name(self, vid: int, static_name: str, interfaces: dict[int, RawInterface]) -> str:
        return static_name

    def poe_if_index(
        self, group: int, port: int, interfaces: dict[int, RawInterface]
    ) -> int | None:
        """pethPsePortTable is indexed (group, port); default: group 1, port = ifIndex."""
        return port if group == 1 and port in interfaces else None

    def firmware_from_descr(self, sys_descr: str) -> str | None:
        return None
