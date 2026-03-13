# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repository Layout

This workspace contains three components:
- `ovn_api/` — the primary Python FastAPI service (main development target)
- `ovs/` — local Open vSwitch source tree (C); its Python bindings in `ovs/python/` are bootstrapped at runtime by `ovn_api/app/__init__.py`
- `ovn/` — OVN source tree (C); referenced for schema files and tooling

## Install Dependencies

All commands run from the **workspace root** (`/home/longth1/workspace/openstack`):

```bash
pip install -r ovn_api/requirements.txt
```

## Run the API

```bash
python3 -m uvicorn ovn_api.app.main:app --host 0.0.0.0 --port 8001 --reload
```

The app **must** be launched from the workspace root. `app/__init__.py` resolves `ovs/python/` as `parents[2]` relative to `app/`, and the default SQLite path (`sqlite:///./ovn_api/data/canary_traces.db`) is also relative to the working directory.

Quick health check after startup:

```bash
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8001/api/v1/traces/capabilities | jq '.sync_endpoint, .store_scope'
```

## No Test Suite

There are currently no automated tests in `ovn_api/`.

## Key Environment Variables

All configuration is read via environment variables (no config files). Defaults come from `ovn_api/app/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `OVN_NB_DB` | `tcp:127.0.0.1:6641` | OVN Northbound OVSDB address |
| `OVN_SB_DB` | `tcp:127.0.0.1:6642` | OVN Southbound OVSDB address |
| `OVN_COMMAND_TRANSPORT` | `docker-exec` | `local` or `docker-exec` |
| `OVN_NB_CONTAINER` | `ovn_nb_db` | Container name for docker-exec NB commands |
| `OVN_SB_CONTAINER` | `ovn_sb_db` | Container name for docker-exec SB commands |
| `OVS_VSWITCHD_CONTAINER` | `openvswitch_vswitchd` | Container name for ovs-ofctl commands |
| `TRACE_STORE_URL` | `sqlite:///./ovn_api/data/canary_traces.db` | SQLite or PostgreSQL URL |
| `TRACE_STORE_MAX_RUNS` | `500` | Max persisted canary runs |
| `SCHEDULED_TRACE_METRICS_ENABLED` | `false` | Enable periodic canary probes for Prometheus |
| `LIVE_MONITORING_INTERVAL_S` | `5.0` | Background metrics refresh interval |

For OVN running locally instead of containers:

```bash
export OVN_COMMAND_TRANSPORT=local
```

## Architecture

### Layer Model

```
HTTP request → router → service → core → OVN/OVS → model → JSON response
```

- **`app/routers/`** — Thin HTTP handlers; no business logic. Each router maps directly to one service.
- **`app/services/`** — All business logic: reading/filtering OVN data, running canary probes, collecting metrics.
- **`app/core/`** — External system clients:
  - `ovsdb.py`: Generic `OvsdbIdlClient` — connects to NB or SB via OVSDB IDL. Fetches schema via RPC (`get_schema`) if the schema file is absent locally.
  - `ovn_nb.py` / `ovn_sb.py`: Singleton wrappers returning `OvsdbIdlClient` instances for NB and SB.
  - `ovn_nbctl.py`: Wraps `ovn-nbctl` CLI for write operations (canary resource creation/deletion).
  - `ovs.py`: Wraps `ovs-ofctl dump-flows` for OpenFlow data.
  - `command.py`: `CommandExecutor` — dispatches to `subprocess` directly (`local`) or via `docker exec` (`docker-exec`).
- **`app/models/`** — Pydantic output models only; no input validation logic.
- **`app/config.py`** — Single frozen `Settings` dataclass populated from `os.getenv`, cached via `@lru_cache`.

### Singletons

Core clients and services are process-level singletons via `@lru_cache(maxsize=1)` (e.g. `get_ovn_nb_client()`, `get_canary_trace_manager()`). The `Settings` object is also cached this way. This means env vars are read once at first access; changing env after startup has no effect unless you use the reload endpoint.

### Background Services (started in `app/main.py` lifespan)

Three daemon threads start when the app starts:

1. **`DatapathMetricsCollector`** — Periodically runs `ovs-appctl dpctl/show` and caches the parsed result in memory. The `/api/v1/metrics/datapath` endpoint reads from this cache rather than invoking the command per-request.

2. **`CanaryTraceManager`** — Single background worker thread processing async canary probe jobs. Jobs are persisted in the SQL trace store as `queued → running → success/failed/timeout`. On restart, any `queued`/`running` rows are immediately marked `failed`.

3. **`LiveMonitoringService`** — Refreshes a composite metrics snapshot (capacity, datapath, latency) on a configurable interval. Publishes `snapshot` and `trace_run` events to all active WebSocket subscribers via a fan-out queue.

### Canary Trace Pipeline

`POST /api/v1/traces/canary` (sync) or `POST /api/v1/traces/canary/runs` (async):

1. `CanaryTraceService.prepare_probe()` resolves resource type aliases (e.g. `logical_flow → acl`, `network → logical_switch`) and builds the `ovn-nbctl` create/cleanup commands.
2. The probe creates a canary resource in OVN NB via `ovn-nbctl`.
3. It polls NB IDL → SB IDL → OpenFlow in sequence, recording latency timestamps for each stage (`nb_committed`, `sb_realized`, `openflow_realized`).
4. Cleanup commands remove the canary resource regardless of success/failure.
5. Result is persisted in the SQL trace store (`SqlCanaryTraceStore` backed by SQLAlchemy). Schema is auto-created on startup — no manual migrations are needed.

### OVN NB vs SB

- **NB (Northbound)**: Intent — what the user/operator configured (Logical_Switch, Logical_Router, ACL, NAT, Load_Balancer).
- **SB (Southbound)**: Realized state — what northd compiled (Logical_Flow, Chassis, Port_Binding, BFD, Datapath_Binding).

### Trace Store

Default: SQLite at `ovn_api/data/canary_traces.db` (created automatically).

PostgreSQL alternative (see `ovn_api/docs/postgresql-trace-store.md`):

```bash
docker compose -f ovn_api/docker-compose.postgres.yml up -d
export TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
```

### Prometheus / Monitoring Endpoints

- `GET /api/v1/monitoring/live` — JSON snapshot (reads from cache, no live OVN query).
- `GET /api/v1/monitoring/prometheus` — Prometheus text exposition.
- `WS /api/v1/ws/monitoring/live` — Push stream; events: `snapshot`, `trace_run`, `heartbeat`.
- `POST /api/v1/monitoring/trace-metrics/reload` — Reload scheduled trace profiles without restart.

## Adding New Endpoints

Follow the existing pattern:
1. Add a new router in `app/routers/`.
2. Add business logic in `app/services/`.
3. Add output schema in `app/models/` if needed.
4. If a new external data source is required, add a client in `app/core/`.
5. Register the router in `app/main.py` with `app.include_router(...)`.
