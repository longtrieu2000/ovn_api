import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware.api_metrics import ApiMetricsMiddleware
from .routers import chassis, flows, health, metrics, monitoring, topology, traces
from .services.datapath_metrics_collector import get_datapath_metrics_collector
from .services.live_monitoring_service import get_live_monitoring_service
from .services.trace_manager import get_canary_trace_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    collector = get_datapath_metrics_collector()
    trace_manager = get_canary_trace_manager()
    monitoring_service = get_live_monitoring_service()
    collector.start()
    trace_manager.start()
    monitoring_service.start()
    try:
        yield
    finally:
        monitoring_service.stop()
        trace_manager.stop()
        collector.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="OVN Dev API", version="0.3.0", lifespan=lifespan)
    app.add_middleware(ApiMetricsMiddleware)
    # Browsers block cross-origin fetch from the web UI (e.g. :3089) to the API (:8001)
    # unless CORS allows the UI origin. Add last so this runs first on each request.
    _cors = os.getenv("OVN_API_CORS_ORIGINS", "").strip()
    if _cors:
        _origins = [o.strip() for o in _cors.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Dev default: any http(s) origin on localhost / 127.0.0.1 with a port
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router)
    app.include_router(flows.router, prefix="/api/v1", tags=["flows"])
    app.include_router(topology.router, prefix="/api/v1", tags=["topology"])
    app.include_router(chassis.router, prefix="/api/v1", tags=["chassis"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
    app.include_router(traces.router, prefix="/api/v1", tags=["traces"])
    return app


app = create_app()
