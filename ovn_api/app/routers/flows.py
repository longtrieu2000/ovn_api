from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from ..models.flow import LogicalFlow, LogicalFlowOriginSummary, OpenFlowDump
from ..services.flow_service import FlowService


router = APIRouter()


@router.get("/flows/logical/summary", response_model=LogicalFlowOriginSummary)
def get_logical_flow_origin_summary() -> LogicalFlowOriginSummary:
    return FlowService().get_logical_flow_origin_summary()


@router.get("/flows/logical", response_model=list[LogicalFlow])
def get_logical_flows(
    table_id: int | None = Query(default=None, alias="table"),
    origin: Literal["acl", "nat", "other"] | None = Query(default=None),
    origin_uuid: str | None = Query(default=None),
) -> list[LogicalFlow]:
    return FlowService().list_logical_flows(
        table_id=table_id,
        origin=origin,
        origin_uuid=origin_uuid,
    )


@router.get("/flows/openflow", response_model=OpenFlowDump)
def get_openflow_flows(bridge: str = "br-int") -> OpenFlowDump:
    return FlowService().get_openflow_flows(bridge=bridge)
