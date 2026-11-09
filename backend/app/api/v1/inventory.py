"""Polled switch state, refresh and model detection."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AppSettings, CallerDep, Db, csrf_guard, get_secret_box
from app.core.crypto import SecretBox
from app.drivers.registry import detect
from app.models import Permission
from app.schemas import (
    DetectRequest,
    DetectResult,
    DeviceHintOut,
    DeviceVlanOut,
    FdbEntryOut,
    LldpNeighborOut,
    PollStateOut,
    PortOut,
    PortStatsOut,
    TopologyOut,
)
from app.services import credentials, inventory_query, polling
from app.services.access import require_permission_anywhere
from app.services.device_hints import site_hints
from app.services.devices import get_device
from app.services.port_stats import port_statistics
from app.services.reports import site_report
from app.services.topology import site_topology
from app.transports.snmp import SnmpError

router = APIRouter(tags=["inventory"], dependencies=[Depends(csrf_guard)])


@router.get("/devices/{device_id}/ports", response_model=list[PortOut])
async def ports(device_id: int, db: Db, caller: CallerDep) -> object:
    return await inventory_query.list_ports(db, caller, device_id)


@router.get("/devices/{device_id}/vlans", response_model=list[DeviceVlanOut])
async def vlans(device_id: int, db: Db, caller: CallerDep) -> object:
    return await inventory_query.list_vlans(db, caller, device_id)


@router.get("/devices/{device_id}/fdb", response_model=list[FdbEntryOut])
async def fdb(device_id: int, db: Db, caller: CallerDep, port_id: int | None = None) -> object:
    return await inventory_query.list_fdb(db, caller, device_id, port_id)


@router.get("/devices/{device_id}/lldp", response_model=list[LldpNeighborOut])
async def lldp(device_id: int, db: Db, caller: CallerDep) -> object:
    return await inventory_query.list_lldp(db, caller, device_id)


@router.get("/devices/{device_id}/poll-state", response_model=list[PollStateOut])
async def poll_state(device_id: int, db: Db, caller: CallerDep) -> object:
    return await inventory_query.poll_states(db, caller, device_id)


@router.post("/devices/{device_id}/poll", status_code=status.HTTP_202_ACCEPTED)
async def request_poll(device_id: int, db: Db, caller: CallerDep) -> None:
    """Ask the worker to refresh this device now (any user who can see it may do this)."""
    await get_device(db, caller, device_id)
    await polling.request_poll(db, device_id)


@router.post("/devices/detect", response_model=DetectResult)
async def detect_model(
    body: DetectRequest,
    db: Db,
    caller: CallerDep,
    settings: AppSettings,
    box: Annotated[SecretBox, Depends(get_secret_box)],
) -> object:
    """Identify a switch before it is added (asks it via SNMP)."""
    require_permission_anywhere(caller.user, Permission.DEVICES_MANAGE)
    profile = (
        await credentials.get_profile(db, body.credential_profile_id)
        if body.credential_profile_id
        else None
    )
    creds = credentials.to_device_credentials(profile, box)
    try:
        return await detect(polling.snmp_client(settings, body.hostname, creds, quick=True))
    except SnmpError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No SNMP answer: {exc}") from exc


@router.get("/sites/{site_id}/device-hints", response_model=list[DeviceHintOut])
async def device_hints(
    site_id: int, db: Db, caller: CallerDep, box: Annotated[SecretBox, Depends(get_secret_box)]
) -> object:
    """Setup problems per device: missing credentials, unreachable switches."""
    return await site_hints(db, caller, box, site_id)


@router.get("/sites/{site_id}/topology", response_model=TopologyOut)
async def topology(
    site_id: int, db: Db, caller: CallerDep, include_external: bool = False
) -> object:
    return await site_topology(db, caller, site_id, include_external=include_external)


@router.get("/devices/{device_id}/ports/{port_id}/stats", response_model=PortStatsOut)
async def port_stats(
    device_id: int,
    port_id: int,
    db: Db,
    caller: CallerDep,
    hours: Annotated[int, Query(ge=1, le=24 * 14)] = 24,
) -> object:
    return await port_statistics(db, caller, device_id, port_id, hours)


@router.get("/sites/{site_id}/reports")
async def reports(site_id: int, db: Db, caller: CallerDep) -> dict[str, Any]:
    return await site_report(db, caller, site_id)
