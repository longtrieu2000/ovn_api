from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .traces import CanaryProbeResult, CanaryResourceType


TargetResolutionMode = Literal["configured", "auto", "not_required", "unresolved"]
ScheduledTraceServiceStatus = Literal["enabled", "disabled"]


class ScheduledTraceProfileStatus(BaseModel):
    profile: str
    requested_resource_type: CanaryResourceType
    bridge: str = "br-int"
    configured_target_name: str | None = None
    resolved_target_name: str | None = None
    target_resolution_mode: TargetResolutionMode = "not_required"
    interval_s: float
    timeout_s: float
    poll_interval_ms: int
    enabled: bool
    last_status: str = "idle"
    last_error: str | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    run_count: int = 0
    success_count: int = 0
    partial_success_count: int = 0
    timeout_count: int = 0
    failed_count: int = 0
    last_result: CanaryProbeResult | None = None


class ScheduledTraceMetricsSnapshot(BaseModel):
    generated_at: str
    status: ScheduledTraceServiceStatus
    worker_alive: bool
    default_bridge: str = "br-int"
    profiles: list[ScheduledTraceProfileStatus] = Field(default_factory=list)


class ScheduledTraceProfileConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    resource_type: CanaryResourceType = Field(
        validation_alias=AliasChoices("resource_type", "requested_resource_type")
    )
    target_name: str | None = None
    bridge: str | None = None
    interval_s: float | None = Field(default=None, gt=0)
    timeout_s: float | None = Field(default=None, gt=0)
    poll_interval_ms: int | None = Field(default=None, ge=50)
    enabled: bool = True


class ScheduledTraceProfilesConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[ScheduledTraceProfileConfigInput] = Field(default_factory=list)
