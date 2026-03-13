# OVN API Prometheus Scrape Guide

Tai lieu nay huong dan:

- scrape Prometheus exporter cua OVN API
- metric nao dang duoc export
- moi metric duoc do tu dau
- tac dong hieu nang va cach tuning de chay 24/24

## 1. Exporter endpoint

Prometheus scrape endpoint:

```text
GET /api/v1/monitoring/prometheus
```

Vi du:

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/prometheus
```

Media type:

```text
text/plain; version=0.0.4; charset=utf-8
```

## 2. Kien truc scrape

Exporter nay duoc thiet ke theo huong `cache-first`:

1. Background collector refresh snapshot theo interval.
2. Prometheus scrape doc lai snapshot cache do.
3. Scrape khong tu goi truc tiep xuong OVN DB moi lan.

Muc tieu:

- giam load len OVN NB/SB DB
- giam so lan goi `ovs-appctl`
- tranh pattern "nhieu Prometheus server / nhieu scrape target => nhieu poll truc tiep"

## 3. Bien moi truong tuning

```env
LIVE_MONITORING_INTERVAL_S=5
LIVE_MONITORING_LATENCY_INTERVAL_S=15
LIVE_MONITORING_WS_QUEUE_SIZE=32
DATAPATH_METRICS_INTERVAL_S=5
SCHEDULED_TRACE_METRICS_ENABLED=false
SCHEDULED_TRACE_METRICS_INTERVAL_S=60
SCHEDULED_TRACE_METRICS_TIMEOUT_S=15
SCHEDULED_TRACE_METRICS_POLL_INTERVAL_MS=250
SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE=br-int
SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME=
SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_ROUTER_TARGET_NAME=
SCHEDULED_TRACE_METRICS_PROFILES_JSON=
SCHEDULED_TRACE_METRICS_PROFILES_FILE=
```

Y nghia:

- `LIVE_MONITORING_INTERVAL_S`
  refresh snapshot chung cho capacity, runtime status, trace queue state
- `LIVE_MONITORING_LATENCY_INTERVAL_S`
  refresh nhom latency cham hon, vi nhom nay co them OVSDB RPC select latency
- `DATAPATH_METRICS_INTERVAL_S`
  refresh collector rieng cho `ovs-appctl dpctl/show`
- `LIVE_MONITORING_WS_QUEUE_SIZE`
  queue fan-out cho tung WebSocket subscriber, khong anh huong scrape Prometheus
- `SCHEDULED_TRACE_METRICS_ENABLED`
  bat active scheduled trace metrics cho Grafana / Prometheus
- `SCHEDULED_TRACE_METRICS_INTERVAL_S`
  chu ky chay lai probe cho tung profile mac dinh
- `SCHEDULED_TRACE_METRICS_TIMEOUT_S`
  timeout cua moi canary probe
- `SCHEDULED_TRACE_METRICS_POLL_INTERVAL_MS`
  poll interval trong tung canary probe
- `SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE`
  bridge mac dinh, nen de `br-int`
- `SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME`
  target switch uu tien cho profile `logical_flow`; neu bo trong, service se auto-chon
- `SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_ROUTER_TARGET_NAME`
  target router uu tien cho cac profile router-target trong tuong lai; neu bo trong, service se auto-chon
- `SCHEDULED_TRACE_METRICS_PROFILES_JSON`
  JSON inline cho danh sach profile; phu hop khi profile ngan
- `SCHEDULED_TRACE_METRICS_PROFILES_FILE`
  duong dan toi file JSON chua danh sach profile; phu hop cho production

Khuyen nghi van hanh:

- `LIVE_MONITORING_INTERVAL_S=5` hoac `10`
- `LIVE_MONITORING_LATENCY_INTERVAL_S=15` hoac `30`
- Prometheus `scrape_interval=15s`
- bat `SCHEDULED_TRACE_METRICS_ENABLED=true` chi khi ban that su can chart phase latency
- neu co ca `SCHEDULED_TRACE_METRICS_PROFILES_FILE` va `SCHEDULED_TRACE_METRICS_PROFILES_JSON`, file se duoc uu tien

## 4. Prometheus config mau

```yaml
scrape_configs:
  - job_name: ovn_api
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /api/v1/monitoring/prometheus
    static_configs:
      - targets:
          - 127.0.0.1:8001
```

Neu co reverse proxy / ingress:

- dam bao route `GET /api/v1/monitoring/prometheus` duoc expose
- khong cache response cua exporter

## 5. Metric groups

### 5.1. Exporter va collector health

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_exporter_up` | Exporter endpoint dang tra du lieu | hardcoded = `1` neu endpoint render duoc |
| `ovn_api_uptime_seconds` | Uptime process API | tinh tu process start |
| `ovn_api_monitoring_snapshot_ready` | Snapshot cache da san sang chua | `LiveMonitoringService` |
| `ovn_api_monitoring_sequence` | So thu tu snapshot moi nhat | tang moi lan collector refresh |
| `ovn_api_monitoring_component_up{component=...}` | Trang thai `capacity/datapath/latency` | dua tren cache component |
| `ovn_api_monitoring_component_age_seconds{component=...}` | Do tuoi cua cache component | `generated_at - updated_at` |

`component_up=0` thuong nghia la component do khong refresh duoc, nhung exporter van song.

### 5.2. Capacity metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_capacity_logical_flows` | Tong `Logical_Flow` | dem row SB table `Logical_Flow` |
| `ovn_api_capacity_logical_switches` | Tong `Logical_Switch` | dem row NB table `Logical_Switch` |
| `ovn_api_capacity_logical_switch_ports` | Tong `Logical_Switch_Port` | dem row NB table `Logical_Switch_Port` |
| `ovn_api_capacity_logical_routers` | Tong `Logical_Router` | dem row NB table `Logical_Router` |
| `ovn_api_capacity_logical_router_ports` | Tong `Logical_Router_Port` | dem row NB table `Logical_Router_Port` |
| `ovn_api_capacity_acls` | Tong `ACL` | dem row NB table `ACL` |
| `ovn_api_capacity_nats` | Tong `NAT` | dem row NB table `NAT` |
| `ovn_api_capacity_load_balancers` | Tong `Load_Balancer` | dem row NB table `Load_Balancer` |

Measurement mode:

- doc qua OVN NB/SB IDL cache
- moi vong refresh snapshot se dem lai row count

Chi phi:

- nhe
- phu hop scrape lien tuc

### 5.3. Datapath metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_datapath_flows` | So flow trong datapath | parse `ovs-appctl dpctl/show` |
| `ovn_api_datapath_lookups_total{result="hit"}` | Tong lookup hit | parse `lookups:` |
| `ovn_api_datapath_lookups_total{result="missed"}` | Tong lookup miss | parse `lookups:` |
| `ovn_api_datapath_lookups_total{result="lost"}` | Tong lookup lost | parse `lookups:` |
| `ovn_api_datapath_cache_hit_rate_percent` | Cache hit rate % | suy ra tu `cache: hit` / tong packet |
| `ovn_api_datapath_mask_hit_per_pkt` | Mask hits per packet | suy ra tu `masks: hit` / tong packet |

Measurement mode:

- collector rieng `DatapathMetricsCollector`
- goi `ovs-appctl dpctl/show`
- parse output text thanh metric

Chi phi:

- trung binh
- van nhe neu de `DATAPATH_METRICS_INTERVAL_S` tu `5s` tro len

### 5.4. OVSDB latency metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_ovsdb_transaction_latency_ms{db="nb"}` | Latency transact select toi NB DB | OVSDB JSON-RPC `transact select` tren `NB_Global` |
| `ovn_api_ovsdb_transaction_latency_ms{db="sb"}` | Latency transact select toi SB DB | OVSDB JSON-RPC `transact select` tren `SB_Global` |
| `ovn_api_ovsdb_idl_sync_latency_ms{db="nb"}` | Thoi gian `get_idl()` sync NB | do quanh `nb_client.get_idl()` |
| `ovn_api_ovsdb_idl_sync_latency_ms{db="sb"}` | Thoi gian `get_idl()` sync SB | do quanh `sb_client.get_idl()` |

Measurement mode:

- duoc refresh theo `LIVE_MONITORING_LATENCY_INTERVAL_S`
- khong do moi lan Prometheus scrape

Chi phi:

- cao hon capacity metrics
- van chap nhan duoc neu de interval hop ly (`15s` hoac `30s`)

### 5.5. BFD metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_bfd_sessions{status="total"}` | Tong so BFD session | dem row SB table `BFD` |
| `ovn_api_bfd_sessions{status="up"}` | So BFD session `up` | dem theo `status` |
| `ovn_api_bfd_sessions{status="down"}` | So BFD session `down` | dem theo `status` |
| `ovn_api_bfd_sessions{status="admin_down"}` | So BFD session `admin_down` | dem theo `status` |
| `ovn_api_bfd_sessions{status="init"}` | So BFD session `init` | dem theo `status` |
| `ovn_api_bfd_min_tx_ms{aggregation="min/max"}` | Gia tri min/max `min_tx` | tong hop tu SB table `BFD` |
| `ovn_api_bfd_min_rx_ms{aggregation="min/max"}` | Gia tri min/max `min_rx` | tong hop tu SB table `BFD` |

Measurement mode:

- lay tu SB IDL cache
- duoc refresh cung nhom latency metrics

### 5.6. Trace worker metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_trace_queue_depth` | So trace dang xep hang | `CanaryTraceManager` in-memory queue |
| `ovn_api_trace_worker_up` | Worker thread co dang song khong | `thread.is_alive()` |
| `ovn_api_trace_max_runs` | Gioi han prune history | config `TRACE_STORE_MAX_RUNS` |

Measurement mode:

- lay truc tiep tu runtime memory
- rat nhe

### 5.7. Scheduled active trace metrics

Nhomm nay dung cho Grafana khi ban muon biet:

- `logical_flow` dang treo o `NB`, `SB` hay `OpenFlow`
- `logical_switch` dang timeout o phase nao
- `logical_router` dang timeout o phase nao

Mac dinh feature nay `tat`, vi no la active probe.

Khi bat:

```env
SCHEDULED_TRACE_METRICS_ENABLED=true
SCHEDULED_TRACE_METRICS_INTERVAL_S=60
SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE=br-int
```

Profile mac dinh hien tai:

- `logical_flow_default`
- `logical_switch_default`
- `logical_router_default`

Neu muon tu cau hinh profile, co 2 cach:

### Cach 1: file JSON

```bash
export SCHEDULED_TRACE_METRICS_PROFILES_FILE=/home/longth1/workspace/openstack/ovn_api/examples/scheduled-trace-profiles.json
```

File mau da co san:

```text
/home/longth1/workspace/openstack/ovn_api/examples/scheduled-trace-profiles.json
```

Format:

```json
{
  "profiles": [
    {
      "name": "logical_flow_prod",
      "resource_type": "logical_flow",
      "target_name": "neutron-<logical-switch-name>",
      "bridge": "br-int",
      "interval_s": 60,
      "timeout_s": 15,
      "poll_interval_ms": 250,
      "enabled": true
    }
  ]
}
```

Neu file cung cap:

```json
{
  "profiles": []
}
```

thi service se khong chay scheduled trace profile nao.

Sau khi sua file profile, khong can restart app. Reload bang:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/monitoring/trace-metrics/reload | jq
```

Day la cach nen dung cho moi truong `24/24`, vi process co the re-doc file ma khong can spawn lai worker service.

### Cach 2: JSON inline trong env

```bash
export SCHEDULED_TRACE_METRICS_PROFILES_JSON='[
  {
    "name": "logical_flow_auto",
    "resource_type": "logical_flow",
    "interval_s": 60
  },
  {
    "name": "logical_switch_default",
    "resource_type": "logical_switch",
    "interval_s": 90
  }
]'
```

Auto target:

- `logical_flow_default`
  neu khong set `SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME`, service se tu chon mot `Logical_Switch`
- `logical_switch_default`
  khong can `target_name`, vi probe nay tu tao canary switch
- `logical_router_default`
  khong can `target_name`, vi probe nay tu tao canary router

Luu y:

- `target_name` chi thuc su co y nghia voi nhom resource can target san co, nhu `logical_flow`, `acl`, `nat`, `logical_port`, `subnet`
- voi `logical_switch` va `logical_router`, probe tu tao canary resource, nen `target_name` se bi bo qua

Bridge:

- mac dinh luon la `br-int`
- co the doi bang `SCHEDULED_TRACE_METRICS_DEFAULT_BRIDGE`, nhung trong OVN thong thuong nen giu `br-int`
- neu profile khong khai bao `bridge`, service se auto-fill `br-int`

Reload endpoint:

- `POST /api/v1/monitoring/trace-metrics/reload`
  reload lai profile tu source hien tai: default, file, hoac env JSON
- `POST /api/v1/monitoring/trace-metrics/reload?reload_settings=true`
  clear cache `get_settings()` roi doc lai env cua process

Luu y van hanh:

- neu ban can no-restart thuc su, hay uu tien `SCHEDULED_TRACE_METRICS_PROFILES_FILE`
- viec `export` lai env trong shell khong tu dong cap nhat env cua process dang chay
- `reload_settings=true` chi huu ich khi process manager da cap nhat env cho process, hoac ban mutate env trong process

Metric duoc export:

| Metric | Y nghia |
| --- | --- |
| `ovn_api_scheduled_trace_metrics_enabled` | Feature active trace metrics co bat khong |
| `ovn_api_scheduled_trace_service_up` | Worker thread co song khong |
| `ovn_api_scheduled_trace_profile_enabled{requested_resource_type,profile}` | Profile co duoc bat khong |
| `ovn_api_scheduled_trace_profile_info{requested_resource_type,profile,bridge,target_name,target_resolution_mode}` | Info profile, bridge, target dang duoc dung |
| `ovn_api_scheduled_trace_last_run_status_code{requested_resource_type,profile}` | Trang thai lan probe gan nhat |
| `ovn_api_scheduled_trace_runs_total{requested_resource_type,profile,result}` | Dem tong so lan probe theo ket qua |
| `ovn_api_scheduled_trace_last_run_timestamp_seconds{requested_resource_type,profile}` | Thoi diem lan probe gan nhat |
| `ovn_api_scheduled_trace_last_success_timestamp_seconds{requested_resource_type,profile}` | Thoi diem lan probe thanh cong gan nhat |
| `ovn_api_scheduled_trace_last_run_age_seconds{requested_resource_type,profile}` | Do tuoi cua lan probe gan nhat |
| `ovn_api_scheduled_trace_phase_duration_ms{requested_resource_type,profile,phase}` | Duration phase gan nhat |
| `ovn_api_scheduled_trace_phase_state_code{requested_resource_type,profile,phase}` | State code cua phase gan nhat |

State code cho phase:

- `0 = observed`
- `1 = timeout`
- `2 = failed`
- `3 = skipped`

Run status code:

- `0 = success`
- `1 = partial_success`
- `2 = timeout`
- `3 = failed`
- `4 = idle`

Phase duoc export:

- `command`
- `nb_committed`
- `sb_realized`
- `openflow_realized`
- `nb_to_sb`
- `sb_to_openflow`
- `total`
- `cleanup` cho `phase_state_code`

Grafana pattern nen dung:

- Time series:
  `ovn_api_scheduled_trace_phase_duration_ms{requested_resource_type="$resource_type"}`
- State timeline:
  `ovn_api_scheduled_trace_phase_state_code{requested_resource_type="$resource_type"}`

Neu `logical_flow` auto-chon sai switch, ban nen set co dinh:

```env
SCHEDULED_TRACE_METRICS_DEFAULT_LOGICAL_SWITCH_TARGET_NAME=neutron-<logical-switch-name>
```

### 5.7.1. Grafana dashboard mau

File dashboard mau:

```text
/home/longth1/workspace/openstack/ovn_api/grafana/ovn-api-scheduled-trace-dashboard.json
```

Import vao Grafana:

1. Dashboards
2. New
3. Import
4. Chon file JSON tren
5. Map datasource Prometheus

Dashboard co san:

- time series cho `phase duration`
- state timeline cho `phase state`
- stat cho `last run status`
- stat cho `last run age`
- outcome panel cho `success/timeout/failed`
- profile info panel de nhin `bridge`, `target_name`, `target_resolution_mode`

Dashboard drill-down rieng cho `logical_flow`:

```text
/home/longth1/workspace/openstack/ovn_api/grafana/ovn-api-logical-flow-drilldown-dashboard.json
```

Dashboard nay tap trung vao:

- `nb_committed`, `sb_realized`, `openflow_realized`
- `nb_to_sb`, `sb_to_openflow`, `total`
- state timeline de thay dang treo o phase nao
- panel tuong quan voi `ovn_api_ovsdb_transaction_latency_ms`
- panel tuong quan voi `ovn_api_capacity_logical_flows` va `ovn_api_datapath_flows`

### 5.8. API HTTP metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_http_requests_total` | Tong HTTP requests xu ly | ASGI middleware counter |
| `ovn_api_http_requests_in_flight` | So request dang xu ly | ASGI middleware gauge |
| `ovn_api_http_request_errors_total` | Tong request loi | request exception hoac status `>=500` |
| `ovn_api_http_request_duration_ms_sum` | Tong thoi gian xu ly request | cong don duration ms |
| `ovn_api_http_request_duration_ms_count` | So request da duoc timing | counter |
| `ovn_api_http_requests_by_method_status_total{method=...,status_class=...}` | Breakdown theo method va `2xx/4xx/5xx` | ASGI middleware counter |

Measurement mode:

- do trong process
- khong can goi OVN
- overhead rat thap

Luu y:

- day khong phai histogram bucket
- neu muon average latency request:

```promql
rate(ovn_api_http_request_duration_ms_sum[5m])
/
rate(ovn_api_http_request_duration_ms_count[5m])
```

### 5.9. WebSocket metrics

| Metric | Y nghia | Do tu dau |
| --- | --- | --- |
| `ovn_api_websocket_clients` | So client WS dang ket noi | counter runtime |
| `ovn_api_websocket_connections_total` | Tong so lan WS connect | counter runtime |
| `ovn_api_websocket_messages_sent_total` | Tong message da push | tang moi lan send JSON event |

Measurement mode:

- do trong process
- khong can poll OVN

## 6. Metric nao KHONG duoc scrape passively

Nhung metric sau khong duoc exporter do thu dong neu chua bat `scheduled active trace metrics`:

- latency create `logical_flow`
- latency create `logical_switch`
- latency create `logical_router`
- `NB -> SB -> OpenFlow` realization latency

Ly do:

- day la active-probe metric
- muon co so lieu dung phai tao canary resource va do theo request lifecycle

Neu khong bat schedule background, cho nhom nay dung:

```text
POST /api/v1/traces/canary
```

Hien tai code da co scheduled collector de dua `last result` cua nhom nay vao Prometheus. Tuy nhien day van la active probe, nen ban phai tu bat feature bang `SCHEDULED_TRACE_METRICS_ENABLED=true`.

## 7. Cach metric duoc do trong code

### Capacity

- `MetricsService.get_capacity_metrics()`
- dem row tren OVN NB/SB IDL

### Datapath

- `DatapathMetricsCollector`
- goi `ovs-appctl dpctl/show`
- parse cac dong `lookups`, `flows`, `masks`, `cache`

### Latency

- `MetricsService.get_latency_metrics()`
- do `get_idl()` sync time
- do OVSDB `transact select` toi `NB_Global` va `SB_Global`
- doc SB table `BFD`

### API runtime

- `ApiMetricsMiddleware` va `ApiMetricsStore`
- dem request trong process

### Trace runtime

- `CanaryTraceManager.get_runtime_metrics()`
- lay queue depth va thread state tu memory

## 8. Khuyen nghi van hanh 24/24

1. Khong de `LIVE_MONITORING_LATENCY_INTERVAL_S` qua thap.
2. Neu moi truong lon, uu tien `15s` hoac `30s` cho latency refresh.
3. De Prometheus scrape `15s` la hop ly cho exporter nay.
4. Theo doi:
   - `ovn_api_monitoring_component_up`
   - `ovn_api_monitoring_component_age_seconds`
   - `ovn_api_http_request_errors_total`
   - `ovn_api_trace_worker_up`
5. Neu `component_up=0` nhung exporter van `up=1`, nghia la app van song nhung datasource ben duoi dang loi.

## 9. PromQL mau

Ty le request loi 5xx:

```promql
sum(rate(ovn_api_http_requests_by_method_status_total{status_class="5xx"}[5m]))
/
sum(rate(ovn_api_http_requests_total[5m]))
```

Average HTTP latency:

```promql
rate(ovn_api_http_request_duration_ms_sum[5m])
/
rate(ovn_api_http_request_duration_ms_count[5m])
```

NB transaction latency:

```promql
ovn_api_ovsdb_transaction_latency_ms{db="nb"}
```

So logical flow hien tai:

```promql
ovn_api_capacity_logical_flows
```

So WebSocket client dang theo doi live stream:

```promql
ovn_api_websocket_clients
```

## 10. Kiem tra nhanh

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/prometheus | grep '^ovn_api_' | head -50
```

Kiem tra snapshot JSON cung nguon cache:

```bash
curl -s http://127.0.0.1:8001/api/v1/monitoring/live | jq
```
