from __future__ import annotations

import time

from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovn_sb import get_ovn_sb_client
from ..models.metrics import CapacityMetrics, LatencyMetrics


class MetricsService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.sb_client = get_ovn_sb_client()

    def get_capacity_metrics(self) -> CapacityMetrics:
        nb_idl = self.nb_client.get_idl()
        sb_idl = self.sb_client.get_idl()
        return CapacityMetrics(
            logical_flow_count=len(sb_idl.tables["Logical_Flow"].rows),
            logical_switch_count=len(nb_idl.tables["Logical_Switch"].rows),
            logical_switch_port_count=len(nb_idl.tables["Logical_Switch_Port"].rows),
            logical_router_count=len(nb_idl.tables["Logical_Router"].rows),
            logical_router_port_count=len(nb_idl.tables["Logical_Router_Port"].rows),
            acl_count=len(nb_idl.tables["ACL"].rows),
            nat_count=len(nb_idl.tables["NAT"].rows),
            load_balancer_count=len(nb_idl.tables["Load_Balancer"].rows),
        )

    def get_latency_metrics(self) -> LatencyMetrics:
        nb_start = time.perf_counter()
        nb_idl = self.nb_client.get_idl()
        nb_query_latency_ms = round((time.perf_counter() - nb_start) * 1000, 3)

        sb_start = time.perf_counter()
        sb_idl = self.sb_client.get_idl()
        sb_query_latency_ms = round((time.perf_counter() - sb_start) * 1000, 3)

        bfd_rows = list(sb_idl.tables["BFD"].rows.values())
        min_txs = [int(getattr(row, "min_tx", 0)) for row in bfd_rows if getattr(row, "min_tx", None) is not None]
        min_rxs = [int(getattr(row, "min_rx", 0)) for row in bfd_rows if getattr(row, "min_rx", None) is not None]

        statuses = [str(getattr(row, "status", "")) for row in bfd_rows]
        return LatencyMetrics(
            nb_query_latency_ms=nb_query_latency_ms,
            sb_query_latency_ms=sb_query_latency_ms,
            bfd_session_count=len(bfd_rows),
            bfd_up_count=sum(1 for status in statuses if status == "up"),
            bfd_down_count=sum(1 for status in statuses if status == "down"),
            bfd_admin_down_count=sum(1 for status in statuses if status == "admin_down"),
            min_tx_min_ms=min(min_txs) if min_txs else None,
            min_tx_max_ms=max(min_txs) if min_txs else None,
            min_rx_min_ms=min(min_rxs) if min_rxs else None,
            min_rx_max_ms=max(min_rxs) if min_rxs else None,
        )
