from __future__ import annotations

import time

from .typing import ASGIApp, Message, Receive, Scope, Send
from ..services.api_metrics import get_api_metrics_store


class ApiMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.metrics = get_api_metrics_store()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type == "http":
            await self._handle_http(scope, receive, send)
            return
        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        method = str(scope.get("method", "UNKNOWN"))
        started_at = time.perf_counter()
        status_code = 500
        self.metrics.mark_http_request_started()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        errored = False
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            errored = True
            raise
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            self.metrics.mark_http_request_finished(
                method=method,
                status_code=status_code,
                duration_ms=duration_ms,
                errored=errored or status_code >= 500,
            )

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.metrics.mark_websocket_connected()
        try:
            await self.app(scope, receive, send)
        finally:
            self.metrics.mark_websocket_disconnected()
