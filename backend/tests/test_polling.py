"""Polling pipeline: recording -> driver -> database -> API."""

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.domain.credentials import DeviceCredentials
from app.drivers.base import SnmpSwitchDriver
from app.models import Device, DevicePollState, PollTask
from app.services.polling import driver_factory_for, due_tasks, poll_device
from app.transports.snmp import SnmpError

FIXTURES = Path(__file__).parent / "fixtures" / "snmp"


async def _device(alice: AsyncClient, hostname: str, model: str) -> int:
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    body = {"name": hostname, "hostname": hostname, "model": model, "site_id": site}
    return int((await alice.post("/devices", json=body)).json()["id"])


async def _poll_all(app, device_id: int, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    for task in PollTask:
        async with app.state.database.sessionmaker() as db:
            ok = await poll_device(
                db,
                device_id,
                task,
                settings=settings,
                box=app.state.secret_box,
                driver_factory=driver_factory_for(settings),
            )
            assert ok, task


async def test_full_poll_of_hp_switch(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    device_id = await _device(alice, "hp-2530-48g", "aruba_os_switch")
    await _poll_all(app, device_id, settings)

    device = (await alice.get(f"/devices/{device_id}")).json()
    assert device["status"] == "online"
    assert device["model_name"] == "J9775A" and device["firmware"] == "YA.16.11.0008"

    ports = (await alice.get(f"/devices/{device_id}/ports")).json()
    assert len(ports) == 53
    trunk = next(p for p in ports if p["name"] == "Trk1")
    assert trunk["is_uplink"] and trunk["kind"] == "lag"
    assert sum(p["mac_count"] for p in ports) == 408
    phone_port = next(p for p in ports if p["name"] == "8")
    assert phone_port["neighbor"]  # LLDP neighbour attached to the port

    vlans = (await alice.get(f"/devices/{device_id}/vlans")).json()
    assert len(vlans) == 30

    fdb = (await alice.get(f"/devices/{device_id}/fdb", params={"port_id": trunk["id"]})).json()
    assert fdb and all(e["port_name"] == "Trk1" for e in fdb)
    assert len((await alice.get(f"/devices/{device_id}/lldp")).json()) == 15

    states = (await alice.get(f"/devices/{device_id}/poll-state")).json()
    assert {s["task"] for s in states} == {t.value for t in PollTask}
    assert all(s["failures"] == 0 for s in states)


async def test_second_poll_keeps_port_ids(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    device_id = await _device(alice, "dell-n1548p", "dell_n1500")
    await _poll_all(app, device_id, settings)
    before = {p["name"]: p["id"] for p in (await alice.get(f"/devices/{device_id}/ports")).json()}
    await _poll_all(app, device_id, settings)
    after = {p["name"]: p["id"] for p in (await alice.get(f"/devices/{device_id}/ports")).json()}
    assert before == after


class _Unreachable:
    def __call__(self, device: Device, credentials: DeviceCredentials) -> SnmpSwitchDriver:
        class Driver(SnmpSwitchDriver):
            async def read_inventory(self):  # type: ignore[no-untyped-def]
                raise SnmpError("No SNMP response received before timeout")

        return Driver(None)  # type: ignore[arg-type]


async def test_device_goes_offline_and_notifies(
    alice: AsyncClient, app, settings: Settings
) -> None:  # type: ignore[no-untyped-def]
    device_id = await _device(alice, "10.0.0.99", "dell_os10")
    for _ in range(2):
        async with app.state.database.sessionmaker() as db:
            ok = await poll_device(
                db,
                device_id,
                PollTask.INVENTORY,
                settings=settings,
                box=app.state.secret_box,
                driver_factory=_Unreachable(),
            )
            assert not ok

    assert (await alice.get(f"/devices/{device_id}")).json()["status"] == "offline"
    notes = (await alice.get("/notifications")).json()
    assert [n["kind"] for n in notes] == ["device_offline"]
    assert (await alice.get("/notifications/count")).json() == {"open": 1}
    assert (await alice.post(f"/notifications/{notes[0]['id']}/acknowledge")).status_code == 204
    assert (await alice.get("/notifications/count")).json() == {"open": 0}

    async with app.state.database.sessionmaker() as db:
        state = await db.get(DevicePollState, (device_id, PollTask.INVENTORY))
        assert state is not None and state.failures == 2 and "timeout" in (state.last_error or "")
        # backoff: not due again right away
        assert (device_id, PollTask.INVENTORY) not in await due_tasks(db, limit=100)


async def test_refresh_makes_tasks_due(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    device_id = await _device(alice, "dell-os10", "dell_os10")
    await _poll_all(app, device_id, settings)
    async with app.state.database.sessionmaker() as db:
        assert await due_tasks(db, limit=100) == []
    assert (await alice.post(f"/devices/{device_id}/poll")).status_code == 202
    async with app.state.database.sessionmaker() as db:
        assert len(await due_tasks(db, limit=100)) == len(PollTask)
        states = (await db.execute(select(DevicePollState))).scalars().all()
        assert len(states) == len(PollTask)


async def test_detect_uses_recording(alice: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    app.state.settings = app.state.settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    r = await alice.post("/devices/detect", json={"hostname": "dell-n1548p"})
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "dell_n1500"
    assert r.json()["model_name"] == "N1548P"


async def test_site_report(alice: AsyncClient, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"snmp_simulator_dir": str(FIXTURES)})
    device_id = await _device(alice, "dell-n1548p", "dell_n1500")
    await _poll_all(app, device_id, settings)
    site_id = (await alice.get(f"/devices/{device_id}")).json()["site_id"]
    report = (await alice.get(f"/sites/{site_id}/reports")).json()
    assert report["firmware"] == [
        {"model": "N1548P", "firmware": "6.8.1.0", "devices": ["dell-n1548p"]}
    ]
    free = report["free_ports"][0]
    assert free["total"] == 48 and len(free["free"]) == 42  # 52 ports - 4 uplinks; 6 up
    assert report["poe"][0]["ports"] == 48
    assert report["backups"][0]["last_backup"] is None  # never backed up
