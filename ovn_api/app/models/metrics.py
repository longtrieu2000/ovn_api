from __future__ import annotations

from pydantic import BaseModel


class CapacityMetrics(BaseModel):
    logical_flow_count: int
    logical_switch_count: int
    logical_switch_port_count: int
    logical_router_count: int
    logical_router_port_count: int
    acl_count: int
    nat_count: int
    load_balancer_count: int


class LatencyMetrics(BaseModel):
    nb_query_latency_ms: float
    sb_query_latency_ms: float
    bfd_session_count: int
    bfd_up_count: int
    bfd_down_count: int
    bfd_admin_down_count: int
    min_tx_min_ms: int | None = None
    min_tx_max_ms: int | None = None
    min_rx_min_ms: int | None = None
    min_rx_max_ms: int | None = None
