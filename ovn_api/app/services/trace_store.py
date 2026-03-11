from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import Boolean, Integer, MetaData, Table, Column, Text, create_engine, delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ..config import get_settings
from ..models.traces import CanaryProbeRequest, CanaryProbeResult, CanaryRunStatus
from .trace_service import PreparedProbe


metadata = MetaData()

canary_trace_runs = Table(
    "canary_trace_runs",
    metadata,
    Column("probe_id", Text, primary_key=True),
    Column("requested_resource_type", Text, nullable=False),
    Column("resolved_resource_type", Text, nullable=False),
    Column("resource_name", Text, nullable=False),
    Column("target_name", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("queued_at", Text, nullable=False),
    Column("started_at", Text, nullable=True),
    Column("updated_at", Text, nullable=False),
    Column("finished_at", Text, nullable=True),
    Column("openflow_expected", Boolean, nullable=False),
    Column("queue_depth", Integer, nullable=True),
    Column("note", Text, nullable=True),
    Column("request_json", Text, nullable=False),
    Column("prepared_json", Text, nullable=False),
    Column("result_json", Text, nullable=True),
    Column("error", Text, nullable=True),
)


@dataclass
class PersistedCanaryRun:
    probe_id: str
    request: CanaryProbeRequest
    prepared: PreparedProbe
    status: CanaryRunStatus
    queued_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    queue_depth: int | None = None
    result: CanaryProbeResult | None = None
    error: str | None = None


class SqlCanaryTraceStore:
    def __init__(self, *, url: str) -> None:
        self.url = url
        self.engine = self._create_engine(url)

    def initialize(self) -> None:
        self._ensure_sqlite_parent_dir()
        try:
            metadata.create_all(self.engine)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to initialize trace store: {exc}") from exc

    def create_run(self, run: PersistedCanaryRun) -> None:
        payload = self._serialize_run(run)
        try:
            with self.engine.begin() as connection:
                connection.execute(canary_trace_runs.insert().values(**payload))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to persist canary run {run.probe_id!r}: {exc}") from exc

    def update_run(self, run: PersistedCanaryRun) -> None:
        payload = self._serialize_run(run)
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(canary_trace_runs).where(canary_trace_runs.c.probe_id == run.probe_id).values(**payload)
                )
                if result.rowcount == 0:
                    raise HTTPException(status_code=404, detail=f"Canary probe {run.probe_id!r} not found in trace store.")
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to update canary run {run.probe_id!r}: {exc}") from exc

    def get_run(self, probe_id: str) -> PersistedCanaryRun | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(canary_trace_runs).where(canary_trace_runs.c.probe_id == probe_id)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to load canary run {probe_id!r}: {exc}") from exc
        if row is None:
            return None
        return self._deserialize_run(dict(row))

    def list_runs(self, *, limit: int) -> list[PersistedCanaryRun]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(canary_trace_runs).order_by(canary_trace_runs.c.queued_at.desc()).limit(limit)
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to list canary runs: {exc}") from exc
        return [self._deserialize_run(dict(row)) for row in rows]

    def fail_stale_runs(self, *, reason: str, finished_at: str) -> int:
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(canary_trace_runs)
                    .where(canary_trace_runs.c.status.in_(("queued", "running")))
                    .values(
                        status="failed",
                        error=reason,
                        updated_at=finished_at,
                        finished_at=finished_at,
                    )
                )
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to recover stale canary runs: {exc}") from exc

    def prune_finished_runs(self, *, max_runs: int) -> int:
        try:
            with self.engine.begin() as connection:
                finished_probe_ids = [
                    row[0]
                    for row in connection.execute(
                        select(canary_trace_runs.c.probe_id)
                        .where(~canary_trace_runs.c.status.in_(("queued", "running")))
                        .order_by(canary_trace_runs.c.queued_at.desc())
                    ).all()
                ]
                removable_probe_ids = finished_probe_ids[max_runs:]
                if not removable_probe_ids:
                    return 0
                connection.execute(delete(canary_trace_runs).where(canary_trace_runs.c.probe_id.in_(removable_probe_ids)))
                return len(removable_probe_ids)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to prune old canary runs: {exc}") from exc

    def _create_engine(self, url: str) -> Engine:
        if url.startswith("sqlite:"):
            return create_engine(url, future=True, connect_args={"check_same_thread": False})
        return create_engine(url, future=True)

    def _ensure_sqlite_parent_dir(self) -> None:
        if not self.url.startswith("sqlite:///"):
            return
        sqlite_path = self.url.removeprefix("sqlite:///")
        if sqlite_path == ":memory:":
            return
        Path(sqlite_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def _serialize_run(self, run: PersistedCanaryRun) -> dict[str, object]:
        return {
            "probe_id": run.probe_id,
            "requested_resource_type": run.prepared.requested_resource_type,
            "resolved_resource_type": run.prepared.resolved_resource_type,
            "resource_name": run.prepared.resource_name,
            "target_name": run.prepared.target_name,
            "status": run.status,
            "queued_at": run.queued_at,
            "started_at": run.started_at,
            "updated_at": run.updated_at,
            "finished_at": run.finished_at,
            "openflow_expected": run.prepared.openflow_expected,
            "queue_depth": run.queue_depth,
            "note": run.prepared.note,
            "request_json": run.request.model_dump_json(),
            "prepared_json": json.dumps(asdict(run.prepared), ensure_ascii=True),
            "result_json": run.result.model_dump_json() if run.result is not None else None,
            "error": run.error,
        }

    def _deserialize_run(self, payload: dict[str, object]) -> PersistedCanaryRun:
        request = CanaryProbeRequest.model_validate_json(str(payload["request_json"]))
        prepared = PreparedProbe(**json.loads(str(payload["prepared_json"])))
        result_json = payload.get("result_json")
        return PersistedCanaryRun(
            probe_id=str(payload["probe_id"]),
            request=request,
            prepared=prepared,
            status=str(payload["status"]),
            queued_at=str(payload["queued_at"]),
            started_at=str(payload["started_at"]) if payload.get("started_at") is not None else None,
            updated_at=str(payload["updated_at"]),
            finished_at=str(payload["finished_at"]) if payload.get("finished_at") is not None else None,
            queue_depth=int(payload["queue_depth"]) if payload.get("queue_depth") is not None else None,
            result=CanaryProbeResult.model_validate_json(str(result_json)) if result_json is not None else None,
            error=str(payload["error"]) if payload.get("error") is not None else None,
        )


@lru_cache(maxsize=1)
def get_trace_store() -> SqlCanaryTraceStore:
    settings = get_settings()
    return SqlCanaryTraceStore(url=settings.trace_store_url)
