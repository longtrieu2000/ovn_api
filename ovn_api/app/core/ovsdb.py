from __future__ import annotations

import os
import time
from threading import Lock
from typing import Iterable

from fastapi import HTTPException
from ovs.db.idl import Idl, SchemaHelper


class OvsdbIdlClient:
    def __init__(
        self,
        *,
        remote: str,
        schema_path: str,
        tables: Iterable[str],
        sync_timeout_s: float,
        label: str,
    ) -> None:
        self.remote = remote
        self.schema_path = schema_path
        self.tables = tuple(tables)
        self.sync_timeout_s = sync_timeout_s
        self.label = label
        self._idl: Idl | None = None
        self._lock = Lock()

    def get_idl(self) -> Idl:
        with self._lock:
            if self._idl is None:
                self._idl = self._create_idl()
            self._sync()
            return self._idl

    def _create_idl(self) -> Idl:
        if not os.path.exists(self.schema_path):
            raise HTTPException(
                status_code=500,
                detail=(
                    f"{self.label} schema file not found at {self.schema_path!r}. "
                    "Set the schema path via environment or mount the matching OVN schema."
                ),
            )

        try:
            helper = SchemaHelper(location=self.schema_path)
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
