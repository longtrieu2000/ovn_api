from __future__ import annotations

from fastapi import APIRouter, Query

from ..models.flow import LogicalFlow, OpenFlowDump
from ..services.flow_service import FlowService


router = APIRouter()


@router.get("/flows/logical", response_model=list[LogicalFlow])
def get_logical_flows(table_id: int | None = Query(default=None, alias="table")) -> list[LogicalFlow]:
    return FlowService().list_logical_flows(table_id=table_id)


@router.get("/flows/openflow", response_model=OpenFlowDump)
def get_openflow_flows(bridge: str = "br-int") -> OpenFlowDump:
    return FlowService().get_openflow_flows(bridge=bridge)
