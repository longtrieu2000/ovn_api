from __future__ import annotations

from fastapi import APIRouter

from ..services.cpu_monitor import get_cpu_monitor_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    service = get_cpu_monitor_service()
    snapshot = service.get_health_snapshot()
    return {
        "status": "ok",
        "collector_running": snapshot["collector_running"],
        "snapshot_ready": snapshot["snapshot_ready"],
        "history_size": snapshot["history_size"],
        "sample_interval_s": snapshot["sample_interval_s"],
        "last_generated_at": snapshot["last_generated_at"],
    }
