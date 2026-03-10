from __future__ import annotations

from fastapi import APIRouter

from ..models.topology import (
    LogicalRouterDetail,
    LogicalRouterSummary,
    LogicalSwitchDetail,
    LogicalSwitchSummary,
)
from ..services.topology_service import TopologyService


router = APIRouter()


@router.get("/switches", response_model=list[LogicalSwitchSummary])
def list_switches() -> list[LogicalSwitchSummary]:
    return TopologyService().list_switches()


@router.get("/switches/{switch_ref}", response_model=LogicalSwitchDetail)
def get_switch(switch_ref: str) -> LogicalSwitchDetail:
    return TopologyService().get_switch(switch_ref=switch_ref)


@router.get("/routers", response_model=list[LogicalRouterSummary])
def list_routers() -> list[LogicalRouterSummary]:
    return TopologyService().list_routers()


@router.get("/routers/{router_ref}", response_model=LogicalRouterDetail)
def get_router(router_ref: str) -> LogicalRouterDetail:
    return TopologyService().get_router(router_ref=router_ref)
