from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..services.cpu_monitor import get_cpu_monitor_service

router = APIRouter()


@router.get("/monitoring/prometheus", response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    payload = get_cpu_monitor_service().render_prometheus_text()
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    return prometheus_metrics()
