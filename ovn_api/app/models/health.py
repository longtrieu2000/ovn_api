from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    ovn_nb_db: str
    ovn_nb_schema: str
    ovn_sb_db: str
    ovn_sb_schema: str
    command_transport: str
    docker_bin: str
    ovn_nb_container: str
    ovn_sb_container: str
    ovs_vswitchd_container: str
