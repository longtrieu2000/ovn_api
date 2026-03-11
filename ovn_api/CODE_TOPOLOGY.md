# OVN API Code Topology

Tai lieu nay giai thich theo ngon ngu don gian:

1. He thong nay chay nhu the nao.
2. Moi file code dung de lam gi.
3. Request di qua cac file theo thu tu nao.

## 1. Topology Tong The

```text
Client / curl / UI
        |
        v
FastAPI Application
app/main.py
        |
        +--> routers/health.py
        +--> routers/flows.py
        +--> routers/topology.py
        +--> routers/chassis.py
        +--> routers/metrics.py
                |
                v
            services/*
                |
                v
            core/*
                |
                +--> OVN Northbound DB
                +--> OVN Southbound DB
                +--> OVS runtime command
```

## 2. Topology Chi Tiet Theo Tung Lop

```text
app/main.py
    |
    +--> app/routers/health.py
    |       |
    |       +--> app/config.py
    |
    +--> app/routers/topology.py
    |       |
    |       +--> app/services/topology_service.py
    |               |
    |               +--> app/core/ovn_nb.py
    |                       |
    |                       +--> app/core/ovsdb.py
    |                               |
    |                               +--> ovn_nb_db
    |
    +--> app/routers/flows.py
    |       |
    |       +--> app/services/flow_service.py
    |               |
    |               +--> app/core/ovn_sb.py
    |               |       |
    |               |       +--> app/core/ovsdb.py
    |               |               |
    |               |               +--> ovn_sb_db
    |               |
    |               +--> app/core/ovs.py
    |                       |
    |                       +--> app/core/command.py
    |                               |
    |                               +--> docker exec / local command
    |
    +--> app/routers/chassis.py
    |       |
    |       +--> app/services/chassis_service.py
    |               |
    |               +--> app/core/ovn_sb.py
    |
    +--> app/routers/metrics.py
            |
            +--> app/services/metrics_service.py
                    |
                    +--> app/core/ovn_nb.py
                    +--> app/core/ovn_sb.py
                    +--> app/services/datapath_metrics_collector.py
                            |
                            +--> app/core/ovs.py
                                    |
                                    +--> app/core/command.py
```

## 3. Luong Request Mau

### 3.1 Khi goi `/api/v1/routers`

```text
curl
 -> routers/topology.py
 -> services/topology_service.py
 -> core/ovn_nb.py
 -> core/ovsdb.py
 -> ovn_nb_db
 -> du lieu router
 -> models/topology.py
 -> JSON response
```

### 3.2 Khi goi `/api/v1/flows/logical`

```text
curl
 -> routers/flows.py
 -> services/flow_service.py
 -> core/ovn_sb.py
 -> core/ovsdb.py
 -> ovn_sb_db
 -> Logical_Flow rows
 -> models/flow.py
 -> JSON response
```

Neu can loc flow do ACL hoac NAT tao ra:

- `/api/v1/flows/logical?origin=acl`
- `/api/v1/flows/logical?origin=acl_exact`
- `/api/v1/flows/logical?origin=acl_stage_generic`
- `/api/v1/flows/logical?origin=nat`
- `/api/v1/flows/logical?origin=nat_exact`
- `/api/v1/flows/logical?origin=nat_stage_generic`
- `/api/v1/flows/logical?origin_uuid=<UUID-cua-ACL-hoac-NAT>`

Service se classify theo 2 tang:

- `acl_exact` / `nat_exact`:
  doc `Logical_Flow.external_ids["stage-hint"]` trong SB DB va doi chieu voi
  UUID hoac prefix UUID cua `ACL` / `NAT` trong NB DB.
- `acl_stage_generic` / `nat_stage_generic`:
  fallback theo `stage-name` khi flow nam trong ACL/NAT pipeline nhung khong
  map exact duoc ve tung ACL/NAT.

Neu can xem so luong tong hop:

- `/api/v1/flows/logical/summary`

Endpoint nay tra ve:

- tong so logical flow
- tong so logical flow lien quan ACL
- tong so logical flow lien quan NAT
- tach rieng `exact` va `stage_generic`
- tong so ACL va tong so NAT

Bang classify moi:

| `origin_type` | Y nghia |
| --- | --- |
| `acl_exact` | Flow map exact duoc ve 1 ACL trong NB bang `stage-hint` full UUID hoac UUID prefix |
| `acl_stage_generic` | Flow thuoc ACL pipeline nhung khong map exact duoc ve 1 ACL |
| `nat_exact` | Flow map exact duoc ve 1 NAT trong NB bang `stage-hint` full UUID hoac UUID prefix |
| `nat_stage_generic` | Flow thuoc NAT pipeline nhung khong map exact duoc ve 1 NAT |
| `other` | Flow khong thuoc ACL/NAT pipeline hoac khong du thong tin de classify |

### 3.3 Khi goi `/api/v1/flows/openflow`

```text
curl
 -> routers/flows.py
 -> services/flow_service.py
 -> core/ovs.py
 -> core/command.py
 -> docker exec openvswitch_vswitchd ovs-ofctl dump-flows
 -> JSON response
```

## 4. Bang Interface: IDL vs CMD vs Interface Khac

### 4.1 Bang Theo Tung API / Nguon Du Lieu

| API / du lieu | Dang dung gi | Giao tiep hien tai | File chinh | Sau nay co the thay bang gi |
| --- | --- | --- | --- | --- |
| `/api/v1/routers` | IDL | OVN Northbound OVSDB | `app/services/topology_service.py` | `ovsdbapp` wrapper hoac service layer cao hon |
| `/api/v1/routers/{id}` | IDL | OVN Northbound OVSDB | `app/services/topology_service.py` | `ovsdbapp` wrapper hoac service layer cao hon |
| `/api/v1/switches` | IDL | OVN Northbound OVSDB | `app/services/topology_service.py` | `ovsdbapp` wrapper hoac service layer cao hon |
| `/api/v1/switches/{id}` | IDL | OVN Northbound OVSDB | `app/services/topology_service.py` | `ovsdbapp` wrapper hoac service layer cao hon |
| `/api/v1/flows/logical` | IDL | OVN Southbound OVSDB | `app/services/flow_service.py` | `ovsdbapp` wrapper hoac event stream tu SB |
| `/api/v1/flows/logical/summary` | IDL | OVN Southbound + OVN Northbound OVSDB | `app/services/flow_service.py` | cache layer hoac Prometheus exporter |
| `/api/v1/chassis` | IDL | OVN Southbound OVSDB | `app/services/chassis_service.py` | `ovsdbapp` wrapper hoac cache layer |
| `/api/v1/chassis/{id}/bindings` | IDL | OVN Southbound OVSDB | `app/services/chassis_service.py` | `ovsdbapp` wrapper hoac cache layer |
| `/api/v1/metrics/capacity` | IDL | NB + SB OVSDB | `app/services/metrics_service.py` | Prometheus exporter hoac metrics cache |
| `/api/v1/metrics/datapath` | Background cache + CMD collector | `ovs-appctl dpctl/show` duoc collector goi dinh ky | `app/services/metrics_service.py`, `app/services/datapath_metrics_collector.py` | OVS telemetry/exporter rieng hoac interface runtime khac |
| `/api/v1/metrics/latency` | IDL | NB + SB OVSDB | `app/services/metrics_service.py` | Prometheus exporter hoac metrics cache |
| `/api/v1/flows/openflow` | CMD | `ovs-ofctl dump-flows` | `app/services/flow_service.py`, `app/core/ovs.py` | OVSDB appctl wrapper, OVS Python/runtime API neu can, hoac parser service rieng |

### 4.2 Bang Theo Thanh Phan Noi Bo

| Thanh phan | Dang dung gi | Muc dich | File chinh | Sau nay co the thay bang gi |
| --- | --- | --- | --- | --- |
| Doc OVN NB schema | IDL bootstrap | OVSDB RPC `get_schema` vao `OVN_Northbound` neu host khong co schema local | `app/core/ovsdb.py` | Mount schema local neu muon boot nhanh hon |
| Doc OVN SB schema | IDL bootstrap | OVSDB RPC `get_schema` vao `OVN_Southbound` neu host khong co schema local | `app/core/ovsdb.py` | Mount schema local neu muon boot nhanh hon |
| Datapath metrics collector | Background cache + CMD | collector nen goi `ovs-appctl dpctl/show` theo chu ky va cache trong memory | `app/services/datapath_metrics_collector.py` | Prometheus exporter rieng hoac runtime API khac |
| Dump OpenFlow runtime | CMD | `ovs-ofctl dump-flows` trong `openvswitch_vswitchd` | `app/core/ovs.py`, `app/core/command.py` | `ovs-appctl`, parser/service layer rieng, hoac telemetry pipeline |

### 4.3 Ket Luan Ngan

- Phan lon API hien tai dang dung IDL.
- Phan bootstrap schema cho NB/SB da chuyen sang OVSDB RPC `get_schema`.
- `/api/v1/metrics/datapath` khong chay CMD moi request, ma doc cache tu collector nen.
- Phan dang dung CMD de lay data runtime la OpenFlow.
- Neu muc tieu cua ban la "bo CLI/CMD", thi uu tien thay the theo thu tu:
  1. datapath collector command
  2. openflow dump

## 5. Vai Tro Tung Thu Muc

### `app/`

Day la noi chua toan bo source code chinh cua API.

### `app/core/`

Day la lop noi chuyen voi he thong ben ngoai:

- OVN Northbound
- OVN Southbound
- OVS runtime command
- command local hoac docker-exec

### `app/routers/`

Day la lop nhan HTTP request. Router khong xu ly logic phuc tap, chi nhan request va goi sang service.

### `app/services/`

Day la lop xu ly nghiep vu. Noi day doc row tu OVN/OVS, loc du lieu, sap xep, dem so luong, roi tra ve output sach se.

### `app/models/`

Day la dinh nghia output JSON. Ban co the hieu don gian: model quy dinh API se tra ve nhung field nao.

## 6. Chuc Nang Tung File

### Cap root cua project

- `requirements.txt`
  Danh sach Python package can cai de chay project.

- `app/__init__.py`
  Khoi tao package `app`.
  File nay con bootstrap de Python import duoc thu vien `ovs` local va fallback `ovs.dirs`.

- `app/main.py`
  Diem vao chinh cua FastAPI.
  File nay tao app va gan tat ca router vao app.

- `app/config.py`
  Doc bien moi truong.
  Vi du:
  - OVN_NB_DB
  - OVN_NB_DB_NAME
  - OVN_SB_DB
  - OVN_SB_DB_NAME
  - OVN_NB_CONTAINER
  - OVN_SB_CONTAINER
  - OVS_VSWITCHD_CONTAINER
  - OVN_COMMAND_TRANSPORT
  - DATAPATH_METRICS_INTERVAL_S

### `app/core/`

- `app/core/command.py`
  Lop chay command.
  Ho tro 2 kieu:
  - local: chay command tren host
  - docker-exec: chay command trong container

- `app/core/ovsdb.py`
  Lop generic de tao OVSDB IDL client.
  Chuc nang:
  - load schema local neu co
  - neu khong co file schema local thi goi OVSDB RPC `get_schema`
  - tao `Idl`
  - sync initial data
  - bao loi neu ket noi that bai

- `app/core/ovn_nb.py`
  Tao client cho OVN Northbound.
  Day la noi dung de doc:
  - Logical_Switch
  - Logical_Router
  - ACL
  - NAT
  - Load_Balancer

- `app/core/ovn_sb.py`
  Tao client cho OVN Southbound.
  Day la noi dung de doc:
  - Logical_Flow
  - Chassis
  - Port_Binding
  - BFD
  - Datapath_Binding

- `app/core/ovs.py`
  Tao client de lay OpenFlow runtime bang `ovs-ofctl dump-flows`.

- `app/core/__init__.py`
  File danh dau package.
  Khong co logic chinh.

### `app/routers/`

- `app/routers/health.py`
  Endpoint `/health`.
  Dung de xem app dang chay voi config nao.

- `app/routers/topology.py`
  Endpoint:
  - `/api/v1/switches`
  - `/api/v1/switches/{id}`
  - `/api/v1/routers`
  - `/api/v1/routers/{id}`

- `app/routers/flows.py`
  Endpoint:
  - `/api/v1/flows/logical`
  - `/api/v1/flows/logical/summary`
  - `/api/v1/flows/openflow`

- `app/routers/chassis.py`
  Endpoint:
  - `/api/v1/chassis`
  - `/api/v1/chassis/{id}/bindings`

- `app/routers/metrics.py`
  Endpoint:
  - `/api/v1/metrics/capacity`
  - `/api/v1/metrics/datapath`
  - `/api/v1/metrics/latency`

- `app/routers/__init__.py`
  File danh dau package.

### `app/services/`

- `app/services/topology_service.py`
  Xu ly du lieu ve router va switch.
  Day la noi chuyen tu row OVN raw thanh output de con nguoi doc duoc.

- `app/services/flow_service.py`
  Xu ly:
  - logical flow tu OVN Southbound
  - doi chieu `stage-hint` voi UUID `ACL`/`NAT` de xac dinh logical flow do ACL hay NAT sinh ra
  - dem so luong logical flow theo nhom ACL/NAT
  - openflow tu OVS

- `app/services/chassis_service.py`
  Xu ly:
  - danh sach chassis
  - port binding cua moi chassis

- `app/services/metrics_service.py`
  Xu ly:
  - dem so luong logical object
  - doc datapath metrics tu background collector
  - do query latency co ban
  - thong ke BFD session

- `app/services/datapath_metrics_collector.py`
  Collector nen cho datapath metrics.
  File nay dinh ky goi `ovs-appctl dpctl/show`, parse output va cache ket qua trong memory.

- `app/services/__init__.py`
  File danh dau package.

### `app/models/`

- `app/models/topology.py`
  Dinh nghia JSON cho switch/router summary va detail.

- `app/models/flow.py`
  Dinh nghia JSON cho:
  - LogicalFlow
  - LogicalFlowOriginSummary
  - OpenFlowDump

- `app/models/chassis.py`
  Dinh nghia JSON cho:
  - ChassisSummary
  - ChassisBinding
  - ChassisBindingsResponse

- `app/models/metrics.py`
  Dinh nghia JSON cho:
  - CapacityMetrics
  - DatapathMetrics
  - LatencyMetrics

- `app/models/health.py`
  Dinh nghia JSON cho endpoint `/health`.

- `app/models/__init__.py`
  File danh dau package.

## 7. NB va SB Dang Chua Gi

Day la y cuc ky quan trong:

- OVN Northbound chua "y dinh" network
  Vi du:
  - router
  - switch
  - port
  - ACL
  - NAT

- OVN Southbound chua "trang thai thuc thi"
  Vi du:
  - logical flow
  - chassis
  - port binding
  - BFD

Noi ngan gon:

- Muon biet user tao gi: xem NB
- Muon biet he thong dang thuc thi ra sao: xem SB

## 8. Cach Doc Code Neu Ban Khong Gioi Python

Nen doc theo thu tu nay:

1. `app/main.py`
2. `app/routers/topology.py`
3. `app/services/topology_service.py`
4. `app/core/ovn_nb.py`
5. `app/core/ovsdb.py`
6. `app/models/topology.py`

Sau khi hieu duoc 1 luong, moi doc tiep:

1. `app/routers/flows.py`
2. `app/services/flow_service.py`
3. `app/core/ovn_sb.py`
4. `app/core/ovs.py`
5. `app/core/command.py`

## 9. Hieu Don Gian Theo Vai Tro

- `router` = cua vao HTTP
- `service` = noi xu ly logic
- `core` = noi noi chuyen voi OVN/OVS
- `model` = khuon JSON output
- `config` = noi doc bien moi truong
- `main` = noi lap rap toan bo app

## 10. Cac File It Quan Tam Hon

Nhung file sau khong can doc ky trong giai doan dau:

- `__init__.py` trong `core/`, `routers/`, `services/`, `models/`
- `__pycache__/`

Ban chi can biet chung dung de Python nhan package hoac cache bytecode.

## 11. Tom Tat Mot Cau

He thong nay duoc thiet ke theo luong:

`HTTP request -> router -> service -> core -> OVN/OVS -> model -> JSON response`

Neu can mo rong them API moi, ban thuong chi can them:

1. route moi trong `routers/`
2. ham xu ly moi trong `services/`
3. neu can, bo sung model output trong `models/`
4. neu can noi voi nguon du lieu moi, mo rong `core/`
