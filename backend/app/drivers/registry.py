"""The one place that maps device models to drivers and detects the model of a switch."""

from dataclasses import dataclass

from app.domain.credentials import DeviceCredentials
from app.drivers.base import SnmpSwitchDriver
from app.drivers.vendors import ArubaCxDriver, ArubaOsSwitchDriver, DellN1500Driver, DellOs10Driver
from app.drivers.writers import (
    ArubaCxRestWriter,
    ArubaOsRestWriter,
    ConfigWriter,
    DnosCliWriter,
    Os10CliWriter,
)
from app.models.device import DeviceModel
from app.transports.snmp import PysnmpClient, SnmpClient

DRIVERS: dict[DeviceModel, type[SnmpSwitchDriver]] = {
    driver.model: driver
    for driver in (DellN1500Driver, DellOs10Driver, ArubaOsSwitchDriver, ArubaCxDriver)
}
assert set(DRIVERS) == set(DeviceModel), "every device model needs a driver"


def driver_for(model: DeviceModel, snmp: SnmpClient) -> SnmpSwitchDriver:
    return DRIVERS[model](snmp)


def snmp_client(host: str, credentials: DeviceCredentials) -> SnmpClient:
    return PysnmpClient(host, credentials.snmp)


@dataclass(frozen=True)
class Detection:
    model: DeviceModel | None
    sys_name: str
    sys_descr: str
    sys_object_id: str
    model_name: str | None


async def detect(snmp: SnmpClient) -> Detection:
    """Identify the switch family from sysObjectID (via a neutral driver instance)."""
    system = await DellN1500Driver(snmp).read_system()  # system group is identical everywhere
    model = next(
        (m for m, d in DRIVERS.items() if d.matches(system.sys_object_id, system.sys_descr)), None
    )
    return Detection(
        model, system.sys_name, system.sys_descr, system.sys_object_id, system.model_name
    )


# --- Writing and backups ---------------------------------------------------------------------

WRITERS: dict[DeviceModel, type[ConfigWriter]] = {
    DeviceModel.DELL_N1500: DnosCliWriter,
    DeviceModel.DELL_OS10: Os10CliWriter,
    DeviceModel.ARUBA_OS_SWITCH: ArubaOsRestWriter,
    DeviceModel.ARUBA_CX: ArubaCxRestWriter,
}
assert set(WRITERS) == set(DeviceModel), "every device model needs a writer"


def writer_for(model: DeviceModel, host: str, credentials: DeviceCredentials) -> ConfigWriter:
    return WRITERS[model](host, credentials)
