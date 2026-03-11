from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LogicalFlowOrigin = Literal["acl", "nat", "other"]


class LogicalFlow(BaseModel):
    uuid: str
    logical_datapath: str | None = None
    table_id: int | None = None
    priority: int | None = None
    match: str = ""
    actions: str = ""
    stage_name: str | None = None
    stage_hint: str | None = None
    source: str | None = None
    origin_type: LogicalFlowOrigin = "other"
    origin_uuid: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)


class LogicalFlowOriginSummary(BaseModel):
    logical_flow_count: int
    acl_logical_flow_count: int
    nat_logical_flow_count: int
    other_logical_flow_count: int
    acl_count: int
    nat_count: int
    acl_with_logical_flows_count: int
    nat_with_logical_flows_count: int


class OpenFlowDump(BaseModel):
    bridge: str
    flow_count: int
    lines: list[str] = Field(default_factory=list)
    raw: str
