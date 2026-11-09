"""Drivers against anonymised recordings of real switches (tests/fixtures/snmp)."""

from pathlib import Path

import pytest

from app.domain.switch import Inventory, PoeStatus, Port, PortKind
from app.drivers import mib
from app.drivers.base import SnmpSwitchDriver
from app.drivers.registry import detect, driver_for
from app.models import DeviceModel
from app.transports.snmp import RecordedSnmpClient

FIXTURES = Path(__file__).parent / "fixtures" / "snmp"


async def _driver(name: str) -> SnmpSwitchDriver:
    client = RecordedSnmpClient.from_file(FIXTURES / f"{name}.snmprec")
    detection = await detect(client)
    assert detection.model is not None
    return driver_for(detection.model, client)


def _port(inventory: Inventory, name: str) -> Port:
    return next(p for p in inventory.ports if p.name == name)


@pytest.mark.parametrize(
    ("fixture", "model", "model_name", "firmware"),
    [
        ("dell-n1548p", DeviceModel.DELL_N1500, "N1548P", "6.8.1.0"),
        ("dell-os10", DeviceModel.DELL_OS10, "S5248F-ON", "10.5.6.8"),
        ("hp-2530-48g", DeviceModel.ARUBA_OS_SWITCH, "J9775A", "YA.16.11.0008"),
    ],
)
async def test_model_detection_and_system_info(
    fixture: str, model: DeviceModel, model_name: str, firmware: str
) -> None:
    driver = await _driver(fixture)
    assert driver.model is model
    system = await driver.read_system()
    assert system.model_name == model_name
    assert system.firmware == firmware
    assert system.serial_number
    assert system.uptime_seconds and system.uptime_seconds > 86400
    assert system.base_mac and len(system.base_mac) == 17


# --- Dell N1548P -----------------------------------------------------------------------------


async def test_n1548p_ports_vlans_and_poe() -> None:
    inv = await (await _driver("dell-n1548p")).read_inventory()
    names = [p.name for p in inv.ports]
    assert len(names) == 52 and names[0] == "Gi1/0/1" and names[-1] == "Te1/0/4"
    assert all(p.kind is PortKind.ETHERNET for p in inv.ports)  # 64 unused Po* are hidden

    general = _port(inv, "Gi1/0/5")
    assert general.untagged_vlans == {581}
    assert general.tagged_vlans == {582, 584, 590, 592, 598}
    assert general.pvid == 581

    assert len(inv.vlans) == 33
    assert inv.vlans[0].vid == 1 and inv.vlans[0].name == "default"
    assert sum(p.poe is not None for p in inv.ports) == 48
    assert _port(inv, "Te1/0/1").poe is None  # uplinks have no PoE
    assert _port(inv, "Gi1/0/1").poe is PoeStatus.SEARCHING


async def test_n1548p_fdb_and_lldp() -> None:
    driver = await _driver("dell-n1548p")
    fdb = await driver.read_fdb()
    assert len(fdb) == 498
    assert all(e.vid is not None for e in fdb)

    [neighbor] = await driver.read_lldp()
    assert (neighbor.local_if_index, neighbor.local_port_name) == (49, "Te1/0/1")
    assert neighbor.port_id == "Te1/0/4"
    assert len(neighbor.chassis_id) == 17  # MAC address


# --- Dell OS10 -------------------------------------------------------------------------------


async def test_os10_ports_and_vlan_names() -> None:
    inv = await (await _driver("dell-os10")).read_inventory()
    assert not any(p.name.startswith("mgmt") for p in inv.ports)
    assert sum(p.kind is PortKind.ETHERNET for p in inv.ports) == 56
    assert sum(p.kind is PortKind.LAG for p in inv.ports) == 16

    # OS10 has no dot1qPvid: derived from the single untagged VLAN
    access = _port(inv, "ethernet1/1/17")
    assert access.untagged_vlans == {2} and access.pvid == 2

    trunk = _port(inv, "port-channel1")
    assert not trunk.untagged_vlans and trunk.pvid is None
    assert len(trunk.tagged_vlans) == 40

    # name comes from the description of interface "vlan1" (ifIndex 103), not "vlan1"
    assert inv.vlans[0].vid == 1 and inv.vlans[0].name == "desc-103"


async def test_os10_bridge_ports_are_translated_to_if_index() -> None:
    driver = await _driver("dell-os10")
    inv = await driver.read_inventory()
    port_indexes = {p.if_index for p in inv.ports}
    fdb = await driver.read_fdb()
    assert len(fdb) == 1257
    # bridge port 1 is port-channel1000 (ifIndex 866): every entry must hit a known port
    assert {e.if_index for e in fdb} <= port_indexes | {866}
    assert len(await driver.read_arp()) == 57


# --- HP 2530 ---------------------------------------------------------------------------------


async def test_hp2530_ports_and_pvid() -> None:
    inv = await (await _driver("hp-2530-48g")).read_inventory()
    assert [p.name for p in inv.ports[:3]] == ["1", "2", "3"]
    trk = _port(inv, "Trk1")
    assert trk.kind is PortKind.LAG and trk.oper_up and trk.speed_mbps == 2000

    tagged_only = _port(inv, "1")  # HP reports PVID 1 although port 1 is not in VLAN 1
    assert tagged_only.tagged_vlans == {120} and not tagged_only.untagged_vlans
    assert tagged_only.pvid is None
    assert _port(inv, "5").pvid == 515


async def test_hp2530_fdb_ids_are_mapped_to_vlans() -> None:
    driver = await _driver("hp-2530-48g")
    vids = {v.vid for v in (await driver.read_inventory()).vlans}
    fdb = await driver.read_fdb()
    assert len(fdb) == 408
    # HP numbers its filtering databases 1..n; without mapping, VLANs would be wrong
    assert {e.vid for e in fdb} <= vids
    assert any(e.vid == 515 for e in fdb)


async def test_hp2530_lldp_neighbors() -> None:
    neighbors = await (await _driver("hp-2530-48g")).read_lldp()
    assert len(neighbors) == 15
    phone = next(n for n in neighbors if n.local_port_name == "8")
    assert phone.local_if_index == 8
    assert phone.system_description.startswith("Mitel 6920")
    assert phone.chassis_id == phone.management_address  # chassis id subtype "network address"
    assert len(phone.port_id) == 17  # port id subtype "MAC address"


# --- MIB helpers -----------------------------------------------------------------------------


def test_bitmap_ports() -> None:
    assert mib.bitmap_ports(bytes.fromhex("8001")) == {1, 16}
    assert mib.bitmap_ports(bytes.fromhex("000000000000c4")) == {49, 50, 54}
    assert mib.bitmap_ports(None) == set()


def test_mac_formatting() -> None:
    assert mib.mac(bytes.fromhex("20040fddb459")) == "20:04:0f:dd:b4:59"
    assert mib.mac(bytes(6)) is None
    assert mib.mac(b"abc") is None
