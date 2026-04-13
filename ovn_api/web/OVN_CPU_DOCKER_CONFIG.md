# OVN CPU Monitoring Service - Docker Configuration

This guide provides docker-compose configuration for running the `ovn_cpu` monitoring agents from the ovn_api repository.

## 📦 Docker Compose for OVN CPU Monitoring

### File: `docker-compose.ovn-cpu.yml`

Create this file in your `ovn_api` repository root:

```yaml
version: '3.8'

services:
  # OVN CPU Monitoring Agent
  ovn-cpu-monitor:
    build:
      context: ./ovn_cpu
      dockerfile: Dockerfile
    container_name: ovn_cpu_monitor
    ports:
      - "8002:8002"
    environment:
      - MONITOR_INTERVAL=5
      - OVN_PROCESSES=ovn-northd,ovn-controller,ovsdb-server
      - METRICS_PORT=8002
      - LOG_LEVEL=INFO
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - ./ovn_cpu/data:/app/data
    privileged: true
    network_mode: "host"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  # Optional: Prometheus for metrics storage
  prometheus:
    image: prom/prometheus:latest
    container_name: ovn_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    restart: unless-stopped
    networks:
      - ovn_monitoring

  # Optional: Grafana for visualization
  grafana:
    image: grafana/grafana:latest
    container_name: ovn_grafana
    ports:
      - "3040:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./ovn_cpu/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./ovn_cpu/grafana/datasources:/etc/grafana/provisioning/datasources
    restart: unless-stopped
    networks:
      - ovn_monitoring
    depends_on:
      - prometheus

volumes:
  prometheus_data:
  grafana_data:

networks:
  ovn_monitoring:
    driver: bridge
    name: ovn_monitoring_network
```

---

## 🐳 Dockerfile for OVN CPU Monitor

### File: `ovn_cpu/Dockerfile`

Create this in the `ovn_cpu` directory:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose metrics port
EXPOSE 8002

# Run the CPU monitoring agent
CMD ["python", "-m", "ovn_cpu.main"]
```

---

## 📋 Requirements File

### File: `ovn_cpu/requirements.txt`

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
psutil==5.9.6
prometheus-client==0.19.0
pydantic==2.5.0
pydantic-settings==2.1.0
```

---

## ⚙️ Prometheus Configuration

### File: `prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'ovn-cpu-monitor'
    static_configs:
      - targets: ['ovn-cpu-monitor:8002']
        labels:
          service: 'ovn-cpu'
          
  - job_name: 'ovn-api'
    static_configs:
      - targets: ['localhost:8001']
        labels:
          service: 'ovn-api'
```

---

## 🚀 Complete Stack - All Services Together

### File: `docker-compose.full-stack.yml`

Run the entire OVN monitoring stack (API + CPU + Dashboard):

```yaml
version: '3.8'

services:
  # 1. OVN API (Main FastAPI Service)
  ovn-api:
    build:
      context: ./ovn_api
      dockerfile: Dockerfile
    container_name: ovn_api_service
    ports:
      - "8001:8001"
    environment:
      - OVN_COMMAND_TRANSPORT=local
      - TRACE_STORE_URL=postgresql://ovn:ovn123@postgres:5432/ovn_traces
      - OVN_NB_CONNECTION=tcp:172.17.0.1:6641
      - OVN_SB_CONNECTION=tcp:172.17.0.1:6642
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped
    networks:
      - ovn_network
    depends_on:
      - postgres

  # 2. OVN CPU Monitor
  ovn-cpu-monitor:
    build:
      context: ./ovn_cpu
      dockerfile: Dockerfile
    container_name: ovn_cpu_monitor
    ports:
      - "8002:8002"
    environment:
      - MONITOR_INTERVAL=5
      - OVN_PROCESSES=ovn-northd,ovn-controller,ovsdb-server
      - METRICS_PORT=8002
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    privileged: true
    network_mode: "host"
    restart: unless-stopped

  # 3. Web Dashboard
  ovn-dashboard:
    build:
      context: ./ovn-dashboard/apps/web
      dockerfile: Dockerfile
    container_name: ovn_dashboard_web
    ports:
      - "3039:3039"
    environment:
      - NODE_ENV=production
      - PORT=3039
      - NEXT_PUBLIC_API_URL=http://ovn-api:8001
    restart: unless-stopped
    networks:
      - ovn_network
    depends_on:
      - ovn-api

  # 4. PostgreSQL (Trace Storage)
  postgres:
    image: postgres:15-alpine
    container_name: ovn_postgres
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=ovn
      - POSTGRES_PASSWORD=ovn123
      - POSTGRES_DB=ovn_traces
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    networks:
      - ovn_network

  # 5. Prometheus
  prometheus:
    image: prom/prometheus:latest
    container_name: ovn_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    restart: unless-stopped
    networks:
      - ovn_network

  # 6. Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: ovn_grafana
    ports:
      - "3040:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped
    networks:
      - ovn_network
    depends_on:
      - prometheus

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:

networks:
  ovn_network:
    driver: bridge
    name: ovn_monitoring_network
```

---

## 🎯 Usage Instructions

### 1. CPU Monitor Only
```bash
# In your ovn_api repository
docker-compose -f docker-compose.ovn-cpu.yml up -d

# View logs
docker-compose -f docker-compose.ovn-cpu.yml logs -f ovn-cpu-monitor

# Check metrics
curl http://localhost:8002/metrics
```

### 2. Full Stack (Recommended)
```bash
# Run everything together
docker-compose -f docker-compose.full-stack.yml up -d

# Services will be available at:
# - OVN API: http://localhost:8001
# - CPU Monitor: http://localhost:8002
# - Web Dashboard: http://localhost:3039
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3040
```

### 3. Individual Services
```bash
# Start only specific services
docker-compose -f docker-compose.full-stack.yml up -d ovn-api ovn-cpu-monitor

# Scale CPU monitors
docker-compose -f docker-compose.full-stack.yml up -d --scale ovn-cpu-monitor=3
```

---

## 📊 Accessing Services

| Service | URL | Credentials |
|---------|-----|-------------|
| OVN API | http://localhost:8001 | - |
| CPU Monitor | http://localhost:8002 | - |
| Web Dashboard | http://localhost:3039 | - |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3040 | admin/admin |

---

## 🔧 Environment Variables

### OVN CPU Monitor

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_INTERVAL` | 5 | Seconds between CPU samples |
| `OVN_PROCESSES` | ovn-northd,ovn-controller | Processes to monitor |
| `METRICS_PORT` | 8002 | Port for metrics endpoint |
| `LOG_LEVEL` | INFO | Logging level |

### OVN API

| Variable | Default | Description |
|----------|---------|-------------|
| `OVN_COMMAND_TRANSPORT` | local | Command execution mode |
| `TRACE_STORE_URL` | sqlite:///./traces.db | Database connection |
| `OVN_NB_CONNECTION` | tcp:127.0.0.1:6641 | NB database |
| `OVN_SB_CONNECTION` | tcp:127.0.0.1:6642 | SB database |

---

## 🐛 Troubleshooting

### CPU Monitor not detecting processes
```bash
# Check if running with proper privileges
docker-compose logs ovn-cpu-monitor

# Verify host /proc is mounted
docker exec ovn_cpu_monitor ls /host/proc
```

### Network mode issues
If using `network_mode: "host"`, remove the `networks` section from that service.

### Permission denied errors
Ensure the container runs with `privileged: true` for /proc access.

---

## 📁 Directory Structure

Your final structure should look like:

```
ovn_api/
├── ovn_api/              # Main API service
├── ovn_cpu/              # CPU monitoring agent
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── grafana/
├── prometheus/
│   └── prometheus.yml
├── docker-compose.ovn-cpu.yml
├── docker-compose.full-stack.yml
└── README.md
```

---

## ✅ Next Steps

1. Copy these configurations to your `ovn_api` repository
2. Adjust OVN connection strings to match your environment
3. Run `docker-compose -f docker-compose.full-stack.yml up -d`
4. Open the web dashboard at http://localhost:3039
5. Configure Grafana dashboards for CPU metrics

---

**Questions?** The CPU monitor exposes Prometheus metrics at `/metrics` endpoint and health check at `/health`.
