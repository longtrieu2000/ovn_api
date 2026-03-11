from __future__ import annotations

from fastapi import APIRouter, Query, status

from ..models.traces import (
    CanaryCapabilitiesResponse,
    CanaryProbeRequest,
    CanaryProbeResult,
    CanaryRunDetail,
    CanaryRunSummary,
)
from ..services.trace_manager import get_canary_trace_manager
from ..services.trace_service import CanaryTraceService


router = APIRouter()


@router.get("/traces/capabilities", response_model=CanaryCapabilitiesResponse)
def get_canary_trace_capabilities() -> CanaryCapabilitiesResponse:
    return CanaryTraceService().get_capabilities()


@router.post("/traces/canary", response_model=CanaryProbeResult)
def run_canary_probe(request: CanaryProbeRequest) -> CanaryProbeResult:
    return get_canary_trace_manager().run_sync(request)


@router.post("/traces/canary/runs", response_model=CanaryRunDetail, status_code=status.HTTP_202_ACCEPTED)
def enqueue_canary_probe(request: CanaryProbeRequest) -> CanaryRunDetail:
    return get_canary_trace_manager().submit(request)


@router.get("/traces/canary/runs", response_model=list[CanaryRunSummary])
def list_canary_probe_runs(limit: int = Query(default=20, ge=1, le=200)) -> list[CanaryRunSummary]:
    return get_canary_trace_manager().list_runs(limit=limit)


@router.get("/traces/canary/runs/{probe_id}", response_model=CanaryRunDetail)
def get_canary_probe_run(probe_id: str) -> CanaryRunDetail:
    return get_canary_trace_manager().get_run(probe_id)
