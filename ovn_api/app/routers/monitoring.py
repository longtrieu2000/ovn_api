from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from ..models.monitoring import MonitoringEvent, MonitoringSnapshot
from ..services.api_metrics import get_api_metrics_store
from ..services.live_monitoring_service import get_live_monitoring_service


router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@router.get("/monitoring/live", response_model=MonitoringSnapshot)
def get_live_monitoring_snapshot() -> MonitoringSnapshot:
    return get_live_monitoring_service().get_snapshot()


@router.get("/monitoring/prometheus", response_class=PlainTextResponse)
def get_prometheus_metrics() -> PlainTextResponse:
    payload = get_live_monitoring_service().render_prometheus_text()
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.websocket("/ws/monitoring/live")
async def stream_live_monitoring(websocket: WebSocket) -> None:
    monitoring_service = get_live_monitoring_service()
    api_metrics = get_api_metrics_store()
    heartbeat_s = 15.0
    send_initial = websocket.query_params.get("send_initial", "true").lower() != "false"

    subscription = monitoring_service.subscribe()
    await websocket.accept()

    try:
        if send_initial:
            snapshot = monitoring_service.get_snapshot_or_none()
            if snapshot is not None:
                initial_event = MonitoringEvent(
                    event="snapshot",
                    emitted_at=snapshot.generated_at,
                    sequence=snapshot.sequence,
                    snapshot=snapshot,
                )
                await websocket.send_json(initial_event.model_dump(mode="json"))
                api_metrics.mark_websocket_message_sent()

        while True:
            event = await run_in_threadpool(monitoring_service.poll_event, subscription.subscription_id, heartbeat_s)
            if event is None:
                heartbeat_event = MonitoringEvent(
                    event="heartbeat",
                    emitted_at=_now_iso(),
                    sequence=None,
                )
                await websocket.send_json(heartbeat_event.model_dump(mode="json"))
                api_metrics.mark_websocket_message_sent()
                continue

            await websocket.send_json(event.model_dump(mode="json"))
            api_metrics.mark_websocket_message_sent()
    except WebSocketDisconnect:
        return
    finally:
        monitoring_service.unsubscribe(subscription.subscription_id)
