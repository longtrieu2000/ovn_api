from __future__ import annotations

import os
import time
import errno
from threading import Lock
from typing import Iterable

from fastapi import HTTPException
from ovs.db.idl import Idl, SchemaHelper
from ovs import jsonrpc, stream

class OvsdbIdlClient:
    def __init__(
        self,
        *,
        remote: str,
        schema_db_name: str,
        schema_path: str,
        tables: Iterable[str],
        sync_timeout_s: float,
        label: str,
    ) -> None:
        self.remote = remote
        self.schema_db_name = schema_db_name
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

        try:
            schema_json = self._fetch_schema_via_rpc()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to fetch {self.label} schema via OVSDB RPC. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r} "
                    f"exc_type={type(exc).__name__} exc={exc!r}"
                ),
            ) from exc

        try:
            return SchemaHelper(schema_json=schema_json)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to build SchemaHelper for {self.label} from OVSDB RPC result. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r} "
                    f"exc_type={type(exc).__name__} exc={exc!r}"
                ),
            ) from exc

    def _fetch_schema_via_rpc(self) -> dict:
        timeout_ms = int(self.sync_timeout_s * 1000)
        error, rpc_stream = stream.Stream.open_block(stream.Stream.open(self.remote), timeout=timeout_ms)
        if error or rpc_stream is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to open JSON-RPC stream to {self.label} at {self.remote!r}: "
                    f"{os.strerror(error) if error else 'unknown error'}"
                ),
            )

        rpc = jsonrpc.Connection(rpc_stream)
        try:
            request = jsonrpc.Message.create_request("get_schema", [self.schema_db_name])
            error, reply = rpc.transact_block(request)
        finally:
            rpc.close()

        if error:
            if error == errno.EOF:
                error_text = "connection closed"
            else:
                error_text = os.strerror(error)
            raise HTTPException(
                status_code=500,
                detail=(
                    f"OVSDB RPC get_schema failed for {self.label}. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r} error={error_text}"
                ),
            )

        if reply is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"OVSDB RPC get_schema returned no reply for {self.label}. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r}"
                ),
            )

        if reply.type == jsonrpc.Message.T_ERROR:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"OVSDB RPC get_schema returned error for {self.label}. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r} error={reply.error!r}"
                ),
            )

        if not isinstance(reply.result, dict):
            raise HTTPException(
                status_code=500,
                detail=(
                    f"OVSDB RPC get_schema returned unexpected result for {self.label}. "
                    f"remote={self.remote!r} db_name={self.schema_db_name!r}"
                ),
            )

        return reply.result

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
