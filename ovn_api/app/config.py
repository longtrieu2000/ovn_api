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
    ovs_appctl_bin: str
    ovs_ofctl_bin: str


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
        ovs_appctl_bin=os.getenv("OVS_APPCTL_BIN", "ovs-appctl"),
        ovs_ofctl_bin=os.getenv("OVS_OFCTL_BIN", "ovs-ofctl"),
    )
