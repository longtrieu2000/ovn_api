from __future__ import annotations

from fastapi import APIRouter

from ..models.metrics import CapacityMetrics, LatencyMetrics
from ..services.metrics_service import MetricsService


router = APIRouter()


@router.get("/metrics/capacity", response_model=CapacityMetrics)
def get_capacity_metrics() -> CapacityMetrics:
    return MetricsService().get_capacity_metrics()


@router.get("/metrics/latency", response_model=LatencyMetrics)
def get_latency_metrics() -> LatencyMetrics:
    return MetricsService().get_latency_metrics()
