from __future__ import annotations

from pydantic import BaseModel, Field


class CapacityMetrics(BaseModel):
    logical_flow_count: int
    logical_switch_count: int
    logical_switch_port_count: int
    logical_router_count: int
    logical_router_port_count: int
    acl_count: int
    nat_count: int
    load_balancer_count: int


class DatapathMetrics(BaseModel):
    datapath_flows: int
    lookups_hit: int
    lookups_missed: int
    lookups_lost: int
    cache_hit_rate: float | None = None
    mask_hit_per_pkt: float | None = None


class BfdSessionLatency(BaseModel):
    uuid: str
    logical_port: str | None = None
    dst_ip: str | None = None
    chassis_name: str | None = None
    status: str = ""
    min_tx_ms: int | None = None
    min_rx_ms: int | None = None
    detect_mult: int | None = None


class BfdLatencyMetrics(BaseModel):
    session_count: int
    up_count: int
    down_count: int
    admin_down_count: int
    init_count: int
    min_tx_min_ms: int | None = None
    min_tx_max_ms: int | None = None
    min_rx_min_ms: int | None = None
    min_rx_max_ms: int | None = None
    sessions: list[BfdSessionLatency] = Field(default_factory=list)


class OvsdbLatencyMetrics(BaseModel):
    measurement_mode: str
    nb_probe_table: str
    sb_probe_table: str
    nb_transaction_latency_ms: float
    sb_transaction_latency_ms: float
    nb_idl_sync_latency_ms: float
    sb_idl_sync_latency_ms: float


class OpenFlowInstallationLatencyMetrics(BaseModel):
    available: bool
    measurement_mode: str
    latency_ms: float | None = None
    reason: str | None = None


class LatencyMetrics(BaseModel):
    bfd: BfdLatencyMetrics
    ovsdb: OvsdbLatencyMetrics
    openflow_installation: OpenFlowInstallationLatencyMetrics
