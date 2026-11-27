import logging

from dataclasses import dataclass
from datetime import datetime

from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.storage.local_storage import LocalStorage


logger = logging.getLogger(__name__)


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
        self.repository = repository
        self.storage = storage

    def cleanup_expired_files(
        self,
        now: datetime,
    ) -> tuple[int, int, int, int]:
        input_deleted = 0
        results_deleted = 0
        metadata_deleted = 0
        failures = 0

        for conversion in self.repository.find_expired_files(now):
            conversion_succeeded = True

            expired_artifacts = (
                (
                    conversion.input_path,
                    conversion.input_expires_at,
                    self.storage.delete_file,
                    "input",
                ),
                (
                    conversion.result_path,
                    conversion.result_expires_at,
                    self.storage.delete_file,
                    "result",
                ),
                (
                    conversion.model_metadata_path,
                    conversion.model_metadata_expires_at,
                    self.storage.delete_directory,
                    "metadata",
                ),
            )

            for path, expires_at, delete, artifact_type in expired_artifacts:
                if path is None or expires_at is None or expires_at > now:
                    continue

                try:
                    existed = (
                        self.storage.directory_exists(path)
                        if artifact_type == "metadata"
                        else self.storage.file_exists(path)
                    )
                    delete(path)

                    if existed:
                        if artifact_type == "input":
                            input_deleted += 1
                        elif artifact_type == "result":
                            results_deleted += 1
                        else:
                            metadata_deleted += 1
                except (OSError, ValueError):
                    conversion_succeeded = False
                    failures += 1
                    logger.exception(
                        "Failed to delete expired %s artifact for conversion %s",
                        artifact_type,
                        conversion.conversion_id,
                    )

            if conversion_succeeded:
                self.repository.clear_expired_file_paths(
                    conversion.conversion_id,
                    now,
                )

        return input_deleted, results_deleted, metadata_deleted, failures

    def prune_orphaned_artifacts(self) -> tuple[int, int]:
        """Delete persistent artifacts not referenced by any conversion row.
        Call this only during startup, before accepting requests or scheduling
        background tasks. It repairs crashes between writing a file and
        committing its path to sqlite.
        """
        referenced_paths = self.repository.get_referenced_artifact_paths()
        deleted = 0
        failures = 0

        for path in self.storage.iter_persistent_artifacts():
            try:
                if path.resolve() in referenced_paths:
                    continue
                if path.is_dir():
                    self.storage.delete_directory(path)
                else:
                    self.storage.delete_file(path)
                deleted += 1
            except (OSError, ValueError):
                failures += 1
                logger.exception(
                    "Failed to prune orphaned persistent artifact %s",
                    path,
                )

        if deleted or failures:
            logger.info(
                "Startup orphan pruning completed: deleted=%d failures=%d",
                deleted,
                failures,
            )
        return deleted, failures

    def cleanup_expired_records(self, now: datetime) -> int:
        deleted = 0
        for conversion in self.repository.find_expired_records(now):
            if self.repository.delete_by_id(conversion.conversion_id):
                deleted += 1
        return deleted

    def run_once(self, now: datetime) -> CleanupReport:
        (
            input_deleted,
            results_deleted,
            metadata_deleted,
            failures,
        ) = self.cleanup_expired_files(now)

        records_deleted = self.cleanup_expired_records(now)

        report = CleanupReport(
            input_files_deleted=input_deleted,
            result_files_deleted=results_deleted,
            model_metadata_files_deleted=metadata_deleted,
            conversion_records_deleted=records_deleted,
            deletion_failures=failures,
        )

        logger.info(
            "Cleanup completed: input=%d result=%d metadata=%d records=%d failures=%d",
            report.input_files_deleted,
            report.result_files_deleted,
            report.model_metadata_files_deleted,
            report.conversion_records_deleted,
            report.deletion_failures,
        )
        return report
