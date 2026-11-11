import shutil
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.models import Device, DeviceStatus, DiscoveredHost
from app.services import discovery
from app.services.context import Runtime
from tests.conftest import recording


async def test_range_scan_finds_switch_once(
    alice: AsyncClient, app, settings: Settings, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    # simulator: the HP recording answers as 192.0.2.10; 192.0.2.9 does not exist (TEST-NET)
    shutil.copy(recording("hp-2530-48g"), tmp_path / "192.0.2.10.snmprec")
    settings = settings.model_copy(update={"snmp_simulator_dir": str(tmp_path)})
    runtime = Runtime(settings, app.state.secret_box)
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]

    async with app.state.database.sessionmaker() as db:
        assert await discovery.discover_range(db, runtime, "192.0.2.8/30", site, None) == 1
        await db.commit()
        device = (await db.execute(select(Device))).scalar_one()
        assert device.status is DeviceStatus.UNCONFIRMED
        assert device.hostname == "192.0.2.10" and device.model.value == "aruba_os_switch"
        hosts = {
            h.ip_address: h.result for h in (await db.execute(select(DiscoveredHost))).scalars()
        }
        assert hosts == {"192.0.2.9": "no answer", "192.0.2.10": "aruba_os_switch"}

    notes = (await alice.get("/notifications")).json()
    assert notes[0]["kind"] == "device_discovered"

    # deleting the unconfirmed device: it is remembered and not found again
    assert (await alice.delete(f"/devices/{device.id}")).status_code == 204
    async with app.state.database.sessionmaker() as db:
        assert await discovery.discover_range(db, runtime, "192.0.2.10/32", site, None) == 0


async def test_confirming_by_editing(alice: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    async with app.state.database.sessionmaker() as db:
        db.add(
            Device(
                site_id=site,
                name="found",
                hostname="192.0.2.20",
                model="dell_os10",
                status=DeviceStatus.UNCONFIRMED,
                location_note="",
            )
        )
        await db.commit()
    device = (await alice.get("/devices")).json()[0]
    updated = (await alice.patch(f"/devices/{device['id']}", json={"name": "sw-core"})).json()
    assert updated["status"] == "unknown"  # confirmed: polled from now on
