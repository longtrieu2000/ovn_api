from __future__ import annotations

import time

from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovn_sb import get_ovn_sb_client
from ..models.metrics import (
    BfdLatencyMetrics,
    BfdSessionLatency,
    CapacityMetrics,
    DatapathMetrics,
    LatencyMetrics,
    OpenFlowInstallationLatencyMetrics,
    OvsdbLatencyMetrics,
)
from .datapath_metrics_collector import get_datapath_metrics_collector


NB_LATENCY_PROBE_TABLE = "NB_Global"
SB_LATENCY_PROBE_TABLE = "SB_Global"


def _single_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        value = next(iter(value))
    return str(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        value = next(iter(value))
    return int(value)


class MetricsService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.sb_client = get_ovn_sb_client()
        self.datapath_collector = get_datapath_metrics_collector()

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

    def get_datapath_metrics(self) -> DatapathMetrics:
        return self.datapath_collector.get_snapshot()

    def get_latency_metrics(self) -> LatencyMetrics:
        nb_idl_start = time.perf_counter()
        nb_idl = self.nb_client.get_idl()
        nb_idl_sync_latency_ms = round((time.perf_counter() - nb_idl_start) * 1000, 3)

        sb_idl_start = time.perf_counter()
        sb_idl = self.sb_client.get_idl()
        sb_idl_sync_latency_ms = round((time.perf_counter() - sb_idl_start) * 1000, 3)

        nb_transaction_latency_ms = self.nb_client.measure_select_latency_ms(table=NB_LATENCY_PROBE_TABLE)
        sb_transaction_latency_ms = self.sb_client.measure_select_latency_ms(table=SB_LATENCY_PROBE_TABLE)

        bfd_rows = list(sb_idl.tables["BFD"].rows.values())
        min_txs = [int(getattr(row, "min_tx", 0)) for row in bfd_rows if getattr(row, "min_tx", None) is not None]
        min_rxs = [int(getattr(row, "min_rx", 0)) for row in bfd_rows if getattr(row, "min_rx", None) is not None]
        sessions = [
            BfdSessionLatency(
                uuid=str(row.uuid),
                logical_port=_single_optional_string(getattr(row, "logical_port", None)),
                dst_ip=_single_optional_string(getattr(row, "dst_ip", None)),
                chassis_name=_single_optional_string(getattr(row, "chassis_name", None)),
                status=str(getattr(row, "status", "")),
                min_tx_ms=_int_or_none(getattr(row, "min_tx", None)),
                min_rx_ms=_int_or_none(getattr(row, "min_rx", None)),
                detect_mult=_int_or_none(getattr(row, "detect_mult", None)),
            )
            for row in bfd_rows
        ]
        statuses = [session.status for session in sessions]
        return LatencyMetrics(
            bfd=BfdLatencyMetrics(
                session_count=len(sessions),
                up_count=sum(1 for status in statuses if status == "up"),
                down_count=sum(1 for status in statuses if status == "down"),
                admin_down_count=sum(1 for status in statuses if status == "admin_down"),
                init_count=sum(1 for status in statuses if status == "init"),
                min_tx_min_ms=min(min_txs) if min_txs else None,
                min_tx_max_ms=max(min_txs) if min_txs else None,
                min_rx_min_ms=min(min_rxs) if min_rxs else None,
                min_rx_max_ms=max(min_rxs) if min_rxs else None,
                sessions=sorted(
                    sessions,
                    key=lambda item: (
                        item.chassis_name or "",
                        item.logical_port or "",
                        item.dst_ip or "",
                        item.uuid,
                    ),
                ),
            ),
            ovsdb=OvsdbLatencyMetrics(
                measurement_mode="ovsdb_transact_select_plus_idl_sync",
                nb_probe_table=NB_LATENCY_PROBE_TABLE,
                sb_probe_table=SB_LATENCY_PROBE_TABLE,
                nb_transaction_latency_ms=nb_transaction_latency_ms,
                sb_transaction_latency_ms=sb_transaction_latency_ms,
                nb_idl_sync_latency_ms=nb_idl_sync_latency_ms,
                sb_idl_sync_latency_ms=sb_idl_sync_latency_ms,
            ),
            openflow_installation=OpenFlowInstallationLatencyMetrics(
                available=False,
                measurement_mode="requires_active_probe",
                reason=(
                    "Passive flow dump cannot infer time from NB commit to OVS flow installation. "
                    "Implement a canary resource trace to measure this dimension accurately."
                ),
            ),
        )
