"""The supported switch families. Each class only states how it differs from the standard."""

import re
from typing import ClassVar

from app.drivers import mib
from app.drivers.base import SnmpSwitchDriver
from app.drivers.mib import RawInterface
from app.models.device import DeviceModel
from app.transports.snmp import Oid, SnmpValue, column, parse_oid


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
    """HPE Aruba Networking CX (AOS-CX), verified with a 6100 on PL.10.11.

    AOS-CX has no Q-BRIDGE VLAN tables; VLANs and PVIDs come from IEEE8021-Q-BRIDGE-MIB.
    Only the static table is used: in the current table every member is reported as
    untagged.
    """

    model = DeviceModel.ARUBA_CX
    sys_object_ids = ("1.3.6.1.4.1.47196.4.1.1.1",)

    #: IEEE column -> Q-BRIDGE column with the same meaning
    _IEEE_TO_DOT1Q: ClassVar[dict[str, str]] = {
        mib.IEEE_Q_STATIC_NAME: mib.DOT1Q_STATIC_NAME,
        mib.IEEE_Q_STATIC_EGRESS: mib.DOT1Q_STATIC_EGRESS,
        mib.IEEE_Q_STATIC_UNTAGGED: mib.DOT1Q_STATIC_UNTAGGED,
        mib.IEEE_Q_PVID: mib.DOT1Q_PVID,
    }

    async def _vlan_rows(self) -> dict[Oid, SnmpValue]:
        rows = await self._walk_all(*self._IEEE_TO_DOT1Q)
        if not rows:  # agent with Q-BRIDGE after all
            return await super()._vlan_rows()
        result: dict[Oid, SnmpValue] = {}
        for ieee, dot1q in self._IEEE_TO_DOT1Q.items():
            target = parse_oid(dot1q)
            for index, value in column(rows, ieee).items():
                if len(index) == 2:  # (component, vid | bridge port): drop the component
                    result[target + index[1:]] = value
        return result

    def port_kind(self, iface: RawInterface):  # type: ignore[no-untyped-def]
        if iface.name.startswith("mgmt"):
            return None
        return super().port_kind(iface)
