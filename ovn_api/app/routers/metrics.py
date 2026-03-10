from __future__ import annotations

from fastapi import APIRouter

from ..models.metrics import CapacityMetrics, DatapathMetrics, LatencyMetrics
from ..services.metrics_service import MetricsService


router = APIRouter()


@router.get("/metrics/capacity", response_model=CapacityMetrics)
def get_capacity_metrics() -> CapacityMetrics:
    return MetricsService().get_capacity_metrics()


@router.get("/metrics/datapath", response_model=DatapathMetrics)
def get_datapath_metrics() -> DatapathMetrics:
    return MetricsService().get_datapath_metrics()


@router.get("/metrics/latency", response_model=LatencyMetrics)
def get_latency_metrics() -> LatencyMetrics:
    return MetricsService().get_latency_metrics()
