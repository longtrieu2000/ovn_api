from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CanaryResourceType = Literal[
    "acl",
    "logical_flow",
    "nat",
    "nat_rule",
    "logical_switch",
    "network",
    "logical_router",
    "logical_switch_port",
    "logical_port",
    "logical_router_port",
    "subnet",
]

CanaryTraceStatus = Literal["success", "partial_success", "timeout", "failed"]
CanaryStageStatus = Literal["observed", "timeout", "skipped", "failed"]
CanaryRunStatus = Literal["queued", "running", "success", "partial_success", "timeout", "failed"]


class CanaryProbeRequest(BaseModel):
    resource_type: CanaryResourceType
    target_name: str | None = None
    bridge: str = "br-int"
    timeout_s: float = Field(default=15.0, gt=0)
    poll_interval_ms: int = Field(default=250, ge=50)
    expect_openflow: bool | None = None


class CanaryProbeStage(BaseModel):
    status: CanaryStageStatus
    observed_at: str | None = None
    latency_ms: float | None = None
    detail: str | None = None
    evidence: list[str] = Field(default_factory=list)


class CanaryProbeResult(BaseModel):
    probe_id: str
    requested_resource_type: CanaryResourceType
    resolved_resource_type: str
    resource_name: str
    target_name: str | None = None
    started_at: str
    finished_at: str | None = None
    status: CanaryTraceStatus
    openflow_expected: bool
    note: str | None = None
    nb_uuid: str | None = None
    command_latency_ms: float
    nb_committed: CanaryProbeStage
    sb_realized: CanaryProbeStage
    openflow_realized: CanaryProbeStage
    cleanup: CanaryProbeStage
    nb_to_sb_latency_ms: float | None = None
    sb_to_openflow_latency_ms: float | None = None
    total_latency_ms: float | None = None


class CanaryCapability(BaseModel):
    requested_resource_type: CanaryResourceType
    resolved_resource_type: str
    alias_for: str | None = None
    target_name_kind: str | None = None
    nb_table: str
    sb_signal: str
    openflow_supported: bool
    requires_target_name_for_openflow: bool
    available_stages: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CanaryCapabilitiesResponse(BaseModel):
    sync_endpoint: str
    async_submit_endpoint: str
    async_run_endpoint_template: str
    execution_model: str
    store_scope: str
    pipeline_stages: list[str] = Field(default_factory=list)
    resources: list[CanaryCapability] = Field(default_factory=list)


class CanaryRunSummary(BaseModel):
    probe_id: str
    requested_resource_type: CanaryResourceType
    resolved_resource_type: str
    resource_name: str
    target_name: str | None = None
    status: CanaryRunStatus
    queued_at: str
    started_at: str | None = None
    updated_at: str
    finished_at: str | None = None
    openflow_expected: bool
    queue_depth: int | None = None
    note: str | None = None


class CanaryRunDetail(CanaryRunSummary):
    request: CanaryProbeRequest
    result: CanaryProbeResult | None = None
    error: str | None = None
