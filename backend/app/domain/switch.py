"""What a switch reports, independent of protocol and vendor.

Produced by drivers, stored by services.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class PortKind(StrEnum):
    ETHERNET = "ethernet"
    LAG = "lag"  # link aggregation / trunk / port-channel


class PoeStatus(StrEnum):
    DISABLED = "disabled"
    SEARCHING = "searching"
    DELIVERING = "delivering"
    FAULT = "fault"


@dataclass(frozen=True)
class SystemInfo:
    sys_name: str
    sys_descr: str
    sys_object_id: str
    uptime_seconds: int | None
    base_mac: str | None = None
    model_name: str | None = None
    serial_number: str | None = None
    firmware: str | None = None


@dataclass(frozen=True)
class Port:
    if_index: int
    name: str
    kind: PortKind
    description: str = ""
    admin_up: bool = True
    oper_up: bool = False
    speed_mbps: int | None = None
    mac_address: str | None = None
    pvid: int | None = None
    untagged_vlans: frozenset[int] = frozenset()
    tagged_vlans: frozenset[int] = frozenset()
    poe: PoeStatus | None = None


@dataclass(frozen=True)
class Vlan:
    vid: int
    name: str


@dataclass(frozen=True)
class FdbEntry:
    """A MAC address learned on a port (forwarding database)."""

    mac_address: str
    vid: int | None
    if_index: int | None


@dataclass(frozen=True)
class ArpEntry:
    ip_address: str
    mac_address: str
    if_index: int | None


@dataclass(frozen=True)
class LldpNeighbor:
    local_if_index: int | None
    local_port_name: str
    chassis_id: str
    port_id: str
    port_description: str = ""
    system_name: str = ""
    system_description: str = ""
    management_address: str | None = None


@dataclass(frozen=True)
class Inventory:
    """Result of one inventory poll."""

    system: SystemInfo
    ports: list[Port] = field(default_factory=list)
    vlans: list[Vlan] = field(default_factory=list)
