from __future__ import annotations

import json
import os
import time
from threading import Lock
from typing import Iterable

from fastapi import HTTPException
from ovs.db.idl import Idl, SchemaHelper

from .command import CommandExecutor


class OvsdbIdlClient:
    def __init__(
        self,
        *,
        remote: str,
        schema_path: str,
        tables: Iterable[str],
        sync_timeout_s: float,
        label: str,
        schema_container: str | None = None,
        executor: CommandExecutor | None = None,
    ) -> None:
        self.remote = remote
        self.schema_path = schema_path
        self.tables = tuple(tables)
        self.sync_timeout_s = sync_timeout_s
        self.label = label
        self.schema_container = schema_container
        self.executor = executor
        self._idl: Idl | None = None
        self._lock = Lock()

    def get_idl(self) -> Idl:
        with self._lock:
            if self._idl is None:
                self._idl = self._create_idl()
            self._sync()
            return self._idl

    def _create_idl(self) -> Idl:
        try:
            helper = self._build_schema_helper()
            for table in self.tables:
                helper.register_table(table)
            return Idl(self.remote, helper)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to initialize {self.label} IDL. "
                    f"remote={self.remote!r} schema={self.schema_path!r} "
                    f"exc_type={type(exc).__name__} exc={exc!r}"
                ),
            ) from exc

    def _build_schema_helper(self) -> SchemaHelper:
        if os.path.exists(self.schema_path):
            return SchemaHelper(location=self.schema_path)

        if self.executor is not None and self.schema_container is not None:
            result = self.executor.run(
                ["cat", self.schema_path],
                container=self.schema_container,
            )
            try:
                schema_json = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Failed to parse {self.label} schema from container "
                        f"{self.schema_container!r} at {self.schema_path!r}: {exc}"
                    ),
                ) from exc
            return SchemaHelper(schema_json=schema_json)

        raise HTTPException(
            status_code=500,
            detail=(
                f"{self.label} schema file not found at {self.schema_path!r}. "
                "If OVN runs in Docker, set OVN_COMMAND_TRANSPORT=docker-exec and "
                "configure the matching OVN_*_CONTAINER environment variable."
            ),
        )

    def _sync(self) -> None:
        if self._idl is None:
            return

        start = time.monotonic()
        if not self._idl.has_ever_connected():
            while not self._idl.has_ever_connected():
                self._run_once()
                if time.monotonic() - start > self.sync_timeout_s:
                    self._idl = None
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            f"Timed out waiting for {self.label} initial sync after "
                            f"{self.sync_timeout_s}s (remote={self.remote!r})."
                        ),
                    )
            return

        self._run_once()

    def _run_once(self) -> None:
        if self._idl is None:
            return
        try:
            self._idl.run()
        except Exception as exc:
            self._idl = None
            raise HTTPException(
                status_code=500,
                detail=(
                    f"{self.label} IDL run() failed (remote={self.remote!r}): "
                    f"{type(exc).__name__}: {exc}"
                ),
            ) from exc
