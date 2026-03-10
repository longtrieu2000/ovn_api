from __future__ import annotations

from fastapi import APIRouter

from ..models.chassis import ChassisBindingsResponse, ChassisSummary
from ..services.chassis_service import ChassisService


router = APIRouter()


@router.get("/chassis", response_model=list[ChassisSummary])
def list_chassis() -> list[ChassisSummary]:
    return ChassisService().list_chassis()


@router.get("/chassis/{chassis_ref}/bindings", response_model=ChassisBindingsResponse)
def get_chassis_bindings(chassis_ref: str) -> ChassisBindingsResponse:
    return ChassisService().get_chassis_bindings(chassis_ref=chassis_ref)
