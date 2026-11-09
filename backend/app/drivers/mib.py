"""Parsers for standard MIBs (IF-MIB, BRIDGE/Q-BRIDGE, LLDP, ENTITY, POWER-ETHERNET, IP-MIB).

Pure functions over walked rows: no vendor decisions, no I/O. Drivers combine them.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.switch import ArpEntry, FdbEntry, LldpNeighbor, PoeStatus
from app.transports.snmp import Oid, SnmpValue, column

# --- OIDs ------------------------------------------------------------------------------------

SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"

IF_TABLE = "1.3.6.1.2.1.2.2.1"
IF_DESCR, IF_TYPE, IF_SPEED, IF_PHYS_ADDRESS, IF_ADMIN, IF_OPER = (
    f"{IF_TABLE}.{c}" for c in (2, 3, 5, 6, 7, 8)
)
IFX_TABLE = "1.3.6.1.2.1.31.1.1.1"
IF_NAME, IF_HIGH_SPEED, IF_ALIAS = (f"{IFX_TABLE}.{c}" for c in (1, 15, 18))
IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS = (f"{IFX_TABLE}.{c}" for c in (6, 10))
IF_IN_OCTETS, IF_IN_ERRORS, IF_OUT_OCTETS, IF_OUT_ERRORS = (
    f"{IF_TABLE}.{c}" for c in (10, 14, 16, 20)
)

BRIDGE_BASE_ADDRESS = "1.3.6.1.2.1.17.1.1.0"
BRIDGE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"
DOT1D_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"
DOT1D_FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3"
DOT1Q_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"
DOT1Q_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3"
DOT1Q_VLAN_FDB_ID = "1.3.6.1.2.1.17.7.1.4.2.1.3"
DOT1Q_CURRENT_EGRESS = "1.3.6.1.2.1.17.7.1.4.2.1.4"
DOT1Q_CURRENT_UNTAGGED = "1.3.6.1.2.1.17.7.1.4.2.1.5"
DOT1Q_STATIC_NAME = "1.3.6.1.2.1.17.7.1.4.3.1.1"
DOT1Q_STATIC_EGRESS = "1.3.6.1.2.1.17.7.1.4.3.1.2"
DOT1Q_STATIC_UNTAGGED = "1.3.6.1.2.1.17.7.1.4.3.1.4"
DOT1Q_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"

ENT_PHYSICAL = "1.3.6.1.2.1.47.1.1.1.1"
ENT_CLASS, ENT_SOFTWARE_REV, ENT_SERIAL, ENT_MODEL = (
    f"{ENT_PHYSICAL}.{c}" for c in (5, 10, 11, 13)
)
ENT_CLASS_CHASSIS = 3

PETH_PORT_ADMIN = "1.3.6.1.2.1.105.1.1.1.3"
PETH_PORT_DETECTION = "1.3.6.1.2.1.105.1.1.1.6"

LLDP_LOC_PORT_ID_SUBTYPE = "1.0.8802.1.1.2.1.3.7.1.2"
LLDP_LOC_PORT_ID = "1.0.8802.1.1.2.1.3.7.1.3"
LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
LLDP_REM = "1.0.8802.1.1.2.1.4.1.1"
LLDP_REM_MAN_ADDR_IF_ID = "1.0.8802.1.1.2.1.4.2.1.3"

IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"
IP_NET_TO_PHYSICAL_PHYS = "1.3.6.1.2.1.4.35.1.4"

IF_TYPE_ETHERNET = 6
IF_TYPE_LAG = 161

Rows = Mapping[Oid, SnmpValue]

# --- Value helpers ---------------------------------------------------------------------------


def text(value: SnmpValue) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    return "" if value is None else str(value).strip()


def mac(value: SnmpValue | bytes | tuple[int, ...]) -> str | None:
    raw = bytes(value) if isinstance(value, (bytes, tuple)) else None
    if raw is None or len(raw) != 6 or raw == bytes(6):
        return None
    return ":".join(f"{b:02x}" for b in raw)


def integer(value: SnmpValue) -> int | None:
    return value if isinstance(value, int) else None


def bitmap_ports(raw: SnmpValue) -> set[int]:
    """Q-BRIDGE PortList: the first bit of the first byte is bridge port 1."""
    if not isinstance(raw, bytes):
        return set()
    return {
        i * 8 + bit + 1 for i, byte in enumerate(raw) for bit in range(8) if byte & (0x80 >> bit)
    }


def _printable_or_hex(raw: SnmpValue) -> str:
    if isinstance(raw, bytes):
        try:
            decoded = raw.decode("ascii")
            if decoded.isprintable():
                return decoded.strip()
        except UnicodeDecodeError:
            pass
        return ":".join(f"{b:02x}" for b in raw)
    return text(raw)


def _single_index(rows: Rows, base: str) -> dict[int, SnmpValue]:
    return {idx[0]: v for idx, v in column(rows, base).items() if len(idx) == 1}


# --- System / entity -------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityInfo:
    model_name: str | None
    serial_number: str | None
    software_revision: str | None


def parse_entity(rows: Rows) -> EntityInfo:
    """First chassis with a model name (stack master / standalone switch)."""
    classes = _single_index(rows, ENT_CLASS)
    models = _single_index(rows, ENT_MODEL)
    serials = _single_index(rows, ENT_SERIAL)
    software = _single_index(rows, ENT_SOFTWARE_REV)
    for index in sorted(i for i, c in classes.items() if c == ENT_CLASS_CHASSIS):
        if model := text(models.get(index)):
            return EntityInfo(
                model, text(serials.get(index)) or None, text(software.get(index)) or None
            )
    return EntityInfo(None, None, None)


# --- Interfaces ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawInterface:
    if_index: int
    if_type: int
    name: str
    descr: str
    alias: str
    admin_up: bool
    oper_up: bool
    speed_mbps: int | None
    mac_address: str | None


def parse_interfaces(rows: Rows) -> dict[int, RawInterface]:
    types = _single_index(rows, IF_TYPE)
    descr = _single_index(rows, IF_DESCR)
    names = _single_index(rows, IF_NAME)
    aliases = _single_index(rows, IF_ALIAS)
    admin = _single_index(rows, IF_ADMIN)
    oper = _single_index(rows, IF_OPER)
    high_speed = _single_index(rows, IF_HIGH_SPEED)
    speed = _single_index(rows, IF_SPEED)
    phys = _single_index(rows, IF_PHYS_ADDRESS)

    result = {}
    for index, if_type in types.items():
        oper_up = oper.get(index) == 1
        mbps = integer(high_speed.get(index)) or (integer(speed.get(index)) or 0) // 1_000_000
        result[index] = RawInterface(
            if_index=index,
            if_type=integer(if_type) or 0,
            name=text(names.get(index)) or text(descr.get(index)),
            descr=text(descr.get(index)),
            alias=text(aliases.get(index)),
            admin_up=admin.get(index) == 1,
            oper_up=oper_up,
            # Current speed only makes sense on a link that is up.
            speed_mbps=mbps if oper_up and mbps else None,
            mac_address=mac(phys.get(index)),
        )
    return result


# --- Bridge / VLANs --------------------------------------------------------------------------


def parse_bridge_ports(rows: Rows) -> dict[int, int]:
    """Bridge port number -> ifIndex (they differ e.g. on Dell OS10)."""
    return {
        port: if_index
        for port, value in _single_index(rows, BRIDGE_PORT_IF_INDEX).items()
        if (if_index := integer(value))
    }


@dataclass(frozen=True)
class VlanTable:
    names: dict[int, str]
    untagged: dict[int, set[int]]  # vid -> ifIndexes
    tagged: dict[int, set[int]]


def parse_vlans(rows: Rows, bridge_ports: Mapping[int, int]) -> VlanTable:
    """VLANs and memberships from the static (configured) table, else the current one."""

    def to_if_indexes(raw: SnmpValue) -> set[int]:
        return {bridge_ports.get(p, p) for p in bitmap_ports(raw)}

    static_names = {i[-1]: text(v) for i, v in column(rows, DOT1Q_STATIC_NAME).items()}
    static_egress = {i[-1]: v for i, v in column(rows, DOT1Q_STATIC_EGRESS).items()}
    if static_egress:
        egress, untagged_raw = (
            static_egress,
            {i[-1]: v for i, v in column(rows, DOT1Q_STATIC_UNTAGGED).items()},
        )
    else:  # index of the current table: (timeMark, vid)
        egress = {i[-1]: v for i, v in column(rows, DOT1Q_CURRENT_EGRESS).items()}
        untagged_raw = {i[-1]: v for i, v in column(rows, DOT1Q_CURRENT_UNTAGGED).items()}

    vids = set(static_names) | set(egress)
    untagged = {vid: to_if_indexes(untagged_raw.get(vid)) for vid in vids}
    tagged = {vid: to_if_indexes(egress.get(vid)) - untagged[vid] for vid in vids}
    return VlanTable(
        names={vid: static_names.get(vid, "") for vid in vids}, untagged=untagged, tagged=tagged
    )


def parse_pvids(rows: Rows, bridge_ports: Mapping[int, int]) -> dict[int, int]:
    """ifIndex -> PVID (native/untagged VLAN for ingress)."""
    return {
        bridge_ports.get(port, port): pvid
        for port, value in _single_index(rows, DOT1Q_PVID).items()
        if (pvid := integer(value))
    }


# --- Forwarding database ---------------------------------------------------------------------

_FDB_LEARNED, _FDB_MGMT = 3, 5


def parse_fdb(rows: Rows, bridge_ports: Mapping[int, int]) -> list[FdbEntry]:
    """Learned and static MAC addresses per port. Q-BRIDGE preferred, BRIDGE-MIB as fallback."""
    # The FDB index is a filtering database id, which is *not* always the VLAN id (HP!).
    fdb_to_vid = {
        fdb_id: index[-1]
        for index, value in column(rows, DOT1Q_VLAN_FDB_ID).items()
        if (fdb_id := integer(value)) is not None
    }
    q_ports = column(rows, DOT1Q_FDB_PORT)
    if q_ports:
        status = column(rows, DOT1Q_FDB_STATUS)
        entries = []
        for index, port in q_ports.items():
            if len(index) != 7 or status.get(index, _FDB_LEARNED) not in (_FDB_LEARNED, _FDB_MGMT):
                continue
            address = mac(index[1:])
            if address is None:
                continue
            fdb_id = index[0]
            vid = fdb_to_vid.get(fdb_id, fdb_id if not fdb_to_vid else None)
            entries.append(FdbEntry(address, vid, _if_index(port, bridge_ports)))
        return entries

    status = column(rows, DOT1D_FDB_STATUS)
    return [
        FdbEntry(address, None, _if_index(port, bridge_ports))
        for index, port in column(rows, DOT1D_FDB_PORT).items()
        if status.get(index, _FDB_LEARNED) in (_FDB_LEARNED, _FDB_MGMT)
        and (address := mac(index)) is not None
    ]


def _if_index(bridge_port: SnmpValue, bridge_ports: Mapping[int, int]) -> int | None:
    port = integer(bridge_port)
    if not port:  # 0 = learned on the CPU / unknown
        return None
    return bridge_ports.get(port, port)


# --- ARP -------------------------------------------------------------------------------------


def parse_arp(rows: Rows) -> list[ArpEntry]:
    """IPv4 neighbours from ipNetToPhysicalTable and the older ipNetToMediaTable."""
    found: dict[tuple[str, str], ArpEntry] = {}
    # ipNetToPhysical index: ifIndex, addressType (1 = IPv4), length (4), a, b, c, d
    for index, value in column(rows, IP_NET_TO_PHYSICAL_PHYS).items():
        if len(index) == 7 and index[1:3] == (1, 4) and (address := mac(value)):
            ip = ".".join(map(str, index[3:]))
            found[(ip, address)] = ArpEntry(ip, address, index[0])
    # ipNetToMedia index: ifIndex, a, b, c, d
    for index, value in column(rows, IP_NET_TO_MEDIA_PHYS).items():
        if len(index) == 5 and (address := mac(value)):
            ip = ".".join(map(str, index[1:]))
            found.setdefault((ip, address), ArpEntry(ip, address, index[0]))
    return list(found.values())


# --- LLDP ------------------------------------------------------------------------------------

_CHASSIS_MAC, _CHASSIS_NETWORK = 4, 5
_PORT_MAC, _PORT_NETWORK = 3, 4


def _network_address(raw: SnmpValue) -> str:
    """LLDP network address: first byte is the IANA family (1 = IPv4)."""
    if isinstance(raw, bytes) and len(raw) == 5 and raw[0] == 1:
        return ".".join(str(b) for b in raw[1:])
    return _printable_or_hex(raw)


def parse_lldp(rows: Rows, interfaces: Mapping[int, RawInterface]) -> list[LldpNeighbor]:
    by_name = {i.name: i.if_index for i in interfaces.values()}
    loc_ids = _single_index(rows, LLDP_LOC_PORT_ID)
    loc_descr = _single_index(rows, LLDP_LOC_PORT_DESC)

    def local_port(port_num: int) -> tuple[int | None, str]:
        """LLDP numbers local ports itself; resolve to ifIndex via the port id / name."""
        port_id = text(loc_ids.get(port_num))
        if port_id in by_name:
            return by_name[port_id], port_id
        if (iface := interfaces.get(port_num)) and (
            not loc_descr or text(loc_descr.get(port_num)) in (iface.descr, iface.name)
        ):
            return iface.if_index, iface.name
        return None, port_id or str(port_num)

    def rem(col: int) -> dict[Oid, SnmpValue]:
        return column(rows, f"{LLDP_REM}.{col}")

    chassis_subtype, chassis_id = rem(4), rem(5)
    port_subtype, port_id = rem(6), rem(7)
    port_desc, sys_name, sys_desc = rem(8), rem(9), rem(10)

    man_addr: dict[Oid, str] = {}
    # index: timeMark, localPortNum, remIndex, addrSubtype, addrLen, address...
    for index, _ in column(rows, LLDP_REM_MAN_ADDR_IF_ID).items():
        if len(index) == 9 and index[3:5] == (1, 4):
            man_addr.setdefault(index[:3], ".".join(map(str, index[5:])))

    neighbors = []
    for index in sorted(set(chassis_id) | set(sys_name)):
        if len(index) != 3:
            continue
        local_if_index, local_name = local_port(index[1])
        chassis_raw = chassis_id.get(index)
        match chassis_subtype.get(index):
            case 4:
                chassis = mac(chassis_raw) or _printable_or_hex(chassis_raw)
            case 5:
                chassis = _network_address(chassis_raw)
            case _:
                chassis = _printable_or_hex(chassis_raw)
        port_raw = port_id.get(index)
        match port_subtype.get(index):
            case 3:
                port = mac(port_raw) or _printable_or_hex(port_raw)
            case 4:
                port = _network_address(port_raw)
            case _:
                port = _printable_or_hex(port_raw)
        neighbors.append(
            LldpNeighbor(
                local_if_index=local_if_index,
                local_port_name=local_name,
                chassis_id=chassis,
                port_id=port,
                port_description=text(port_desc.get(index)),
                system_name=text(sys_name.get(index)),
                system_description=text(sys_desc.get(index)),
                management_address=man_addr.get(index),
            )
        )
    return neighbors


# --- PoE -------------------------------------------------------------------------------------

_DETECTION = {
    1: PoeStatus.DISABLED,
    2: PoeStatus.SEARCHING,
    3: PoeStatus.DELIVERING,
    4: PoeStatus.FAULT,
    5: PoeStatus.SEARCHING,  # test
    6: PoeStatus.FAULT,  # otherFault
}


def parse_poe(rows: Rows) -> dict[tuple[int, int], PoeStatus]:
    """(group, port) -> status. Mapping to ifIndex is vendor specific (see drivers)."""
    admin = column(rows, PETH_PORT_ADMIN)
    result = {}
    for index, value in column(rows, PETH_PORT_DETECTION).items():
        if len(index) != 2:
            continue
        if admin.get(index) == 2:
            result[(index[0], index[1])] = PoeStatus.DISABLED
        elif (status := _DETECTION.get(integer(value) or 0)) is not None:
            result[(index[0], index[1])] = status
    return result


# --- Counters --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Counters:
    in_octets: int
    out_octets: int
    in_errors: int
    out_errors: int


def parse_counters(rows: Rows) -> dict[int, Counters]:
    """Traffic and error counters per ifIndex; 64 bit counters preferred over 32 bit ones."""
    hc_in, hc_out = _single_index(rows, IF_HC_IN_OCTETS), _single_index(rows, IF_HC_OUT_OCTETS)
    in32, out32 = _single_index(rows, IF_IN_OCTETS), _single_index(rows, IF_OUT_OCTETS)
    in_err, out_err = _single_index(rows, IF_IN_ERRORS), _single_index(rows, IF_OUT_ERRORS)
    result = {}
    for index in set(hc_in) | set(in32):
        result[index] = Counters(
            in_octets=integer(hc_in.get(index, in32.get(index))) or 0,
            out_octets=integer(hc_out.get(index, out32.get(index))) or 0,
            in_errors=integer(in_err.get(index)) or 0,
            out_errors=integer(out_err.get(index)) or 0,
        )
    return result
