import asyncio
import logging

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from guitarcv_restapi.core.config import Settings, settings
from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.database.schema import initialize_database
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.services.cleanup_service import CleanupService
from guitarcv_restapi.storage.local_storage import LocalStorage


logger = logging.getLogger(__name__)


def recover_interrupted_conversions(
    repository: ConversionRepository,
    settings: Settings,
    now: datetime | None = None,
) -> int:
    """Mark jobs left in PROCESSING after a previous process exit as failed"""
    finished_at = now or datetime.now(timezone.utc)
    return repository.mark_interrupted_as_failed(
        finished_at=finished_at,
        input_expires_at=finished_at + timedelta(
            seconds=settings.input_retention_seconds
        ),
        model_metadata_expires_at=finished_at + timedelta(
            seconds=settings.model_metadata_retention_seconds
        ),
        expires_at=finished_at + timedelta(
            seconds=settings.conversion_metadata_retention_seconds
        ),
    )


async def run_cleanup_loop(
    cleanup_service: CleanupService,
    interval_seconds: int,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("cleanup interval must be positive")

    while True:
        await asyncio.sleep(interval_seconds)
        now = datetime.now(timezone.utc)
        try:
            await asyncio.to_thread(cleanup_service.run_once, now)
        except Exception:
            logger.exception("Periodic cleanup pass failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(settings.sqlite_path)
    storage = LocalStorage(
        upload_dir=settings.upload_dir,
        result_dir=settings.result_dir,
        metadata_dir=settings.metadata_dir,
        temp_dir=settings.temp_dir,
    )

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    storage.ensure_directories()
    initialize_database(database)

    repository = ConversionRepository(database)
    interrupted_count = recover_interrupted_conversions(repository, settings)
    if interrupted_count:
        logger.warning(
            "Marked %d interrupted conversion(s) as failed",
            interrupted_count,
        )

    cleanup_service = CleanupService(repository, storage)

    # no task from the previous process can still be running at startup, so
    # remove abandoned normalized/annotated videos and partial upload copies
    removed_temporary = storage.clear_temporary_storage()
    if removed_temporary:
        logger.info("Removed %d abandoned temporary artifact(s)", removed_temporary)

    # repair crashes between writing a persistent artifact and storing its
    # path in sqlite (e.g. an upload before conversion registration or
    # a completed MIDI rename before the ready-state transaction)
    cleanup_service.prune_orphaned_artifacts()

    # run one pass at startup so expired artifacts from previous runs do not
    # have to wait for the first periodic interval
    try:
        await asyncio.to_thread(
            cleanup_service.run_once,
            datetime.now(timezone.utc),
        )
    except Exception:
        logger.exception("Initial cleanup pass failed")

    app.state.settings = settings
    app.state.database = database
    app.state.storage = storage
    app.state.conversion_repository = repository
    app.state.cleanup_service = cleanup_service

    cleanup_task = asyncio.create_task(
        run_cleanup_loop(
            cleanup_service,
            settings.cleanup_interval_seconds,
        ),
        name="guitarcv-cleanup",
    )

    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
