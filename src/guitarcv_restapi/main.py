from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from guitarcv_restapi.api.v1.router import router as v1_router
from guitarcv_restapi.core.exception_handlers import (
    register_exception_handlers,
)
from guitarcv_restapi.core.lifespan import lifespan

from guitarcv_restapi.core.logging import setup as logging_setup


logging_setup()


def create_app() -> FastAPI:
    app = FastAPI(
        title="GuitarCV REST API",
        description="REST API for GuitarCV video-to-MIDI conversion",
        version="1.0.0",
        debug=False,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        #allow_origins=[
        #    "http://localhost:8000",
        #    "http://127.0.0.1:8000",
        #    "http://localhost:4500",
        #    "http://127.0.0.1:4500",
        #],
        allow_origins=["*"],  # TODO remove this! only for *local testing*
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(
        v1_router,
        prefix="/api/v1",
    )

    return app


app = create_app()