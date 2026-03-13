from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    ovn_nb_db: str
    ovn_nb_db_name: str
    ovn_nb_schema: str
    ovn_sb_db: str
    ovn_sb_db_name: str
    ovn_sb_schema: str
    ovn_idl_sync_timeout_s: float
    datapath_metrics_interval_s: float
    command_transport: str
    docker_bin: str
    ovn_nb_container: str
    ovn_sb_container: str
    ovs_vswitchd_container: str
    ovn_nbctl_bin: str
    ovs_appctl_bin: str
    ovs_ofctl_bin: str
    trace_store_url: str
    trace_store_max_runs: int
    live_monitoring_interval_s: float
    live_monitoring_latency_interval_s: float
    live_monitoring_ws_queue_size: int
    scheduled_trace_metrics_enabled: bool
    scheduled_trace_metrics_interval_s: float
    scheduled_trace_metrics_timeout_s: float
    scheduled_trace_metrics_poll_interval_ms: int
    scheduled_trace_metrics_default_bridge: str
    scheduled_trace_metrics_default_logical_switch_target_name: str | None
    scheduled_trace_metrics_default_logical_router_target_name: str | None
    scheduled_trace_metrics_profiles_json: str | None
    scheduled_trace_metrics_profiles_file: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        ovn_nb_db=os.getenv("OVN_NB_DB", "tcp:127.0.0.1:6641"),
        ovn_nb_db_name=os.getenv("OVN_NB_DB_NAME", "OVN_Northbound"),
        ovn_nb_schema=os.getenv("OVN_NB_SCHEMA", "/usr/share/ovn/ovn-nb.ovsschema"),
        ovn_sb_db=os.getenv("OVN_SB_DB", "tcp:127.0.0.1:6642"),
        ovn_sb_db_name=os.getenv("OVN_SB_DB_NAME", "OVN_Southbound"),
        ovn_sb_schema=os.getenv("OVN_SB_SCHEMA", "/usr/share/ovn/ovn-sb.ovsschema"),
        ovn_idl_sync_timeout_s=float(os.getenv("OVN_IDL_SYNC_TIMEOUT_S", "3.0")),
        datapath_metrics_interval_s=float(os.getenv("DATAPATH_METRICS_INTERVAL_S", "5.0")),
        command_transport=os.getenv("OVN_COMMAND_TRANSPORT", "docker-exec"),
        docker_bin=os.getenv("DOCKER_BIN", "docker"),
        ovn_nb_container=os.getenv("OVN_NB_CONTAINER", "ovn_nb_db"),
        ovn_sb_container=os.getenv("OVN_SB_CONTAINER", "ovn_sb_db"),
        ovs_vswitchd_container=os.getenv("OVS_VSWITCHD_CONTAINER", "openvswitch_vswitchd"),
        ovn_nbctl_bin=os.getenv("OVN_NBCTL_BIN", "ovn-nbctl"),
        ovs_appctl_bin=os.getenv("OVS_APPCTL_BIN", "ovs-appctl"),
        ovs_ofctl_bin=os.getenv("OVS_OFCTL_BIN", "ovs-ofctl"),
        trace_store_url=os.getenv("TRACE_STORE_URL", "sqlite:///./ovn_api/data/canary_traces.db"),
        trace_store_max_runs=int(os.getenv("TRACE_STORE_MAX_RUNS", "500")),
        live_monitoring_interval_s=float(os.getenv("LIVE_MONITORING_INTERVAL_S", "5.0")),
        live_monitoring_latency_interval_s=float(os.getenv("LIVE_MONITORING_LATENCY_INTERVAL_S", "15.0")),
        live_monitoring_ws_queue_size=int(os.getenv("LIVE_MONITORING_WS_QUEUE_SIZE", "32")),
        scheduled_trace_metrics_enabled=os.getenv("SCHEDULED_TRACE_METRICS_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        scheduled_trace_metrics_interval_s=float(os.getenv("SCHEDULED_TRACE_METRICS_INTERVAL_S", "60.0")),
        scheduled_trace_metrics_timeout_s=float(os.getenv("SCHEDULED_TRACE_METRICS_TIMEOUT_S", "15.0")),
        scheduled_trace_metrics_poll_interval_ms=int(os.getenv("SCHEDULED_TRACE_METRICS_POLL_INTERVAL_MS", "250")),
        scheduled_trace_metrics_default_bridge=os.getenv("SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE", "br-int"),
        scheduled_trace_metrics_default_logical_switch_target_name=(
            os.getenv("SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME") or None
        ),
        scheduled_trace_metrics_default_logical_router_target_name=(
            os.getenv("SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_ROUTER_TARGET_NAME") or None
        ),
        scheduled_trace_metrics_profiles_json=os.getenv("SCHEDULED_TRACE_METRICS_PROFILES_JSON") or None,
        scheduled_trace_metrics_profiles_file=os.getenv("SCHEDULED_TRACE_METRICS_PROFILES_FILE") or None,
    )
