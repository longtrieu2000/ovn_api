# OVN CPU Monitor

Service này theo dõi CPU usage của các process/thread liên quan tới OVN và OVS để soi các đợt spike như lúc restart `OVN_Southbound`.

## Vì sao bám các thread này

Các nhóm thread được map trực tiếp từ source tree local:

- `handler` và `revalidator` được tạo trong [`ovs/ofproto/ofproto-dpif-upcall.c`](/home/longth1/workspace/openstack/ovs/ofproto/ofproto-dpif-upcall.c).
- `pmd-*` được tạo trong [`ovs/lib/dpif-netdev.c`](/home/longth1/workspace/openstack/ovs/lib/dpif-netdev.c).
- `ovn_pinctrl` và `ovn_statctrl` được tạo trong [`ovn/controller/pinctrl.c`](/home/longth1/workspace/openstack/ovn/controller/pinctrl.c) và [`ovn/controller/statctrl.c`](/home/longth1/workspace/openstack/ovn/controller/statctrl.c).
- `compaction` và `log_fsync` của `ovsdb-server` được tạo trong [`ovs/ovsdb/ovsdb.c`](/home/longth1/workspace/openstack/ovs/ovsdb/ovsdb.c) và [`ovs/ovsdb/log.c`](/home/longth1/workspace/openstack/ovs/ovsdb/log.c).

Ngoài userspace, service còn đọc `ksoftirqd/*`, `irq/*`, `napi/*` và delta từ `/proc/softirqs` để có thêm tín hiệu kernel-side của datapath.

## Tính năng

- Sample CPU theo process và thread từ `procfs`, không cần `psutil`.
- Tách riêng `ovn-sb-db`, `ovn-nb-db`, `ovs-db`, `ovs-vswitchd`, `ovn-controller`, `ovn-northd`.
- Phân nhóm thread nóng như `handler`, `revalidator`, `pmd`, `pinctrl`, `statctrl`, `compaction`, `log_fsync`.
- Lưu history vòng tròn trong memory để query lại spike gần đây.
- Hỗ trợ chạy với host `/proc` mặc định hoặc mount host `/proc` vào path khác qua `OVN_CPU_PROC_ROOT`.

## Cài và chạy

Từ workspace root:

```bash
python3 -m pip install -r ovn_cpu/requirements.txt
python3 -m uvicorn ovn_cpu.app.main:app --host 0.0.0.0 --port 8002 --env-file ovn_cpu/.env
```

Nếu service chạy trong container nhưng muốn monitor host:

```bash
export OVN_CPU_PROC_ROOT=/host/proc
```

## Endpoint chính

- `GET /health`
- `GET /api/v1/cpu/snapshot`
- `GET /api/v1/cpu/history`
- `GET /api/v1/cpu/threads?component=ovs-vswitchd&thread_group=handler`
- `GET /api/v1/cpu/spikes?component=ovn-sb-db&threshold_pct=50`

Ví dụ:

```bash
curl -s http://127.0.0.1:8002/api/v1/cpu/snapshot | jq '.components'
curl -s 'http://127.0.0.1:8002/api/v1/cpu/threads?component=ovs-vswitchd&thread_group=revalidator' | jq
curl -s 'http://127.0.0.1:8002/api/v1/cpu/spikes?component=ovn-sb-db&threshold_pct=20' | jq
```

## Biến môi trường

- `OVN_CPU_HOST` mặc định `0.0.0.0`
- `OVN_CPU_PORT` mặc định `8002`
- `OVN_CPU_PROC_ROOT` mặc định `/proc`
- `OVN_CPU_SAMPLE_INTERVAL_S` mặc định `1.0`
- `OVN_CPU_HISTORY_SIZE` mặc định `900`
- `OVN_CPU_TOP_THREADS` mặc định `20`
- `OVN_CPU_THREADS_PER_COMPONENT` mặc định `5`
- `OVN_CPU_ENABLE_KERNEL_THREADS` mặc định `true`
- `OVN_CPU_SOFTIRQS` mặc định `NET_RX,NET_TX,RCU,TIMER,SCHED,HRTIMER`

## Test nhanh

```bash
python3 -m unittest discover -s ovn_cpu/tests -v
```
