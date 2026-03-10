from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .command import CommandExecutor
from .ovsdb import OvsdbIdlClient


SB_TABLES = (
    "BFD",
    "Chassis",
    "Chassis_Private",
    "Datapath_Binding",
    "Encap",
    "Port_Binding",
)


@lru_cache(maxsize=1)
def get_ovn_sb_client() -> OvsdbIdlClient:
    settings = get_settings()
    return OvsdbIdlClient(
        remote=settings.ovn_sb_db,
        schema_path=settings.ovn_sb_schema,
        tables=SB_TABLES,
        sync_timeout_s=settings.ovn_idl_sync_timeout_s,
        label="OVN Southbound",
        schema_container=settings.ovn_sb_container,
        executor=CommandExecutor(
            transport=settings.command_transport,
            docker_bin=settings.docker_bin,
        ),
    )
