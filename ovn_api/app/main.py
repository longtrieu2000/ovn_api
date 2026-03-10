from typing import Any, Dict, List

import os
import subprocess
import time

from fastapi import FastAPI, HTTPException

from ovs.db import idl
OVN_NB_DB = os.getenv("OVN_NB_DB", "tcp:127.0.0.1:6641")
OVN_NB_SCHEMA = os.getenv("OVN_NB_SCHEMA", "/usr/share/ovn/ovn-nb.ovsschema")


def _build_schema_helper() -> idl.SchemaHelper:
    """Build a SchemaHelper for OVN Northbound.

    This dev API expects the OVN Northbound schema to exist as a local file.
    """
    if not os.path.exists(OVN_NB_SCHEMA):
        raise HTTPException(
            status_code=500,
            detail=(
                f"OVN_NB_SCHEMA not found at {OVN_NB_SCHEMA!r}. "
                "Copy it from your OVN container, e.g.: "
                "'docker cp ovn_nb_db:/usr/share/ovn/ovn-nb.ovsschema "
                "/tmp/ovn-nb.ovsschema' then 'export OVN_NB_SCHEMA=/tmp/ovn-nb.ovsschema'."
            ),
        )

    try:
        helper = idl.SchemaHelper(location=OVN_NB_SCHEMA)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to load OVN NB schema file. "
                f"OVN_NB_SCHEMA={OVN_NB_SCHEMA!r}. "
                f"exc_type={type(exc).__name__}. "
                f"exc={exc!r}"
            ),
        ) from exc

    helper.register_table("Logical_Flow")
    return helper


def _get_idl() -> idl.Idl:
    """Create a simple IDL connection to the OVN Northbound DB.

    This is intentionally minimal and not pooled; good enough for
    development and testing.
    """
    schema_helper = _build_schema_helper()
    try:
        return idl.Idl(OVN_NB_DB, schema_helper)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to initialize OVN NB IDL. "
                f"OVN_NB_DB={OVN_NB_DB!r}. "
                f"exc_type={type(exc).__name__}. "
                f"exc={exc!r}"
            ),
        ) from exc


app = FastAPI(title="OVN Dev API", version="0.1.0")


@app.get("/api/v1/flows/logical")
def get_logical_flows() -> List[Dict[str, Any]]:
    """Return logical flows from OVN Northbound.

    NOTE: This is a very simple, synchronous implementation for development
    and testing only. It assumes OVN NB DB is reachable at OVN_NB_DB.
    """
    try:
        nb_idl = _get_idl()
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - connection failure
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to connect to OVN NB DB. "
                f"exc_type={type(exc).__name__}. "
                f"exc={exc!r}"
            ),
        ) from exc

    # Run one poll/transaction to populate the IDL.
    start = time.monotonic()
    timeout_s = float(os.getenv("OVN_IDL_SYNC_TIMEOUT_S", "3.0"))
    seqno = nb_idl.change_seqno
    while nb_idl.change_seqno == seqno:
        try:
            nb_idl.run()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"OVN NB IDL run() failed (OVN_NB_DB={OVN_NB_DB!r}): {exc}",
            ) from exc
        if time.monotonic() - start > timeout_s:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Timed out waiting for OVN NB IDL initial sync after {timeout_s}s "
                    f"(OVN_NB_DB={OVN_NB_DB!r}). Check NB DB is reachable from this host "
                    "and that OVN_NB_SCHEMA matches the running OVN version."
                ),
            )

    flows: List[Dict[str, Any]] = []
    for row in nb_idl.tables["Logical_Flow"].rows.values():
        flows.append(
            {
                "uuid": str(row.uuid),
                "logical_datapath": str(getattr(row, "logical_datapath", "")),
                "table_id": getattr(row, "table_id", None),
                "priority": getattr(row, "priority", None),
                "match": getattr(row, "match", ""),
                "actions": getattr(row, "actions", ""),
                "external_ids": dict(getattr(row, "external_ids", {})),
            }
        )

    return flows


@app.get("/api/v1/flows/openflow")
def get_openflow_flows(bridge: str = "br-int") -> Dict[str, Any]:
    """Return OpenFlow flows for the given OVS bridge.

    This uses `ovs-ofctl dump-flows` for now, which is acceptable for a
    development-only API.
    """
    try:
        result = subprocess.run(
            ["ovs-ofctl", "dump-flows", bridge],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to dump flows for bridge {bridge}: {exc.stderr.strip()}",
        ) from exc

    return {
        "bridge": bridge,
        "raw": result.stdout,
    }

