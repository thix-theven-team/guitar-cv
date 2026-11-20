from dataclasses import dataclass
from datetime import datetime

from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.storage.local_storage import LocalStorage


@dataclass(frozen=True, slots=True)
class CleanupReport:
    input_files_deleted: int
    result_files_deleted: int
    model_metadata_files_deleted: int
    conversion_records_deleted: int
    deletion_failures: int


class CleanupService:
    def __init__(
        self,
        repository: ConversionRepository,
        storage: LocalStorage,
    ) -> None:
        ... # TODO

    def cleanup_expired_files(
        self,
        now: datetime,
    ) -> tuple[int, int, int]:
        ... # TODO

    def cleanup_expired_records(
        self,
        now: datetime,
    ) -> int:
        ... # TODO

    def run_once(
        self,
        now: datetime,
    ) -> CleanupReport:
        ... # TODO
