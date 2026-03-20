from __future__ import annotations

from fastapi import APIRouter, Query

from ..config import get_settings
from ..models import CpuHistoryPoint, CpuSnapshot, CpuSpike, ThreadCpuSample
from ..services.cpu_monitor import get_cpu_monitor_service

router = APIRouter()


@router.get("/cpu/snapshot", response_model=CpuSnapshot)
def snapshot(
    threads_per_component: int | None = Query(default=None, ge=1, le=100),
    top_threads: int | None = Query(default=None, ge=1, le=500),
) -> CpuSnapshot:
    settings = get_settings()
    service = get_cpu_monitor_service()
    return service.get_snapshot(
        threads_per_component=threads_per_component or settings.default_threads_per_component,
        top_threads=top_threads or settings.default_top_threads,
    )


@router.get("/cpu/history", response_model=list[CpuHistoryPoint])
def history(limit: int | None = Query(default=None, ge=1, le=2000)) -> list[CpuHistoryPoint]:
    settings = get_settings()
    service = get_cpu_monitor_service()
    return service.get_history(limit=limit or settings.default_history_limit)


@router.get("/cpu/threads", response_model=list[ThreadCpuSample])
def threads(
    component: str | None = Query(default=None),
    thread_group: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    min_cpu_pct: float = Query(default=0.0, ge=0.0),
) -> list[ThreadCpuSample]:
    settings = get_settings()
    service = get_cpu_monitor_service()
    return service.get_threads(
        component=component,
        thread_group=thread_group,
        limit=limit or settings.default_top_threads,
        min_cpu_pct=min_cpu_pct,
    )


@router.get("/cpu/spikes", response_model=list[CpuSpike])
def spikes(
    component: str | None = Query(default=None),
    threshold_pct: float = Query(default=50.0, ge=0.0),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[CpuSpike]:
    service = get_cpu_monitor_service()
    return service.find_spikes(component=component, threshold_pct=threshold_pct, limit=limit)
