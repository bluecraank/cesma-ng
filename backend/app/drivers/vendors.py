"""The supported switch families. Each class only states how it differs from the standard."""

import re

from app.drivers.base import SnmpSwitchDriver
from app.drivers.mib import RawInterface
from app.models.device import DeviceModel


class DellN1500Driver(SnmpSwitchDriver):
    """Dell N1548P and other N1500 models (DNOS 6). Configuration via SSH CLI (phase 3)."""

    model = DeviceModel.DELL_N1500
    sys_object_ids = ("1.3.6.1.4.1.674.10895",)

    def poe_if_index(
        self, group: int, port: int, interfaces: dict[int, RawInterface]
    ) -> int | None:
        # group = stack unit, port = port on that unit -> "Gi<unit>/0/<port>"
        name = f"Gi{group}/0/{port}"
        return next((i.if_index for i in interfaces.values() if i.name == name), None)


class DellOs10Driver(SnmpSwitchDriver):
    """Dell PowerSwitch with SmartFabric OS10."""

    model = DeviceModel.DELL_OS10
    sys_object_ids = ("1.3.6.1.4.1.674.11000.5000.100",)

    def port_kind(self, iface: RawInterface):  # type: ignore[no-untyped-def]
        if iface.name.startswith("mgmt"):  # out-of-band management port
            return None
        return super().port_kind(iface)

    def vlan_name(self, vid: int, static_name: str, interfaces: dict[int, RawInterface]) -> str:
        # OS10 reports "vlan<id>" as name; the configured description is on the VLAN interface.
        alias = next((i.alias for i in interfaces.values() if i.name == f"vlan{vid}"), "")
        return alias or static_name

    def firmware_from_descr(self, sys_descr: str) -> str | None:
        match = re.search(r"OS Version:\s*([\w.\-]+)", sys_descr)
        return match.group(1).rstrip(".") if match else None


class ArubaOsSwitchDriver(SnmpSwitchDriver):
    """HP/Aruba 2530 and other ArubaOS-Switch (ProCurve) models."""

    model = DeviceModel.ARUBA_OS_SWITCH
    sys_object_ids = ("1.3.6.1.4.1.11.2.3.7.11",)

    def firmware_from_descr(self, sys_descr: str) -> str | None:
        match = re.search(r"revision ([\w.]+)", sys_descr)
        return match.group(1) if match else None


class ArubaCxDriver(SnmpSwitchDriver):
    """HPE Aruba Networking CX (AOS-CX). SNMP baseline; details via REST follow.

    Not yet verified against a recording of a real device.
    """

    model = DeviceModel.ARUBA_CX
    sys_object_ids = ("1.3.6.1.4.1.47196.4.1.1.1",)

    def port_kind(self, iface: RawInterface):  # type: ignore[no-untyped-def]
        if iface.name.startswith("mgmt"):
            return None
        return super().port_kind(iface)
