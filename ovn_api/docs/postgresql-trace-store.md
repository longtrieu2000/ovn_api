# OVN API Trace Store With PostgreSQL

Tai lieu nay huong dan dung PostgreSQL thay cho SQLite cho `TRACE_STORE_URL` cua OVN API.

## 1. Muc tieu

Service canary trace dang persist lich su run vao SQL trace store qua bien moi truong:

```env
TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
TRACE_STORE_MAX_RUNS=500
```

Schema duoc tao tu dong khi app start boi `SqlCanaryTraceStore.initialize()`, nen ban khong can chay migration rieng cho phien ban hien tai.

## 2. Dung PostgreSQL bang Docker Compose

File compose da duoc them tai:

```text
ovn_api/docker-compose.postgres.yml
```

Khoi dong container:

```bash
docker compose -f /home/longth1/workspace/openstack/ovn_api/docker-compose.postgres.yml up -d
```

Kiem tra health:

```bash
docker compose -f /home/longth1/workspace/openstack/ovn_api/docker-compose.postgres.yml ps
docker exec -it ovn_trace_postgres pg_isready -U ovn_api -d ovn_api
```

## 3. Thong so ket noi

Mac dinh compose tao ra:

- Host port: `5432`
- Database: `ovn_api`
- User: `ovn_api`
- Password: `ovn_api_pass`
- Container name: `ovn_trace_postgres`

Neu OVN API chay tren host:

```env
TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
```

Neu OVN API chay trong container cung compose network:

```env
TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@ovn-trace-postgres:5432/ovn_api
```

Luu y:

- `ovn-trace-postgres` la service name trong compose.
- `127.0.0.1` chi dung khi app chay tren host va port `5432` duoc publish ra ngoai.

## 4. Chay OVN API voi PostgreSQL

Tu workspace root:

```bash
export TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
export TRACE_STORE_MAX_RUNS=500

python3 -m uvicorn ovn_api.app.main:app --host 0.0.0.0 --port 8001
```

Neu ban dung file env:

```env
TRACE_STORE_URL=postgresql+psycopg://ovn_api:ovn_api_pass@127.0.0.1:5432/ovn_api
TRACE_STORE_MAX_RUNS=500
```

Sau do start lai service theo cach ban dang deploy.

## 5. Kiem tra ket noi

Sau khi app start, goi thu capability:

```bash
curl -s http://127.0.0.1:8001/api/v1/traces/capabilities | jq '.store_scope'
```

Ban se thay `current dialect: postgresql+psycopg` neu service doc dung `TRACE_STORE_URL`.

Kiem tra luu trace:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/traces/canary \
  -H 'Content-Type: application/json' \
  -d '{
    "resource_type": "logical_switch",
    "timeout_s": 15
  }' | jq '.probe_id, .status'
```

Sau do xem du lieu trong PostgreSQL:

```bash
docker exec -it ovn_trace_postgres psql -U ovn_api -d ovn_api -c \
  "select probe_id, requested_resource_type, status, queued_at from canary_trace_runs order by queued_at desc limit 10;"
```

## 6. Loi thuong gap

### `ModuleNotFoundError: No module named 'psycopg'`

Cai dependencies:

```bash
pip install -r /home/longth1/workspace/openstack/ovn_api/requirements.txt
```

### `connection refused`

Kiem tra:

- container PostgreSQL da `healthy` chua
- port `5432` co dang duoc bind khong
- `TRACE_STORE_URL` dang dung `127.0.0.1` hay service name cho dung voi cach app chay

### `password authentication failed`

Kiem tra lai:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- chuoi `TRACE_STORE_URL`

## 7. Dung va xoa

Dung container:

```bash
docker compose -f /home/longth1/workspace/openstack/ovn_api/docker-compose.postgres.yml down
```

Xoa ca data volume:

```bash
docker compose -f /home/longth1/workspace/openstack/ovn_api/docker-compose.postgres.yml down -v
```
