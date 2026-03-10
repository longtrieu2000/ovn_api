from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .ovsdb import OvsdbIdlClient


NB_TABLES = (
    "ACL",
    "Load_Balancer",
    "Logical_Router",
    "Logical_Router_Port",
    "Logical_Switch",
    "Logical_Switch_Port",
    "NAT",
)


@lru_cache(maxsize=1)
def get_ovn_nb_client() -> OvsdbIdlClient:
    settings = get_settings()
    return OvsdbIdlClient(
        remote=settings.ovn_nb_db,
        schema_db_name=settings.ovn_nb_db_name,
        schema_path=settings.ovn_nb_schema,
        tables=NB_TABLES,
        sync_timeout_s=settings.ovn_idl_sync_timeout_s,
        label="OVN Northbound",
    )
