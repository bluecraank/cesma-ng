"""Clients, global search, MAC types and SNMP gateways."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CallerDep, Db, csrf_guard
from app.schemas import (
    ClientOut,
    GatewayIn,
    GatewayOut,
    MacTypeIn,
    MacTypeOut,
    Page,
    SearchResult,
)
from app.services import gateways
from app.services.clients import ClientFilter, search_clients
from app.services.search import search

router = APIRouter(tags=["clients"], dependencies=[Depends(csrf_guard)])


@router.get("/clients", response_model=Page[ClientOut])
async def list_clients(
    db: Db,
    caller: CallerDep,
    q: str | None = None,
    site_id: int | None = None,
    vid: int | None = None,
    device_id: int | None = None,
    active_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> object:
    items, total = await search_clients(
        db, caller, ClientFilter(q, site_id, vid, device_id, active_only, limit, offset)
    )
    return {"items": items, "total": total}


@router.get("/search", response_model=SearchResult)
async def global_search(db: Db, caller: CallerDep, q: str) -> object:
    return {"hits": await search(db, caller, q)}


@router.get("/mac-types", response_model=list[MacTypeOut])
async def list_mac_types(db: Db, caller: CallerDep) -> object:
    return await gateways.list_mac_types(db)


@router.post("/mac-types", response_model=MacTypeOut, status_code=status.HTTP_201_CREATED)
async def create_mac_type(body: MacTypeIn, db: Db, caller: CallerDep) -> object:
    return await gateways.save_mac_type(db, caller, body.model_dump())


@router.put("/mac-types/{type_id}", response_model=MacTypeOut)
async def update_mac_type(type_id: int, body: MacTypeIn, db: Db, caller: CallerDep) -> object:
    return await gateways.save_mac_type(db, caller, body.model_dump(), type_id)


@router.delete("/mac-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mac_type(type_id: int, db: Db, caller: CallerDep) -> None:
    await gateways.delete_mac_type(db, caller, type_id)


@router.get("/gateways", response_model=list[GatewayOut])
async def list_gateways(db: Db, caller: CallerDep) -> object:
    return await gateways.list_gateways(db, caller)


@router.post("/gateways", response_model=GatewayOut, status_code=status.HTTP_201_CREATED)
async def create_gateway(body: GatewayIn, db: Db, caller: CallerDep) -> object:
    return await gateways.save_gateway(db, caller, body.model_dump())


@router.put("/gateways/{gateway_id}", response_model=GatewayOut)
async def update_gateway(gateway_id: int, body: GatewayIn, db: Db, caller: CallerDep) -> object:
    return await gateways.save_gateway(db, caller, body.model_dump(), gateway_id)


@router.delete("/gateways/{gateway_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gateway(gateway_id: int, db: Db, caller: CallerDep) -> None:
    await gateways.delete_gateway(db, caller, gateway_id)
