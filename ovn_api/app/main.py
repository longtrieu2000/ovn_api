from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import chassis, flows, health, metrics, topology
from .services.datapath_metrics_collector import get_datapath_metrics_collector


@asynccontextmanager
async def lifespan(_: FastAPI):
    collector = get_datapath_metrics_collector()
    collector.start()
    try:
        yield
    finally:
        collector.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="OVN Dev API", version="0.3.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(flows.router, prefix="/api/v1", tags=["flows"])
    app.include_router(topology.router, prefix="/api/v1", tags=["topology"])
    app.include_router(chassis.router, prefix="/api/v1", tags=["chassis"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    return app


app = create_app()
