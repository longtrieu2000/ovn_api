from __future__ import annotations

import threading
import time
from collections import defaultdict
from functools import lru_cache

from ..models.monitoring import ApiRuntimeMetrics


class ApiMetricsStore:
    def __init__(self) -> None:
        self._started_perf = time.perf_counter()
        self._lock = threading.Lock()
        self._http_requests_total = 0
        self._http_requests_in_flight = 0
        self._http_request_errors_total = 0
        self._http_request_duration_ms_sum = 0.0
        self._http_request_duration_ms_count = 0
        self._http_requests_by_method_status: dict[tuple[str, str], int] = defaultdict(int)
        self._websocket_clients_current = 0
        self._websocket_connections_total = 0
        self._websocket_messages_sent_total = 0

    def mark_http_request_started(self) -> None:
        with self._lock:
            self._http_requests_in_flight += 1

    def mark_http_request_finished(self, *, method: str, status_code: int, duration_ms: float, errored: bool) -> None:
        status_class = f"{max(status_code, 0) // 100}xx" if status_code > 0 else "error"
        with self._lock:
            self._http_requests_total += 1
            self._http_requests_in_flight = max(self._http_requests_in_flight - 1, 0)
            self._http_request_duration_ms_sum = round(self._http_request_duration_ms_sum + duration_ms, 3)
            self._http_request_duration_ms_count += 1
            if errored:
                self._http_request_errors_total += 1
            self._http_requests_by_method_status[(method.upper() or "UNKNOWN", status_class)] += 1

    def mark_websocket_connected(self) -> None:
        with self._lock:
            self._websocket_clients_current += 1
            self._websocket_connections_total += 1

    def mark_websocket_disconnected(self) -> None:
        with self._lock:
            self._websocket_clients_current = max(self._websocket_clients_current - 1, 0)

    def mark_websocket_message_sent(self) -> None:
        with self._lock:
            self._websocket_messages_sent_total += 1

    def get_snapshot(self) -> ApiRuntimeMetrics:
        with self._lock:
            return ApiRuntimeMetrics(
                uptime_s=round(time.perf_counter() - self._started_perf, 3),
                http_requests_total=self._http_requests_total,
                http_requests_in_flight=self._http_requests_in_flight,
                http_request_errors_total=self._http_request_errors_total,
                http_request_duration_ms_sum=self._http_request_duration_ms_sum,
                http_request_duration_ms_count=self._http_request_duration_ms_count,
                websocket_clients_current=self._websocket_clients_current,
                websocket_connections_total=self._websocket_connections_total,
                websocket_messages_sent_total=self._websocket_messages_sent_total,
            )

    def get_http_status_breakdown(self) -> dict[tuple[str, str], int]:
        with self._lock:
            return dict(self._http_requests_by_method_status)


@lru_cache(maxsize=1)
def get_api_metrics_store() -> ApiMetricsStore:
    return ApiMetricsStore()
