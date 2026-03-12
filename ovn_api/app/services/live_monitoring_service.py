from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import HTTPException

from ..config import get_settings
from ..models.monitoring import (
    MonitoringComponentStatus,
    MonitoringEvent,
    MonitoringSnapshot,
    TraceRuntimeMetrics,
)
from ..models.traces import CanaryRunSummary
from .api_metrics import get_api_metrics_store
from .metrics_service import MetricsService
from .trace_manager import get_canary_trace_manager


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="milliseconds")


@dataclass
class _ComponentState:
    data: object | None = None
    updated_at: datetime | None = None
    error: str | None = None


@dataclass
class MonitoringSubscription:
    subscription_id: str
    events: queue.Queue[MonitoringEvent]


class LiveMonitoringService:
    def __init__(
        self,
        *,
        interval_s: float,
        latency_interval_s: float,
        queue_size: int,
    ) -> None:
        self.interval_s = max(interval_s, 1.0)
        self.latency_interval_s = max(latency_interval_s, self.interval_s)
        self.queue_size = max(queue_size, 4)
        self.metrics_service = MetricsService()
        self.trace_manager = get_canary_trace_manager()
        self.api_metrics = get_api_metrics_store()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0
        self._snapshot: MonitoringSnapshot | None = None
        self._capacity = _ComponentState()
        self._datapath = _ComponentState()
        self._latency = _ComponentState()
        self._next_latency_refresh_at = 0.0
        self._subscriptions: dict[str, queue.Queue[MonitoringEvent]] = {}
        self._listener_registered = False

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="live-monitoring-service",
                daemon=True,
            )
            thread = self._thread

        self.trace_manager.start()
        self._register_trace_listener()
        self._refresh_safely(force_latency=True)
        thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()

        if thread is not None:
            thread.join(timeout=self.interval_s + 1.0)
        self._unregister_trace_listener()

    def get_snapshot(self) -> MonitoringSnapshot:
        self.start()
        with self._lock:
            if self._snapshot is not None:
                return self._snapshot.model_copy(deep=True)
        raise HTTPException(status_code=503, detail="Live monitoring snapshot is not ready yet.")

    def get_snapshot_or_none(self) -> MonitoringSnapshot | None:
        self.start()
        with self._lock:
            if self._snapshot is None:
                return None
            return self._snapshot.model_copy(deep=True)

    def subscribe(self) -> MonitoringSubscription:
        self.start()
        subscription_id = str(uuid.uuid4())
        event_queue: queue.Queue[MonitoringEvent] = queue.Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscriptions[subscription_id] = event_queue
        return MonitoringSubscription(subscription_id=subscription_id, events=event_queue)

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            self._subscriptions.pop(subscription_id, None)

    def poll_event(self, subscription_id: str, timeout_s: float) -> MonitoringEvent | None:
        with self._lock:
            event_queue = self._subscriptions.get(subscription_id)
        if event_queue is None:
            return None
        try:
            return event_queue.get(timeout=max(timeout_s, 0.1))
        except queue.Empty:
            return None

    def publish_trace_run(self, summary: CanaryRunSummary) -> None:
        emitted_at = _isoformat(_now_utc()) or ""
        event = MonitoringEvent(
            event="trace_run",
            emitted_at=emitted_at,
            sequence=self._sequence,
            trace_run=summary.model_copy(deep=True),
        )
        self._publish_event(event)

    def render_prometheus_text(self) -> str:
        snapshot = self.get_snapshot_or_none()
        api_runtime = self.api_metrics.get_snapshot()
        http_breakdown = self.api_metrics.get_http_status_breakdown()

        lines: list[str] = []
        self._append_metric(lines, "ovn_api_exporter_up", 1)
        self._append_metric(lines, "ovn_api_uptime_seconds", api_runtime.uptime_s)

        if snapshot is None:
            self._append_metric(lines, "ovn_api_monitoring_snapshot_ready", 0)
        else:
            self._append_metric(lines, "ovn_api_monitoring_snapshot_ready", 1)
            self._append_metric(lines, "ovn_api_monitoring_sequence", snapshot.sequence)
            self._append_metric(
                lines,
                "ovn_api_monitoring_component_up",
                1 if snapshot.capacity_status.available else 0,
                labels={"component": "capacity"},
            )
            self._append_metric(
                lines,
                "ovn_api_monitoring_component_up",
                1 if snapshot.datapath_status.available else 0,
                labels={"component": "datapath"},
            )
            self._append_metric(
                lines,
                "ovn_api_monitoring_component_up",
                1 if snapshot.latency_status.available else 0,
                labels={"component": "latency"},
            )
            self._append_optional_metric(
                lines,
                "ovn_api_monitoring_component_age_seconds",
                snapshot.capacity_status.age_s,
                labels={"component": "capacity"},
            )
            self._append_optional_metric(
                lines,
                "ovn_api_monitoring_component_age_seconds",
                snapshot.datapath_status.age_s,
                labels={"component": "datapath"},
            )
            self._append_optional_metric(
                lines,
                "ovn_api_monitoring_component_age_seconds",
                snapshot.latency_status.age_s,
                labels={"component": "latency"},
            )

            if snapshot.capacity is not None:
                self._append_metric(lines, "ovn_api_capacity_logical_flows", snapshot.capacity.logical_flow_count)
                self._append_metric(lines, "ovn_api_capacity_logical_switches", snapshot.capacity.logical_switch_count)
                self._append_metric(lines, "ovn_api_capacity_logical_switch_ports", snapshot.capacity.logical_switch_port_count)
                self._append_metric(lines, "ovn_api_capacity_logical_routers", snapshot.capacity.logical_router_count)
                self._append_metric(lines, "ovn_api_capacity_logical_router_ports", snapshot.capacity.logical_router_port_count)
                self._append_metric(lines, "ovn_api_capacity_acls", snapshot.capacity.acl_count)
                self._append_metric(lines, "ovn_api_capacity_nats", snapshot.capacity.nat_count)
                self._append_metric(lines, "ovn_api_capacity_load_balancers", snapshot.capacity.load_balancer_count)

            if snapshot.datapath is not None:
                self._append_metric(lines, "ovn_api_datapath_flows", snapshot.datapath.datapath_flows)
                self._append_metric(
                    lines,
                    "ovn_api_datapath_lookups_total",
                    snapshot.datapath.lookups_hit,
                    labels={"result": "hit"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_datapath_lookups_total",
                    snapshot.datapath.lookups_missed,
                    labels={"result": "missed"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_datapath_lookups_total",
                    snapshot.datapath.lookups_lost,
                    labels={"result": "lost"},
                )
                self._append_optional_metric(lines, "ovn_api_datapath_cache_hit_rate_percent", snapshot.datapath.cache_hit_rate)
                self._append_optional_metric(lines, "ovn_api_datapath_mask_hit_per_pkt", snapshot.datapath.mask_hit_per_pkt)

            if snapshot.latency is not None:
                self._append_metric(
                    lines,
                    "ovn_api_ovsdb_transaction_latency_ms",
                    snapshot.latency.ovsdb.nb_transaction_latency_ms,
                    labels={"db": "nb"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_ovsdb_transaction_latency_ms",
                    snapshot.latency.ovsdb.sb_transaction_latency_ms,
                    labels={"db": "sb"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_ovsdb_idl_sync_latency_ms",
                    snapshot.latency.ovsdb.nb_idl_sync_latency_ms,
                    labels={"db": "nb"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_ovsdb_idl_sync_latency_ms",
                    snapshot.latency.ovsdb.sb_idl_sync_latency_ms,
                    labels={"db": "sb"},
                )
                self._append_metric(
                    lines,
                    "ovn_api_bfd_sessions",
                    snapshot.latency.bfd.session_count,
                    labels={"status": "total"},
                )
                self._append_metric(lines, "ovn_api_bfd_sessions", snapshot.latency.bfd.up_count, labels={"status": "up"})
                self._append_metric(lines, "ovn_api_bfd_sessions", snapshot.latency.bfd.down_count, labels={"status": "down"})
                self._append_metric(
                    lines,
                    "ovn_api_bfd_sessions",
                    snapshot.latency.bfd.admin_down_count,
                    labels={"status": "admin_down"},
                )
                self._append_metric(lines, "ovn_api_bfd_sessions", snapshot.latency.bfd.init_count, labels={"status": "init"})
                self._append_optional_metric(
                    lines,
                    "ovn_api_bfd_min_tx_ms",
                    snapshot.latency.bfd.min_tx_min_ms,
                    labels={"aggregation": "min"},
                )
                self._append_optional_metric(
                    lines,
                    "ovn_api_bfd_min_tx_ms",
                    snapshot.latency.bfd.min_tx_max_ms,
                    labels={"aggregation": "max"},
                )
                self._append_optional_metric(
                    lines,
                    "ovn_api_bfd_min_rx_ms",
                    snapshot.latency.bfd.min_rx_min_ms,
                    labels={"aggregation": "min"},
                )
                self._append_optional_metric(
                    lines,
                    "ovn_api_bfd_min_rx_ms",
                    snapshot.latency.bfd.min_rx_max_ms,
                    labels={"aggregation": "max"},
                )

            self._append_metric(lines, "ovn_api_trace_queue_depth", snapshot.trace_runtime.queue_depth)
            self._append_metric(lines, "ovn_api_trace_worker_up", 1 if snapshot.trace_runtime.worker_alive else 0)
            self._append_metric(lines, "ovn_api_trace_max_runs", snapshot.trace_runtime.max_runs)

        self._append_metric(lines, "ovn_api_http_requests_total", api_runtime.http_requests_total)
        self._append_metric(lines, "ovn_api_http_requests_in_flight", api_runtime.http_requests_in_flight)
        self._append_metric(lines, "ovn_api_http_request_errors_total", api_runtime.http_request_errors_total)
        self._append_metric(lines, "ovn_api_http_request_duration_ms_sum", api_runtime.http_request_duration_ms_sum)
        self._append_metric(lines, "ovn_api_http_request_duration_ms_count", api_runtime.http_request_duration_ms_count)
        self._append_metric(lines, "ovn_api_websocket_clients", api_runtime.websocket_clients_current)
        self._append_metric(lines, "ovn_api_websocket_connections_total", api_runtime.websocket_connections_total)
        self._append_metric(lines, "ovn_api_websocket_messages_sent_total", api_runtime.websocket_messages_sent_total)

        for (method, status_class), value in sorted(http_breakdown.items()):
            self._append_metric(
                lines,
                "ovn_api_http_requests_by_method_status_total",
                value,
                labels={"method": method, "status_class": status_class},
            )

        return "".join(lines)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            try:
                self._refresh_safely(force_latency=False)
            except Exception:
                continue

    def _register_trace_listener(self) -> None:
        with self._lock:
            if self._listener_registered:
                return
            self._listener_registered = True
        self.trace_manager.register_listener(self.publish_trace_run)

    def _unregister_trace_listener(self) -> None:
        with self._lock:
            if not self._listener_registered:
                return
            self._listener_registered = False
        self.trace_manager.unregister_listener(self.publish_trace_run)

    def _refresh_safely(self, *, force_latency: bool) -> None:
        now = time.monotonic()
        should_refresh_latency = force_latency or now >= self._next_latency_refresh_at or self._latency.data is None
        if should_refresh_latency:
            self._next_latency_refresh_at = now + self.latency_interval_s

        snapshot = self._collect_snapshot(refresh_latency=should_refresh_latency)
        with self._lock:
            self._sequence += 1
            snapshot.sequence = self._sequence
            self._snapshot = snapshot

        self._publish_event(
            MonitoringEvent(
                event="snapshot",
                emitted_at=snapshot.generated_at,
                sequence=snapshot.sequence,
                snapshot=snapshot.model_copy(deep=True),
            )
        )

    def _collect_snapshot(self, *, refresh_latency: bool) -> MonitoringSnapshot:
        now = _now_utc()
        errors: list[str] = []

        self._update_capacity_state()
        self._update_datapath_state()
        if refresh_latency:
            self._update_latency_state()

        trace_runtime = TraceRuntimeMetrics(**self.trace_manager.get_runtime_metrics())
        api_runtime = self.api_metrics.get_snapshot()
        capacity_status = self._component_status(self._capacity, now)
        datapath_status = self._component_status(self._datapath, now)
        latency_status = self._component_status(self._latency, now)

        if capacity_status.error:
            errors.append(f"capacity: {capacity_status.error}")
        if datapath_status.error:
            errors.append(f"datapath: {datapath_status.error}")
        if latency_status.error:
            errors.append(f"latency: {latency_status.error}")

        status = "degraded" if errors else "ok"
        return MonitoringSnapshot(
            sequence=0,
            generated_at=_isoformat(now) or "",
            status=status,
            interval_s=self.interval_s,
            capacity=self._capacity.data,
            datapath=self._datapath.data,
            latency=self._latency.data,
            capacity_status=capacity_status,
            datapath_status=datapath_status,
            latency_status=latency_status,
            trace_runtime=trace_runtime,
            api_runtime=api_runtime,
            errors=errors,
        )

    def _update_capacity_state(self) -> None:
        try:
            data = self.metrics_service.get_capacity_metrics()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            self._capacity.error = detail
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            self._capacity.error = f"Unexpected capacity refresh error: {type(exc).__name__}: {exc}"
            return
        self._capacity.data = data
        self._capacity.updated_at = _now_utc()
        self._capacity.error = None

    def _update_datapath_state(self) -> None:
        try:
            data = self.metrics_service.get_datapath_metrics()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            self._datapath.error = detail
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            self._datapath.error = f"Unexpected datapath refresh error: {type(exc).__name__}: {exc}"
            return
        self._datapath.data = data
        self._datapath.updated_at = _now_utc()
        self._datapath.error = None

    def _update_latency_state(self) -> None:
        try:
            data = self.metrics_service.get_latency_metrics()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            self._latency.error = detail
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            self._latency.error = f"Unexpected latency refresh error: {type(exc).__name__}: {exc}"
            return
        self._latency.data = data
        self._latency.updated_at = _now_utc()
        self._latency.error = None

    def _component_status(self, state: _ComponentState, now: datetime) -> MonitoringComponentStatus:
        age_s: float | None = None
        if state.updated_at is not None:
            age_s = round((now - state.updated_at).total_seconds(), 3)
        return MonitoringComponentStatus(
            available=state.data is not None,
            updated_at=_isoformat(state.updated_at),
            age_s=age_s,
            error=state.error,
        )

    def _publish_event(self, event: MonitoringEvent) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions.values())

        for event_queue in subscriptions:
            try:
                event_queue.put_nowait(event)
            except queue.Full:
                try:
                    event_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    event_queue.put_nowait(event)
                except queue.Full:
                    continue

    def _append_metric(
        self,
        lines: list[str],
        name: str,
        value: int | float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        if labels:
            rendered_labels = ",".join(
                f'{key}="{self._escape_label_value(raw_value)}"'
                for key, raw_value in sorted(labels.items())
            )
            lines.append(f"{name}{{{rendered_labels}}} {value}\n")
            return
        lines.append(f"{name} {value}\n")

    def _append_optional_metric(
        self,
        lines: list[str],
        name: str,
        value: int | float | None,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        if value is None:
            return
        self._append_metric(lines, name, value, labels=labels)

    def _escape_label_value(self, raw_value: object) -> str:
        return str(raw_value).replace("\\", "\\\\").replace('"', '\\"')


@lru_cache(maxsize=1)
def get_live_monitoring_service() -> LiveMonitoringService:
    settings = get_settings()
    return LiveMonitoringService(
        interval_s=settings.live_monitoring_interval_s,
        latency_interval_s=settings.live_monitoring_latency_interval_s,
        queue_size=settings.live_monitoring_ws_queue_size,
    )
