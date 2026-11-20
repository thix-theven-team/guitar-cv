import sqlite3

from datetime import datetime
from pathlib import Path

from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.models.conversion import (
    Conversion,
    ConversionStatus,
)


class ConversionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _serialize_datetime(
        value: datetime | None,
    ) -> str | None:
        if value is None:
            return None

        return value.isoformat()

    @staticmethod
    def _parse_datetime(
        value: str | None,
    ) -> datetime | None:
        if value is None:
            return None

        return datetime.fromisoformat(value)

    @classmethod
    def _row_to_conversion(
        cls,
        row: sqlite3.Row,
    ) -> Conversion:
        return Conversion(
            conversion_id=row["conversion_id"],
            status=ConversionStatus(row["status"]),
            created_at=cls._parse_datetime(row["created_at"]),
            updated_at=cls._parse_datetime(row["updated_at"]),
            input_path=Path(row["input_path"]),
            result_path=(
                Path(row["result_path"])
                if row["result_path"] is not None
                else None
            ),
            error_code=row["error_code"],
            error_message=row["error_message"],
            started_at=cls._parse_datetime(row["started_at"]),
            finished_at=cls._parse_datetime(row["finished_at"]),
            expires_at=cls._parse_datetime(row["expires_at"]),
        )

    def create(
        self,
        conversion: Conversion,
    ) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO conversions (
                    conversion_id,
                    status,
                    created_at,
                    updated_at,
                    input_path,
                    result_path,
                    error_code,
                    error_message,
                    started_at,
                    finished_at,
                    expires_at
                )
                VALUES (
                    :conversion_id,
                    :status,
                    :created_at,
                    :updated_at,
                    :input_path,
                    :result_path,
                    :error_code,
                    :error_message,
                    :started_at,
                    :finished_at,
                    :expires_at
                )
                """,
                {
                    "conversion_id": conversion.conversion_id,
                    "status": conversion.status.value,
                    "created_at": self._serialize_datetime(
                        conversion.created_at
                    ),
                    "updated_at": self._serialize_datetime(
                        conversion.updated_at
                    ),
                    "input_path": str(conversion.input_path),
                    "result_path": (
                        str(conversion.result_path)
                        if conversion.result_path is not None
                        else None
                    ),
                    "error_code": conversion.error_code,
                    "error_message": conversion.error_message,
                    "started_at": self._serialize_datetime(
                        conversion.started_at
                    ),
                    "finished_at": self._serialize_datetime(
                        conversion.finished_at
                    ),
                    "expires_at": self._serialize_datetime(
                        conversion.expires_at
                    ),
                },
            )

    def get_by_id(
        self,
        conversion_id: str,
    ) -> Conversion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM conversions
                WHERE conversion_id = ?
                """,
                (conversion_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_conversion(row)

    def mark_processing(
        self,
        conversion_id: str,
        started_at: datetime,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET
                    status = ?,
                    started_at = ?,
                    updated_at = ?
                WHERE conversion_id = ?
                """,
                (
                    ConversionStatus.PROCESSING.value,
                    self._serialize_datetime(started_at),
                    self._serialize_datetime(started_at),
                    conversion_id,
                ),
            )

        return cursor.rowcount > 0

    def mark_ready(
        self,
        conversion_id: str,
        result_path: Path,
        finished_at: datetime,
        expires_at: datetime,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversions
                SET
                    status = ?,
                    result_path = ?,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = ?,
                    finished_at = ?,
                    expires_at = ?
                WHERE conversion_id = ?
                """,
                (
                    ConversionStatus.READY.value,
                    str(result_path),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(expires_at),
                    conversion_id,
                ),
            )

        return cursor.rowcount > 0

    def mark_failed(
        self,
        conversion_id: str,
        error_code: str,
        error_message: str,
        finished_at: datetime,
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
                    updated_at = ?,
                    finished_at = ?,
                    expires_at = ?
                WHERE conversion_id = ?
                """,
                (
                    ConversionStatus.FAILED.value,
                    error_code,
                    error_message,
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(finished_at),
                    self._serialize_datetime(expires_at),
                    conversion_id,
                ),
            )

        return cursor.rowcount > 0

    def find_expired(
        self,
        now: datetime,
    ) -> list[Conversion]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM conversions
                WHERE expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (self._serialize_datetime(now),),
            ).fetchall()

        return [
            self._row_to_conversion(row)
            for row in rows
        ]

    def delete_by_id(
        self,
        conversion_id: str,
    ) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM conversions
                WHERE conversion_id = ?
                """,
                (conversion_id,),
            )

        return cursor.rowcount > 0

    def find_expired_files(
        self,
        now: datetime,
    ) -> list[Conversion]:
        ... # TODO


    def clear_expired_file_paths(
        self,
        conversion_id: str,
        now: datetime,
    ) -> None:
        ... # TODO


    def mark_interrupted_as_failed(
        self,
        finished_at: datetime,
        expires_at: datetime,
    ) -> int:
        ... # TODO


    def find_expired_records(
        self,
        now: datetime,
    ) -> list[Conversion]:
        ... # TODO
