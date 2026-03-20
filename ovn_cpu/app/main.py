from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import cpu, health
from .services.cpu_monitor import get_cpu_monitor_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    service = get_cpu_monitor_service()
    service.start()
    try:
        yield
    finally:
        service.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="OVN CPU Monitor", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(cpu.router, prefix="/api/v1", tags=["cpu"])
    return app


app = create_app()
