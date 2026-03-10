from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..models.health import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        ovn_nb_db=settings.ovn_nb_db,
        ovn_nb_schema=settings.ovn_nb_schema,
        ovn_sb_db=settings.ovn_sb_db,
        ovn_sb_schema=settings.ovn_sb_schema,
        command_transport=settings.command_transport,
        docker_bin=settings.docker_bin,
        ovn_nb_container=settings.ovn_nb_container,
        ovn_sb_container=settings.ovn_sb_container,
        ovs_vswitchd_container=settings.ovs_vswitchd_container,
    )
