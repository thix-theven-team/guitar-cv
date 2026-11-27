import sqlite3

from datetime import datetime, timezone
from pathlib import Path

from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.models.conversion import Conversion, ConversionStatus


class ConversionRepository:
    """Persistence operations for conversion records"""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _parse_required_datetime(cls, value: str) -> datetime:
        parsed = cls._parse_datetime(value)
        if parsed is None:
            raise ValueError("A required timestamp is NULL")
        return parsed

    @classmethod
    def _row_to_conversion(cls, row: sqlite3.Row) -> Conversion:
        return Conversion(
            conversion_id=row["conversion_id"],
            status=ConversionStatus(row["status"]),
            created_at=cls._parse_required_datetime(row["created_at"]),
            updated_at=cls._parse_required_datetime(row["updated_at"]),
            input_path=(
                Path(row["input_path"])
                if row["input_path"] is not None
                else None
            ),
            result_path=(
                Path(row["result_path"])
                if row["result_path"] is not None
                else None
            ),
            model_metadata_path=(
                Path(row["model_metadata_path"])
                if row["model_metadata_path"] is not None
                else None
            ),
            error_code=row["error_code"],
            error_message=row["error_message"],
            started_at=cls._parse_datetime(row["started_at"]),
            finished_at=cls._parse_datetime(row["finished_at"]),
            input_expires_at=cls._parse_datetime(row["input_expires_at"]),
            result_expires_at=cls._parse_datetime(row["result_expires_at"]),
            model_metadata_expires_at=cls._parse_datetime(
                row["model_metadata_expires_at"]
            ),
            expires_at=cls._parse_datetime(row["expires_at"]),
        )

    def create(self, conversion: Conversion) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO conversions (
                    conversion_id, status, created_at, updated_at,
                    input_path, result_path, model_metadata_path,
                    error_code, error_message, started_at, finished_at,
                    input_expires_at, result_expires_at,
                    model_metadata_expires_at, expires_at
                )
                VALUES (
                    :conversion_id, :status, :created_at, :updated_at,
                    :input_path, :result_path, :model_metadata_path,
                    :error_code, :error_message, :started_at, :finished_at,
                    :input_expires_at, :result_expires_at,
                    :model_metadata_expires_at, :expires_at
                )
                """,
                {
                    "conversion_id": conversion.conversion_id,
                    "status": conversion.status.value,
                    "created_at": self._serialize_datetime(conversion.created_at),
                    "updated_at": self._serialize_datetime(conversion.updated_at),
                    "input_path": (
                        str(conversion.input_path)
                        if conversion.input_path is not None else None
                    ),
                    "result_path": (
                        str(conversion.result_path)
                        if conversion.result_path is not None else None
                    ),
                    "model_metadata_path": (
                        str(conversion.model_metadata_path)
                        if conversion.model_metadata_path is not None else None
                    ),
                    "error_code": conversion.error_code,
                    "error_message": conversion.error_message,
                    "started_at": self._serialize_datetime(conversion.started_at),
                    "finished_at": self._serialize_datetime(conversion.finished_at),
                    "input_expires_at": self._serialize_datetime(
                        conversion.input_expires_at
                    ),
                    "result_expires_at": self._serialize_datetime(
                        conversion.result_expires_at
                    ),
                    "model_metadata_expires_at": self._serialize_datetime(
                        conversion.model_metadata_expires_at
                    ),
                    "expires_at": self._serialize_datetime(conversion.expires_at),
                },
            )

    def get_by_id(self, conversion_id: str) -> Conversion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversions WHERE conversion_id = ?",
                (conversion_id,),
            ).fetchone()

        return self._row_to_conversion(row) if row is not None else None

    def set_model_metadata_path(
        self,
        conversion_id: str,
        metadata_path: Path,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET model_metadata_path = ?, updated_at = ?
                WHERE conversion_id = ? AND status = ?
                """,
                (
                    str(metadata_path),
                    self._serialize_datetime(datetime.now(timezone.utc)),
                    conversion_id,
                    ConversionStatus.PROCESSING.value,
                ),
            )
        return cursor.rowcount > 0

    def mark_processing(
        self,
        conversion_id: str,
        started_at: datetime,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET status = ?, started_at = ?, updated_at = ?
                WHERE conversion_id = ?
                  AND status = ?
                  AND started_at IS NULL
                """,
                (
                    ConversionStatus.PROCESSING.value,
                    self._serialize_datetime(started_at),
                    self._serialize_datetime(started_at),
                    conversion_id,
                    ConversionStatus.PROCESSING.value,
                ),
            )
        return cursor.rowcount > 0

    def mark_ready(
        self,
        conversion_id: str,
        result_path: Path,
        model_metadata_path: Path,
        finished_at: datetime,
        input_expires_at: datetime,
        result_expires_at: datetime,
        model_metadata_expires_at: datetime,
        expires_at: datetime,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET
                    status = ?,
                    result_path = ?,
                    model_metadata_path = ?,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = ?,
                    finished_at = ?,
                    input_expires_at = ?,
                    result_expires_at = ?,
                    model_metadata_expires_at = ?,
                    expires_at = ?
                WHERE conversion_id = ? AND status = ?
                """,
                (
                    ConversionStatus.READY.value,
                    str(result_path),
                    str(model_metadata_path),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(input_expires_at),
                    self._serialize_datetime(result_expires_at),
                    self._serialize_datetime(model_metadata_expires_at),
                    self._serialize_datetime(expires_at),
                    conversion_id,
                    ConversionStatus.PROCESSING.value,
                ),
            )
        return cursor.rowcount > 0

    def mark_failed(
        self,
        conversion_id: str,
        error_code: str,
        error_message: str,
        model_metadata_path: Path | None,
        finished_at: datetime,
        input_expires_at: datetime,
        model_metadata_expires_at: datetime,
        expires_at: datetime,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET
                    status = ?,
                    error_code = ?,
                    error_message = ?,
                    result_path = NULL,
                    result_expires_at = NULL,
                    model_metadata_path = ?,
                    updated_at = ?,
                    finished_at = ?,
                    input_expires_at = ?,
                    model_metadata_expires_at = ?,
                    expires_at = ?
                WHERE conversion_id = ? AND status = ?
                """,
                (
                    ConversionStatus.FAILED.value,
                    error_code,
                    error_message,
                    str(model_metadata_path) if model_metadata_path is not None else None,
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(input_expires_at),
                    self._serialize_datetime(model_metadata_expires_at),
                    self._serialize_datetime(expires_at),
                    conversion_id,
                    ConversionStatus.PROCESSING.value,
                ),
            )
        return cursor.rowcount > 0

    def find_expired_files(self, now: datetime) -> list[Conversion]:
        now_text = self._serialize_datetime(now)
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversions
                WHERE
                    (input_path IS NOT NULL AND input_expires_at IS NOT NULL
                     AND input_expires_at <= ?)
                    OR
                    (result_path IS NOT NULL AND result_expires_at IS NOT NULL
                     AND result_expires_at <= ?)
                    OR
                    (model_metadata_path IS NOT NULL
                     AND model_metadata_expires_at IS NOT NULL
                     AND model_metadata_expires_at <= ?)
                """,
                (now_text, now_text, now_text),
            ).fetchall()
        return [self._row_to_conversion(row) for row in rows]

    def clear_expired_file_paths(
        self,
        conversion_id: str,
        now: datetime,
    ) -> None:
        now_text = self._serialize_datetime(now)
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE conversions
                SET
                    input_path = CASE
                        WHEN input_expires_at IS NOT NULL AND input_expires_at <= ?
                        THEN NULL ELSE input_path END,
                    result_path = CASE
                        WHEN result_expires_at IS NOT NULL AND result_expires_at <= ?
                        THEN NULL ELSE result_path END,
                    model_metadata_path = CASE
                        WHEN model_metadata_expires_at IS NOT NULL
                             AND model_metadata_expires_at <= ?
                        THEN NULL ELSE model_metadata_path END,
                    updated_at = ?
                WHERE conversion_id = ?
                """,
                (now_text, now_text, now_text, now_text, conversion_id),
            )

    def mark_interrupted_as_failed(
        self,
        finished_at: datetime,
        input_expires_at: datetime,
        model_metadata_expires_at: datetime,
        expires_at: datetime,
    ) -> int:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET
                    status = ?,
                    error_code = 'PROCESS_INTERRUPTED',
                    error_message = 'Processing was interrupted by an application restart.',
                    updated_at = ?,
                    finished_at = ?,
                    input_expires_at = CASE
                        WHEN input_path IS NOT NULL THEN ? ELSE input_expires_at END,
                    model_metadata_expires_at = CASE
                        WHEN model_metadata_path IS NOT NULL THEN ?
                        ELSE model_metadata_expires_at END,
                    result_path = NULL,
                    result_expires_at = NULL,
                    expires_at = ?
                WHERE status = ?
                """,
                (
                    ConversionStatus.FAILED.value,
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(input_expires_at),
                    self._serialize_datetime(model_metadata_expires_at),
                    self._serialize_datetime(expires_at),
                    ConversionStatus.PROCESSING.value,
                ),
            )
        return cursor.rowcount

    def find_expired_records(self, now: datetime) -> list[Conversion]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversions
                WHERE expires_at IS NOT NULL
                  AND expires_at <= ?
                  AND input_path IS NULL
                  AND result_path IS NULL
                  AND model_metadata_path IS NULL
                """,
                (self._serialize_datetime(now),),
            ).fetchall()
        return [self._row_to_conversion(row) for row in rows]

    def get_referenced_artifact_paths(self) -> set[Path]:
        """Return every persistent file/directory currently referenced by SQLite."""
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT input_path, result_path, model_metadata_path
                FROM conversions
                """
            ).fetchall()

        return {
            Path(row[column]).resolve()
            for row in rows
            for column in (
                "input_path",
                "result_path",
                "model_metadata_path",
            )
            if row[column] is not None
        }

    def delete_by_id(self, conversion_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversions WHERE conversion_id = ?",
                (conversion_id,),
            )
        return cursor.rowcount > 0
