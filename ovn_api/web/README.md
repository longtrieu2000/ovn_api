# OVN Control Plane Monitor Dashboard

A high-fidelity web dashboard for monitoring and analyzing OVN (Open Virtual Network) infrastructure in real-time.

## Features

### 📊 Overview Dashboard
- Real-time control plane latency metrics
- Active canary probe monitoring
- OVN database connection status
- OpenFlow rule statistics
- System health indicators
- Recent activity timeline

### ⚡ Canary Probe Monitoring
- End-to-end latency measurement
- NB → SB → OpenFlow pipeline visualization
- Trigger manual probes
- Historical trace results
- Latency breakdown (northd compilation, controller realization)

### 💾 Database State Explorer
- Browse OVN Northbound and Southbound tables
- Search and filter tables
- View table contents and metadata
- Real-time OVSDB state inspection

### 🌐 OpenFlow Monitor
- Live OpenFlow rule inspection
- Filter by table and search patterns
- Download flow dumps
- Action and priority distribution analysis
- Packet statistics

### 📈 Performance Metrics
- Historical latency charts (NB→SB, SB→OpenFlow)
- CPU usage tracking (northd, ovn-controller)
- Latency percentiles (P50, P75, P95, P99)
- Resource utilization monitoring
- Configurable time ranges (15m, 1h, 6h, 24h)

## Design System

This dashboard follows a **High-Fidelity SaaS** design language with:
- **Ghost Structure**: Ultra-thin borders (`1px solid #E5E7EB`) for organization
- **Typography**: Inter font with precise weight contrasts
- **Pill Taxonomy**: Metadata pills, soft action pills, status indicators
- **Flat Elevation**: No drop shadows, border-based depth
- **Action Blue**: Color reserved for primary actions and active states

## Connecting to Your OVN API

The dashboard expects your `ovn_api` FastAPI service to be running and accessible. By default, it connects to `http://localhost:8001`.

### Expected API Endpoints

The dashboard makes requests to these endpoints (with graceful fallbacks if unavailable):

#### Health & Stats
- `GET /health` - Service health status
- `GET /api/stats` - Overall system statistics

#### Canary Probes
- `GET /api/canary/probes` - List active probes
- `GET /api/canary/latest-trace` - Most recent trace result
- `POST /api/canary/trigger` - Manually trigger a probe

#### Database State
- `GET /api/ovn/nb/tables` - List Northbound tables
- `GET /api/ovn/sb/tables` - List Southbound tables
- `GET /api/ovn/nb/table/{name}` - Get NB table data
- `GET /api/ovn/sb/table/{name}` - Get SB table data

#### OpenFlow
- `GET /api/ovs/flows` - Dump OpenFlow rules

#### Performance
- `GET /api/metrics/history?range={timeRange}` - Historical metrics

### Configuring the API URL

You can change the API endpoint directly in the dashboard UI:
1. Look for the API URL input in the top-right header
2. Enter your OVN API service URL (e.g., `http://your-server:8001`)
3. The dashboard will automatically reconnect

### Running with Docker

If your `ovn_api` service is running in Docker:

1. Start your OVN API service:
   ```bash
   cd /path/to/ovn_api
   docker-compose up
   ```

2. Start this dashboard:
   ```bash
   npm run dev
   ```

3. Access the dashboard at `http://localhost:3089`

### CORS Configuration

If your OVN API is on a different domain, ensure it has CORS enabled:

```python
# In your FastAPI app (ovn_api/app/main.py)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3089"],  # Your dashboard URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Mock Data

The dashboard includes mock data for development and demonstration when the API is unavailable. This allows you to:
- Preview the UI design
- Test dashboard functionality
- Develop without a running OVN infrastructure

## Technologies

- **React** - UI framework
- **Recharts** - Performance visualizations
- **Tailwind CSS** - Styling with custom design tokens
- **React Query** - Data fetching and caching
- **Lucide Icons** - Iconography

## Next Steps

Once connected, you can:
- Monitor your OVN control plane latency in real-time
- Trigger canary probes to measure infrastructure performance
- Explore your OVSDB state across Northbound and Southbound databases
- Analyze OpenFlow rules and identify bottlenecks
- Track historical performance trends
