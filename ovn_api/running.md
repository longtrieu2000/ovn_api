export SCHEDULED_TRACE_METRICS_ENABLED=true
export OVN_COMMAND_TRANSPORT=docker-exec          # nếu OVN chạy trong container như trong running.md
export OVN_NB_CONTAINER=ovn_nb_db
export OVN_SB_CONTAINER=ovn_sb_db
export OVS_VSWITCHD_CONTAINER=openvswitch_vswitchd
# OVN API Running Guide

Tai lieu nay huong dan chay OVN API service va goi cac API canary trace de lay latency cho:

- `logical_flow`
- `logical_router`
- `logical_switch`

## 1. Cai dependencies

Tu workspace root:

```bash
cd /home/longth1/workspace/openstack
pip install -r /home/longth1/workspace/openstack/ovn_api/requirements.txt
```

## 2. Chon trace store

### Cach 1: Dung SQLite mac dinh

Khong can them cau hinh gi, service se mac dinh dung:

```env
TRACE_STORE_URL=sqlite:///./ovn_api/data/canary_traces.db
```

### Cach 2: Dung PostgreSQL

Xem huong dan day du o:

```text
/home/longth1/workspace/openstack/ovn_api/docs/postgresql-trace-store.md
```

Quick start PostgreSQL:

```bash
docker compose -f /home/longth1/workspace/openstack/ovn_api/docker-compose.postgres.yml up -d

export TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
export TRACE_STORE_MAX_RUNS=500
```

## 3. Cau hinh OVN command transport

Service canary trace dung `ovn-nbctl`, `ovs-ofctl`, `ovs-appctl` de tao canary resource va do realization.

### Neu OVN chay trong container

```bash
export OVN_COMMAND_TRANSPORT=docker-exec
export OVN_NB_CONTAINER=ovn_nb_db
export OVN_SB_CONTAINER=ovn_sb_db
export OVS_VSWITCHD_CONTAINER=openvswitch_vswitchd
```

### Neu OVN chay local tren host

```bash
export OVN_COMMAND_TRANSPORT=local
```

Neu can, set them binary path:

```bash
export OVN_NBCTL_BIN=ovn-nbctl
export OVS_OFCTL_BIN=ovs-ofctl
export OVS_APPCTL_BIN=ovs-appctl
```

Neu bat live monitoring/exporter, co the tinh chinh them:

```bash
export LIVE_MONITORING_INTERVAL_S=5
export LIVE_MONITORING_LATENCY_INTERVAL_S=15
export LIVE_MONITORING_WS_QUEUE_SIZE=32
export SCHEDULED_TRACE_METRICS_ENABLED=true
export SCHEDULED_TRACE_METRICS_INTERVAL_S=60
export SCHEDULED_TRACE_METRICS_TIMEOUT_S=15
export SCHEDULED_TRACE_METRICS_POLL_INTERVAL_MS=250
export SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE=br-int
# Neu muon co dinh target cho logical_flow:
# export SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME=neutron-<logical-switch-name>
# Neu muon dung danh sach profile tu file:
# export SCHEDULED_TRACE_METRICS_PROFILES_FILE=/home/longth1/workspace/openstack/ovn_api/examples/scheduled-trace-profiles.json
```

Luu y:

- `SCHEDULED_TRACE_METRICS_ENABLED=true` can phai co trong env cua process truoc khi app start
- neu app da chay roi, chi `export` trong shell hien tai se khong tu dong bat worker ben trong uvicorn
- trong van hanh that, nen cap env nay tu `systemd`, `docker compose`, hoac shell start app

## 4. Chay app

Tu workspace root:

```bash
cd /home/longth1/workspace/openstack

python3 -m uvicorn ovn_api.app.main:app \
  --host 0.0.0.0 \
  --port 8001 \
  --reload
```

Neu service da len, kiem tra nhanh:

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/capabilities | jq '.sync_endpoint, .store_scope'
```

## 5. Live monitoring va Prometheus

### 5.1. Snapshot cache hien tai

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/live | jq
```

Endpoint nay tra ve snapshot cache tong hop:

- `capacity`
- `datapath`
- `latency`
- `trace_runtime`
- `api_runtime`
- `errors`

Luu y:

- endpoint nay doc tu background collector cache
- khong do lai OVN DB moi lan client goi
- phu hop cho dashboard/API polling nhe

### 5.2. Prometheus exporter

Scrape endpoint:

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/prometheus
```

Metric chinh dang duoc export:

- `ovn_api_exporter_up`
- `ovn_api_capacity_*`
- `ovn_api_datapath_*`
- `ovn_api_ovsdb_*`
- `ovn_api_bfd_*`
- `ovn_api_trace_*`
- `ovn_api_http_*`
- `ovn_api_websocket_*`

Vi du scrape config:

```yaml
scrape_configs:
  - job_name: ovn_api
    scrape_interval: 15s
    metrics_path: /api/v1/monitoring/prometheus
    static_configs:
      - targets: ['127.0.0.1:8001']
```

### 5.2.1. Debug scheduled trace metrics

Xem JSON snapshot cua active scheduled trace metrics:

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/trace-metrics | jq
```

Endpoint nay cho thay:

- profile nao dang bat
- `target_name` da auto-fill thanh gia tri nao
- lan probe gan nhat `success/timeout/failed`
- phase nao dang timeout

Reload lai danh sach profile tu source hien tai ma khong can restart app:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/monitoring/trace-metrics/reload | jq
```

Neu worker dang dung source la file JSON, lenh tren se re-doc file va restart background scheduler nhe.

Neu ban can clear cache settings va doc lai env cua process:

```bash
curl -s -X POST 'http://127.0.0.1:8001/api/v1/monitoring/trace-metrics/reload?reload_settings=true' | jq
```

Luu y:

- de no-restart thuc su, nen dung `SCHEDULED_TRACE_METRICS_PROFILES_FILE`
- `export` env moi trong shell khong lam process uvicorn dang chay nhan env moi
- vi vay `reload_settings=true` khong thay the duoc file-based reload trong van hanh 24/24

### 5.2.2. Import Grafana dashboard mau

File JSON mau:

```text
/home/longth1/workspace/openstack/ovn_api/grafana/ovn-api-scheduled-trace-dashboard.json
```

Dashboard nay co:

- phase duration chart
- phase state timeline
- last run status
- last run age
- run outcomes
- profile info

Dashboard drill-down rieng cho `logical_flow`:

```text
/home/longth1/workspace/openstack/ovn_api/grafana/ovn-api-logical-flow-drilldown-dashboard.json
```

Dashboard nay phu hop khi ban muon:

- xem `logical_flow` dang cham o `NB`, `SB`, hay `OpenFlow`
- doi chieu `nb_to_sb` va `sb_to_openflow`
- canh bao som khi `ACL`/`logical_flow` lam tang `Logical_Flow` va backlog datapath

### 5.3. WebSocket push-based live stream

WebSocket endpoint:

```text
ws://127.0.0.1:8001/api/v1/ws/monitoring/live
```

Su kien dang push:

- `snapshot`
- `trace_run`
- `heartbeat`

Neu co `websocat`:

```bash
websocat ws://127.0.0.1:8001/api/v1/ws/monitoring/live
```

Neu muon khong gui snapshot ngay khi connect:

```bash
websocat 'ws://127.0.0.1:8001/api/v1/ws/monitoring/live?send_initial=false'
```

## 6. API capability

Xem mapping resource:

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/capabilities | jq
```

Xem rieng `logical_flow`:

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/capabilities | jq '
  .resources[] | select(.requested_resource_type=="logical_flow")'
```

Luu y:

- `logical_flow` la alias cua probe `acl`
- khong co `target_name` thi thong thuong chi do toi `NB -> SB`
- muon co `sb_to_openflow_latency_ms` thi nen truyen `target_name` cua mot `Logical_Switch` that dang realize tren local `br-int`

## 7. POST API lay latency

Endpoint sync:

```text
POST /api/v1/traces/canary
```

Field latency quan trong trong response:

- `command_latency_ms`
- `nb_committed.latency_ms`
- `sb_realized.latency_ms`
- `openflow_realized.latency_ms`
- `nb_to_sb_latency_ms`
- `sb_to_openflow_latency_ms`
- `total_latency_ms`

### 7.1. Latency cho logical switch

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_switch",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq
```

Command chi in ra latency chinh:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_switch",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq '{
    probe_id,
    status,
    command_latency_ms,
    nb_committed: .nb_committed.latency_ms,
    sb_realized: .sb_realized.latency_ms,
    nb_to_sb_latency_ms,
    total_latency_ms
  }'
```

Luu y:

- `logical_switch` hien tai khong do `OpenFlow` 1:1 on dinh
- vi vay `openflow_realized` thuong la `skipped`
- neu `sb_realized` timeout thi `nb_to_sb_latency_ms` va `total_latency_ms` se la `null`

### 7.2. Latency cho logical router

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_router",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq
```

Command chi in latency chinh:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_router",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq '{
    probe_id,
    status,
    command_latency_ms,
    nb_committed: .nb_committed.latency_ms,
    sb_realized: .sb_realized.latency_ms,
    nb_to_sb_latency_ms,
    total_latency_ms
  }'
```

Luu y:

- `logical_router` cung chu yeu la `NB -> SB`
- `openflow_realized` thuong la `skipped`

### 7.3. Latency cho logical flow

`logical_flow` khong duoc tao truc tiep trong NB. Probe se tao `ACL canary` de ep OVN sinh `Logical_Flow` trong SB.

#### Cach co ban: do `NB -> SB`

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_flow",
    "bridge": "br-int",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq
```

Command chi in latency chinh:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_flow",
    "bridge": "br-int",
    "timeout_s": 15,
    "poll_interval_ms": 250
  }' | jq '{
    probe_id,
    status,
    resolved_resource_type,
    command_latency_ms,
    nb_committed: .nb_committed.latency_ms,
    sb_realized: .sb_realized.latency_ms,
    nb_to_sb_latency_ms,
    sb_to_openflow_latency_ms,
    total_latency_ms,
    note
  }'
```

Trong mode nay:

- `resolved_resource_type` se la `acl`
- `sb_realized` la luc thay `Logical_Flow` trong OVN SB
- `sb_to_openflow_latency_ms` thuong la `null` vi `openflow_expected=false`

#### Cach day du: do toi OpenFlow

Ban can mot `Logical_Switch` that dang realize tren local `br-int`.

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_flow",
    "target_name": "neutron-<logical-switch-name>",
    "bridge": "br-int",
    "timeout_s": 15,
    "poll_interval_ms": 250,
    "expect_openflow": true
  }' | jq
```

Command chi in latency chinh:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_flow",
    "target_name": "neutron-<logical-switch-name>",
    "bridge": "br-int",
    "timeout_s": 15,
    "poll_interval_ms": 250,
    "expect_openflow": true
  }' | jq '{
    probe_id,
    status,
    command_latency_ms,
    nb_committed: .nb_committed.latency_ms,
    sb_realized: .sb_realized.latency_ms,
    openflow_realized: .openflow_realized.latency_ms,
    nb_to_sb_latency_ms,
    sb_to_openflow_latency_ms,
    total_latency_ms
  }'
```

Neu `sb_to_openflow_latency_ms` van la `null`, thuong la do:

- switch target khong nam tren local chassis
- `br-int` khong phai bridge chua datapath do
- OpenFlow cho datapath nay chua duoc realize trong khoang timeout

## 8. API async

Neu khong muon HTTP request block den luc trace xong:

### Submit job

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_switch",
    "timeout_s": 15
  }' | jq
```

### List lich su

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/canary/runs | jq
```

### Lay chi tiet mot run

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/canary/runs/<probe_id> | jq
```

## 9. Loi thuong gap

### `Method Not Allowed`

`/api/v1/traces/canary` la `POST`, khong phai `GET`.

Dung:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{"resource_type":"logical_switch"}' | jq
```

### `connection refused`

Kiem tra:

- app da chay o `127.0.0.1:8001` chua
- PostgreSQL neu co da start chua
- OVN NB/SB DB co reachable chua

### Prometheus scrape timeout

Kiem tra:

- scrape path co dung `/api/v1/monitoring/prometheus` khong
- `LIVE_MONITORING_INTERVAL_S` co dang dat qua thap khong
- exporter co dang bi tre vi OVN DB loi hay khong, xem `ovn_api_monitoring_component_up`

### WebSocket khong nhan du lieu

Kiem tra:

- endpoint co dung `ws://127.0.0.1:8001/api/v1/ws/monitoring/live` khong
- reverse proxy co support WebSocket upgrade khong
- `ovn_api_websocket_clients` va `ovn_api_websocket_messages_sent_total` tren Prometheus co tang khong

### `openflow_realized.status = skipped`

Day la hanh vi dung trong cac truong hop:

- `resource_type` la `logical_switch` hoac `logical_router`
- `logical_flow` khong co `target_name`
- request khong bat `expect_openflow`
