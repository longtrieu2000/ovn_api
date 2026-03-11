from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import HTTPException

from ..config import get_settings
from ..models.traces import CanaryProbeRequest, CanaryProbeResult, CanaryRunDetail, CanaryRunSummary, CanaryRunStatus
from .trace_service import CanaryTraceService
from .trace_store import PersistedCanaryRun, get_trace_store


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="milliseconds")


class CanaryTraceManager:
    def __init__(self, *, max_runs: int = 200) -> None:
        self.max_runs = max(max_runs, 20)
        self.trace_service = CanaryTraceService()
        self.trace_store = get_trace_store()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self.trace_store.initialize()
            self.trace_store.fail_stale_runs(
                reason="Marked failed because the API process restarted before the probe completed.",
                finished_at=_isoformat(_now_utc()) or "",
            )
            self._stop_event.clear()
            self._queue = queue.Queue()
            self._thread = threading.Thread(
                target=self._run,
                name="canary-trace-manager",
                daemon=True,
            )
            thread = self._thread
        thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
        if thread is not None:
            self._queue.put(None)
        if thread is not None:
            thread.join(timeout=5.0)

    def submit(self, request: CanaryProbeRequest) -> CanaryRunDetail:
        self.start()
        prepared = self.trace_service.prepare_probe(request)
        now = _isoformat(_now_utc()) or ""
        with self._lock:
            queue_depth = self._queue.qsize() + 1
        record = PersistedCanaryRun(
            probe_id=prepared.probe_id,
            prepared=prepared,
            request=request.model_copy(deep=True),
            status="queued",
            queued_at=now,
            updated_at=now,
            queue_depth=queue_depth,
        )
        self.trace_store.create_run(record)
        self.trace_store.prune_finished_runs(max_runs=self.max_runs)
        self._queue.put(prepared.probe_id)
        return self.get_run(prepared.probe_id)

    def run_sync(self, request: CanaryProbeRequest) -> CanaryProbeResult:
        self.trace_store.initialize()
        prepared = self.trace_service.prepare_probe(request)
        now = _isoformat(_now_utc()) or ""
        record = PersistedCanaryRun(
            probe_id=prepared.probe_id,
            prepared=prepared,
            request=request.model_copy(deep=True),
            status="running",
            queued_at=now,
            started_at=now,
            updated_at=now,
            queue_depth=0,
        )
        self.trace_store.create_run(record)
        try:
            result = self.trace_service.run_prepared_probe(prepared)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            finished_at = _isoformat(_now_utc()) or ""
            record.status = "failed"
            record.error = detail
            record.updated_at = finished_at
            record.finished_at = finished_at
            self.trace_store.update_run(record)
            self.trace_store.prune_finished_runs(max_runs=self.max_runs)
            raise
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            finished_at = _isoformat(_now_utc()) or ""
            record.status = "failed"
            record.error = f"Unexpected sync trace error: {type(exc).__name__}: {exc}"
            record.updated_at = finished_at
            record.finished_at = finished_at
            self.trace_store.update_run(record)
            self.trace_store.prune_finished_runs(max_runs=self.max_runs)
            raise

        finished_at = _isoformat(_now_utc()) or ""
        record.result = result.model_copy(deep=True)
        record.status = result.status
        record.error = None
        record.updated_at = finished_at
        record.finished_at = finished_at
        self.trace_store.update_run(record)
        self.trace_store.prune_finished_runs(max_runs=self.max_runs)
        return result

    def list_runs(self, *, limit: int = 20) -> list[CanaryRunSummary]:
        self.trace_store.initialize()
        records = self.trace_store.list_runs(limit=limit)
        return [self._to_summary(record) for record in records[:limit]]

    def get_run(self, probe_id: str) -> CanaryRunDetail:
        self.trace_store.initialize()
        record = self.trace_store.get_run(probe_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Canary probe {probe_id!r} not found.")
        return self._to_detail(record)

    def _run(self) -> None:
        while True:
            try:
                probe_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue

            if probe_id is None:
                self._queue.task_done()
                break

            record = self.trace_store.get_run(probe_id)
            if record is None:
                self._queue.task_done()
                continue
            now = _isoformat(_now_utc()) or ""
            record.status = "running"
            record.started_at = now
            record.updated_at = now
            self.trace_store.update_run(record)

            try:
                result = self.trace_service.run_prepared_probe(record.prepared)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                self._mark_failed(probe_id, detail)
            except Exception as exc:  # pragma: no cover - unexpected runtime failure
                self._mark_failed(probe_id, f"Unexpected trace worker error: {type(exc).__name__}: {exc}")
            else:
                self._mark_completed(probe_id, result)
            finally:
                self._queue.task_done()

    def _mark_completed(self, probe_id: str, result: CanaryProbeResult) -> None:
        record = self.trace_store.get_run(probe_id)
        if record is None:
            return
        finished_at = _isoformat(_now_utc()) or ""
        record.result = result.model_copy(deep=True)
        record.status = result.status
        record.error = None
        record.updated_at = finished_at
        record.finished_at = finished_at
        self.trace_store.update_run(record)
        self.trace_store.prune_finished_runs(max_runs=self.max_runs)

    def _mark_failed(self, probe_id: str, error: str) -> None:
        record = self.trace_store.get_run(probe_id)
        if record is None:
            return
        finished_at = _isoformat(_now_utc()) or ""
        record.status = "failed"
        record.error = error
        record.updated_at = finished_at
        record.finished_at = finished_at
        self.trace_store.update_run(record)
        self.trace_store.prune_finished_runs(max_runs=self.max_runs)

    def _to_summary(self, record: PersistedCanaryRun) -> CanaryRunSummary:
        result = record.result
        return CanaryRunSummary(
            probe_id=record.probe_id,
            requested_resource_type=record.prepared.requested_resource_type,
            resolved_resource_type=record.prepared.resolved_resource_type,
            resource_name=record.prepared.resource_name,
            target_name=record.prepared.target_name,
            status=record.status,
            queued_at=record.queued_at,
            started_at=(result.started_at if result is not None else record.started_at),
            updated_at=record.updated_at,
            finished_at=(result.finished_at if result is not None else record.finished_at),
            openflow_expected=record.prepared.openflow_expected,
            queue_depth=record.queue_depth,
            note=record.prepared.note,
        )

    def _to_detail(self, record: PersistedCanaryRun) -> CanaryRunDetail:
        summary = self._to_summary(record)
        return CanaryRunDetail(
            **summary.model_dump(),
            request=record.request.model_copy(deep=True),
            result=record.result.model_copy(deep=True) if record.result is not None else None,
            error=record.error,
        )


@lru_cache(maxsize=1)
def get_canary_trace_manager() -> CanaryTraceManager:
    settings = get_settings()
    return CanaryTraceManager(max_runs=settings.trace_store_max_runs)
