from fastapi import FastAPI

from guitarcv_restapi.api.v1.router import router as v1_router
from guitarcv_restapi.core.exception_handlers import (
    register_exception_handlers,
)
from guitarcv_restapi.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="GuitarCV REST API",
        description="REST API for GuitarCV video-to-MIDI conversion",
        version="1.0.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.include_router(
        v1_router,
        prefix="/api/v1",
    )

    return app


app = create_app()
