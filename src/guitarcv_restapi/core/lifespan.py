import asyncio

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guitarcv_restapi.core.config import Settings
from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.services.cleanup_service import CleanupService


def recover_interrupted_conversions(
    repository: ConversionRepository,
) -> int:
    ... # TODO


async def run_cleanup_loop(
    cleanup_service: CleanupService,
    interval_seconds: int,
) -> None:
    ... # TODO


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    ... # TODO

    yield

    ... # TODO