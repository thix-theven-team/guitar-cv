from typing import Annotated

from fastapi import Depends

from guitarcv_restapi.core.config import Settings, get_settings
from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.services.conversion_service import ConversionService
from guitarcv_restapi.services.submission_service import SubmissionService
from guitarcv_restapi.storage.local_storage import LocalStorage
from guitarcv_restapi.processing.media.ffprobe import FFprobeValidator


def get_database(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Database:
    return Database(settings.database_path)


def get_local_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LocalStorage:
    return LocalStorage(
        upload_dir=settings.upload_dir,
        result_dir=settings.result_dir,
    )


def get_ffprobe_validator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FFprobeValidator:
    return FFprobeValidator(
        timeout_seconds=settings.ffprobe_timeout_seconds,
    )


def get_conversion_repository(
    database: Annotated[Database, Depends(get_database)],
) -> ConversionRepository:
    return ConversionRepository(database)


def get_submission_service(
    repository: Annotated[
        ConversionRepository,
        Depends(get_conversion_repository),
    ],
    storage: Annotated[
        LocalStorage,
        Depends(get_local_storage),
    ],
    ffprobe: Annotated[
        FFprobeValidator,
        Depends(get_ffprobe_validator),
    ],
) -> SubmissionService:
    return SubmissionService(
        repository=repository,
        storage=storage,
        ffprobe=ffprobe,
    )


def get_conversion_service(
    repository: Annotated[
        ConversionRepository,
        Depends(get_conversion_repository),
    ],
) -> ConversionService:
    return ConversionService(
        repository=repository,
    )