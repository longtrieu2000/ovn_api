from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .metrics import CapacityMetrics, DatapathMetrics, LatencyMetrics
from .traces import CanaryRunSummary


MonitoringStatus = Literal["ok", "degraded"]
MonitoringEventType = Literal["snapshot", "trace_run", "heartbeat"]


class MonitoringComponentStatus(BaseModel):
    available: bool
    updated_at: str | None = None
    age_s: float | None = None
    error: str | None = None


class TraceRuntimeMetrics(BaseModel):
    queue_depth: int
    worker_alive: bool
    max_runs: int


class ApiRuntimeMetrics(BaseModel):
    uptime_s: float
    http_requests_total: int
    http_requests_in_flight: int
    http_request_errors_total: int
    http_request_duration_ms_sum: float
    http_request_duration_ms_count: int
    websocket_clients_current: int
    websocket_connections_total: int
    websocket_messages_sent_total: int


class MonitoringSnapshot(BaseModel):
    sequence: int
    generated_at: str
    status: MonitoringStatus
    interval_s: float
    capacity: CapacityMetrics | None = None
    datapath: DatapathMetrics | None = None
    latency: LatencyMetrics | None = None
    capacity_status: MonitoringComponentStatus
    datapath_status: MonitoringComponentStatus
    latency_status: MonitoringComponentStatus
    trace_runtime: TraceRuntimeMetrics
    api_runtime: ApiRuntimeMetrics
    errors: list[str] = Field(default_factory=list)


class MonitoringEvent(BaseModel):
    event: MonitoringEventType
    emitted_at: str
    sequence: int | None = None
    snapshot: MonitoringSnapshot | None = None
    trace_run: CanaryRunSummary | None = None
