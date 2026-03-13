# Scope ovn_api

# ovn_api Scope

`ovn_api` là một **FastAPI REST service** đứng trước hệ thống **OVN/OVS**, cung cấp khả năng:

- Đọc trạng thái mạng
- Đo latency thực tế của pipeline OVN
- Export metrics cho **Prometheus / Grafana**

Service **không quản lý cấu hình mạng**, chỉ dùng để **đọc và đo (observe)**.

---

# Các tính năng chính

## 1. Topology Viewer

Xem thông tin các resource trong OVN:

- Logical Switch
- Logical Router
- Port
- ACL
- NAT
- Static route

---

## 2. Logical Flow Viewer

Đọc dữ liệu từ **OVN Southbound DB**

Chức năng:

- Xem toàn bộ `Logical_Flow`
- Filter theo origin (ACL / NAT)
- Phân loại:

```
exact
stage_generic
```

- Thống kê tổng số flow

---

## 3. OpenFlow Dump

Đọc **OpenFlow flows từ OVS**

Thông qua:

```
ovs-ofctl dump-flows
```

Bridge mặc định:

```
br-int
```

---

## 4. Chassis Viewer

Đọc dữ liệu từ **OVN Southbound DB**

Hiển thị:

- danh sách chassis (hypervisor)
- hostname
- encapsulation IP
- port binding

---

## 5. Metrics

### Capacity Metrics

Đếm số lượng object:

```
Logical Switch
Logical Router
Port
ACL
NAT
Load Balancer
Logical Flow
```

---

### Datapath Metrics

Lấy từ:

```
ovs-appctl dpctl/show
```

Bao gồm:

- flow count
- lookup hit
- miss
- lost
- cache hit rate

Lưu ý:

- metrics được **cache từ background thread**
- **không query trực tiếp mỗi request**

---

### Latency Metrics

Bao gồm:

- OVSDB transaction latency (NB + SB)
- IDL sync latency
- BFD session stats

---

# 6. Canary Trace (Tính năng cốt lõi)

Tạo **resource tạm thời trong OVN Northbound** để đo pipeline realization.

Mục tiêu:

```
NB → SB → OpenFlow
```

Các phase được đo:

```
NB committed
SB realized
OpenFlow realized
```

Mục đích:

Giúp xác định **phase nào trong pipeline OVN bị chậm hoặc lỗi**.

Ví dụ sự cố:

```
ACL được tạo
→ SB DB bị treo
→ flow không sinh
```

Canary giúp xác định:

```
NB ok
SB fail
```

---

# Resource type hỗ trợ

| Requested | Resolves to | Ghi chú |
| --- | --- | --- |
| acl | acl | tạo ACL trên Logical Switch |
| logical_flow | acl | alias tạo ACL để sinh Logical Flow |
| nat / nat_rule | nat | tạo NAT rule trên Logical Router |
| logical_switch / network | logical_switch | tạo Logical Switch |
| logical_router | logical_router | tạo Logical Router |
| logical_switch_port / logical_port | logical_switch_port | tạo LSP |
| logical_router_port / subnet | logical_router_port | tạo LRP với CIDR |

---

# Scheduled Trace Metrics

Canary probe có thể chạy **định kỳ**.

Config từ:

- environment variables
- JSON file

Kết quả:

```
export Prometheus metrics
```

Dùng để theo dõi latency theo thời gian.

---

# Live Monitoring & Prometheus Export

Snapshot tổng hợp:

```
capacity
datapath
latency
trace runtime
```

Snapshot được refresh định kỳ bằng **background thread**.

Các phương thức export:

- Prometheus text format
- WebSocket push stream

WebSocket event:

```
snapshot
trace_run
heartbeat
```

---

# API Metrics (middleware)

Middleware tự động đo:

- request count
- in-flight request
- error count
- duration
- websocket connection count

Metrics được expose qua:

```
Prometheus endpoint
```

---

# Danh sách API

---

# Health API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/health` | Trả config đang chạy |

---

# Topology API

## Switch

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/switches` | danh sách logical switch |
| GET | `/api/v1/switches/{switch_ref}` | chi tiết switch |

---

## Router

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/routers` | danh sách router |
| GET | `/api/v1/routers/{router_ref}` | chi tiết router |

---

# Flow API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/flows/logical` | danh sách Logical Flow |
| GET | `/api/v1/flows/logical/summary` | thống kê flow |
| GET | `/api/v1/flows/openflow` | OpenFlow dump |

Query:

```
?table=<id>
?origin=acl
?bridge=br-int
```

---

# Chassis API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/chassis` | danh sách chassis |
| GET | `/api/v1/chassis/{chassis_ref}/bindings` | port binding của chassis |

---

# Metrics API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/metrics/capacity` | số lượng object |
| GET | `/api/v1/metrics/datapath` | datapath stats |
| GET | `/api/v1/metrics/latency` | latency metrics |

---

# Canary Trace API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/traces/capabilities` | danh sách resource type |
| POST | `/api/v1/traces/canary` | chạy probe sync |
| POST | `/api/v1/traces/canary/runs` | submit async probe |
| GET | `/api/v1/traces/canary/runs` | lịch sử run |
| GET | `/api/v1/traces/canary/runs/{probe_id}` | chi tiết run |

---

# Monitoring API

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/api/v1/monitoring/live` | snapshot monitoring |
| GET | `/api/v1/monitoring/prometheus` | prometheus metrics |
| GET | `/api/v1/monitoring/trace-metrics` | trạng thái scheduled trace |
| POST | `/api/v1/monitoring/trace-metrics/reload` | reload profile |
| WS | `/api/v1/ws/monitoring/live` | WebSocket monitoring |

---

# Canary Trace Latency Fields

| Field | Ý nghĩa |
| --- | --- |
| command_latency_ms | thời gian chạy ovn-nbctl |
| nb_committed.latency_ms | resource xuất hiện trong NB |
| sb_realized.latency_ms | trạng thái xuất hiện trong SB |
| openflow_realized.latency_ms | flow xuất hiện trên bridge |
| nb_to_sb_latency_ms | latency NB → SB |
| sb_to_openflow_latency_ms | latency SB → OpenFlow |
| total_latency_ms | tổng latency pipeline |

---

# Planning / Roadmap

Các mục dự kiến triển khai:

- test trên staging
- bổ sung thông số monitoring
- authentication / authorization
- schema migration (SQLAlchemy)
- tối ưu openflow realization metrics
- containerization production

---

# Giới hạn hiện tại

`ovn_api` **không hỗ trợ write API**.

Không có endpoint để:

```
create network
delete router
modify ACL
```

Chỉ dùng cho:

```
read
observe
measure
```