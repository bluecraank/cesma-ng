"""Changing switches: ports, site VLANs, VLAN sync, port profiles, backups, jobs, SSH keys."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CallerDep, Db, RuntimeDep, csrf_guard
from app.core.errors import NotFoundError
from app.domain.changes import ChangePlan
from app.models import PortProfile
from app.schemas import (
    ApplyResult,
    BackupOut,
    ChangePlanOut,
    ConsoleIn,
    ConsoleOut,
    JobIn,
    JobOut,
    PortChangeIn,
    PortProfileIn,
    PortProfileOut,
    RenameIn,
    SiteVlanIn,
    SiteVlanOut,
    SshKeyIn,
    SshKeyOut,
    VlanSyncIn,
)
from app.services import backups, device_rename, jobs, port_config, site_config, ssh_keys
from app.services.console import run_command
from app.services.context import Caller
from app.services.devices import get_device
from app.services.port_config import PortChange

router = APIRouter(tags=["configuration"], dependencies=[Depends(csrf_guard)])


def _plan_out(plan: ChangePlan) -> dict[str, Any]:
    return {
        "device_id": plan.device_id,
        "device_name": plan.device_name,
        "operations": len(plan.operations),
        "commands": plan.commands,
        "warnings": plan.warnings,
    }


async def _port_change(db: Db, caller: Caller, device_id: int, body: PortChangeIn) -> PortChange:
    if body.profile_id is not None:
        device = await get_device(db, caller, device_id)
        profile = await db.get(PortProfile, body.profile_id)
        if profile is None or profile.site_id != device.site_id:
            raise NotFoundError("Port profile not found at this site")
        return PortChange(
            description=profile.description,
            enabled=body.enabled,
            untagged=profile.untagged_vid,
            tagged=frozenset(profile.tagged_vids),
            clear_untagged=profile.untagged_vid is None,
        )
    return PortChange(
        description=body.description,
        enabled=body.enabled,
        untagged=body.untagged,
        tagged=frozenset(body.tagged) if body.tagged is not None else None,
        clear_untagged=body.clear_untagged,
        add_tagged=frozenset(body.add_tagged),
        remove_tagged=frozenset(body.remove_tagged),
    )


# --- Ports -----------------------------------------------------------------------------------


@router.post("/devices/{device_id}/ports/plan", response_model=ChangePlanOut)
async def plan_ports(
    device_id: int, body: PortChangeIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    change = await _port_change(db, caller, device_id, body)
    result = await port_config.plan_port_change(
        db, caller, runtime, device_id, body.port_ids, change
    )
    return _plan_out(result.plan)


@router.post("/devices/{device_id}/ports/apply", response_model=ApplyResult)
async def apply_ports(
    device_id: int, body: PortChangeIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    change = await _port_change(db, caller, device_id, body)
    plan, log = await port_config.apply_port_change(
        db, caller, runtime, device_id, body.port_ids, change
    )
    return {"plan": _plan_out(plan), "log": log}


@router.post("/devices/{device_id}/rename/plan", response_model=ChangePlanOut)
async def plan_rename(
    device_id: int, body: RenameIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    return _plan_out(await device_rename.plan_rename(db, caller, runtime, device_id, body.name))


@router.post("/devices/{device_id}/rename/apply", response_model=ApplyResult)
async def apply_rename(
    device_id: int, body: RenameIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    plan, log = await device_rename.apply_rename(db, caller, runtime, device_id, body.name)
    return {"plan": _plan_out(plan), "log": log}


# --- Site VLANs and sync ---------------------------------------------------------------------


@router.get("/sites/{site_id}/vlans", response_model=list[SiteVlanOut])
async def list_site_vlans(site_id: int, db: Db, caller: CallerDep) -> object:
    return await site_config.list_site_vlans(db, caller, site_id)


@router.post("/sites/{site_id}/vlans", status_code=status.HTTP_201_CREATED)
async def create_site_vlan(
    site_id: int, body: SiteVlanIn, db: Db, caller: CallerDep
) -> dict[str, int]:
    vlan = await site_config.save_site_vlan(db, caller, site_id, body.model_dump())
    return {"id": vlan.id}


@router.put("/sites/{site_id}/vlans/{vlan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_site_vlan(
    site_id: int, vlan_id: int, body: SiteVlanIn, db: Db, caller: CallerDep
) -> None:
    await site_config.save_site_vlan(db, caller, site_id, body.model_dump(), vlan_id)


@router.delete("/sites/{site_id}/vlans/{vlan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site_vlan(site_id: int, vlan_id: int, db: Db, caller: CallerDep) -> None:
    await site_config.delete_site_vlan(db, caller, site_id, vlan_id)


@router.post("/sites/{site_id}/vlans/import")
async def import_vlans(site_id: int, db: Db, caller: CallerDep) -> dict[str, int]:
    return {"imported": await site_config.import_vlans_from_devices(db, caller, site_id)}


@router.post("/sites/{site_id}/vlans/sync/plan", response_model=list[ChangePlanOut])
async def plan_vlan_sync(
    site_id: int, body: VlanSyncIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    plans = await site_config.plan_vlan_sync(
        db,
        caller,
        runtime,
        site_id,
        device_ids=body.device_ids,
        delete_extra=body.delete_extra,
        tag_uplinks=body.tag_uplinks,
    )
    return [_plan_out(p) for p in plans]


# --- Port profiles ---------------------------------------------------------------------------


@router.get("/sites/{site_id}/port-profiles", response_model=list[PortProfileOut])
async def list_profiles(site_id: int, db: Db, caller: CallerDep) -> object:
    return await site_config.list_profiles(db, caller, site_id)


@router.post(
    "/sites/{site_id}/port-profiles",
    response_model=PortProfileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(site_id: int, body: PortProfileIn, db: Db, caller: CallerDep) -> object:
    return await site_config.save_profile(db, caller, site_id, body.model_dump())


@router.put("/sites/{site_id}/port-profiles/{profile_id}", response_model=PortProfileOut)
async def update_profile(
    site_id: int, profile_id: int, body: PortProfileIn, db: Db, caller: CallerDep
) -> object:
    return await site_config.save_profile(db, caller, site_id, body.model_dump(), profile_id)


@router.delete(
    "/sites/{site_id}/port-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_profile(site_id: int, profile_id: int, db: Db, caller: CallerDep) -> None:
    await site_config.delete_profile(db, caller, site_id, profile_id)


# --- Backups ---------------------------------------------------------------------------------


@router.get("/backups", response_model=list[BackupOut])
async def list_backups(
    db: Db,
    caller: CallerDep,
    device_id: int | None = None,
    site_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> object:
    return await backups.list_backups(db, caller, device_id=device_id, site_id=site_id, limit=limit)


@router.get("/backups/{backup_id}/config")
async def download_backup(
    backup_id: int, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> Response:
    backup, device, text = await backups.backup_config(db, caller, runtime, backup_id)
    filename = f"{device.name}_{backup.created_at:%Y-%m-%d_%H%M}.txt"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/backups/diff")
async def diff_backups(
    old: int, new: int, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> dict[str, str]:
    return {"diff": await backups.diff_backups(db, caller, runtime, old, new)}


# --- Jobs ------------------------------------------------------------------------------------


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(body: JobIn, db: Db, caller: CallerDep) -> object:
    payload = {
        "device_ids": body.device_ids,
        "delete_extra": body.delete_extra,
        "tag_uplinks": body.tag_uplinks,
        "cidr": body.cidr,
        "credential_profile_id": body.credential_profile_id,
        "backup_id": body.backup_id,
    }
    return await jobs.enqueue(db, caller, body.kind, body.site_id, payload)


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(db: Db, caller: CallerDep, site_id: int | None = None) -> object:
    return await jobs.list_jobs(db, caller, site_id)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: Db, caller: CallerDep) -> object:
    return await jobs.get_job(db, caller, job_id)


# --- SSH keys --------------------------------------------------------------------------------


@router.get("/ssh-keys", response_model=list[SshKeyOut])
async def list_keys(db: Db, caller: CallerDep, all_users: bool = False) -> object:
    """The caller's own keys; ``all_users`` (super administrators) lists everyone's."""
    return await ssh_keys.list_keys(db, caller, all_users=all_users)


@router.post("/ssh-keys", response_model=SshKeyOut, status_code=status.HTTP_201_CREATED)
async def add_key(body: SshKeyIn, db: Db, caller: CallerDep) -> object:
    return await ssh_keys.add_key(db, caller, body.description, body.key)


@router.delete("/ssh-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(key_id: int, db: Db, caller: CallerDep) -> None:
    await ssh_keys.delete_key(db, caller, key_id)


# --- Console (read-only commands) ------------------------------------------------------------


@router.post("/devices/{device_id}/console", response_model=ConsoleOut)
async def console(
    device_id: int, body: ConsoleIn, db: Db, caller: CallerDep, runtime: RuntimeDep
) -> object:
    return {"output": await run_command(db, caller, runtime, device_id, body.command)}
