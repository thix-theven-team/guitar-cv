import logging
import sqlite3

from datetime import datetime, timedelta, timezone

from guitarcv_restapi.core.config import Settings, settings
from guitarcv_restapi.database.connection import Database


logger = logging.getLogger(__name__)


CREATE_CONVERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversions (
    conversion_id TEXT PRIMARY KEY NOT NULL,

    status TEXT NOT NULL CHECK (
        status IN ('processing', 'ready', 'failed')
    ),

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    input_path TEXT,
    result_path TEXT,
    model_metadata_path TEXT,

    error_code TEXT,
    error_message TEXT,

    started_at TEXT,
    finished_at TEXT,

    input_expires_at TEXT,
    result_expires_at TEXT,
    model_metadata_expires_at TEXT,
    expires_at TEXT
);
"""

# additive migrations for databases created by earlier development snapshots
# existing data is retained, new nullable metadata columns are added
_LEGACY_COLUMN_ADDITIONS = {
    "status": "TEXT NOT NULL DEFAULT 'failed'",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "input_path": "TEXT",
    "result_path": "TEXT",
    "model_metadata_path": "TEXT",
    "error_code": "TEXT",
    "error_message": "TEXT",
    "started_at": "TEXT",
    "finished_at": "TEXT",
    "input_expires_at": "TEXT",
    "result_expires_at": "TEXT",
    "model_metadata_expires_at": "TEXT",
    "expires_at": "TEXT",
}

CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_conversions_status "
    "ON conversions(status);",
    "CREATE INDEX IF NOT EXISTS idx_conversions_expires_at "
    "ON conversions(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_conversions_input_expires_at "
    "ON conversions(input_expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_conversions_result_expires_at "
    "ON conversions(result_expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_conversions_metadata_expires_at "
    "ON conversions(model_metadata_expires_at);",
)


def _parse_legacy_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _backfill_legacy_retention(
    connection: sqlite3.Connection,
    configuration: Settings,
) -> int:
    rows = connection.execute(
        """
        SELECT
            conversion_id, status, created_at, updated_at, finished_at,
            input_path, result_path, model_metadata_path,
            input_expires_at, result_expires_at,
            model_metadata_expires_at, expires_at
        FROM conversions
        WHERE status IN ('ready', 'failed')
          AND (
              expires_at IS NULL
              OR (input_path IS NOT NULL AND input_expires_at IS NULL)
              OR (result_path IS NOT NULL AND result_expires_at IS NULL)
              OR (
                  model_metadata_path IS NOT NULL
                  AND model_metadata_expires_at IS NULL
              )
          )
        """
    ).fetchall()

    migrated = 0
    for row in rows:
        base_time = (
            _parse_legacy_timestamp(row["finished_at"])
            or _parse_legacy_timestamp(row["updated_at"])
            or _parse_legacy_timestamp(row["created_at"])
        )
        if base_time is None:
            logger.warning(
                "Could not backfill retention for conversion %s: no valid timestamp",
                row["conversion_id"],
            )
            continue

        updates: dict[str, str] = {}
        if row["finished_at"] is None:
            updates["finished_at"] = base_time.isoformat()
        if row["input_path"] is not None and row["input_expires_at"] is None:
            updates["input_expires_at"] = (
                base_time
                + timedelta(seconds=configuration.input_retention_seconds)
            ).isoformat()
        if row["result_path"] is not None and row["result_expires_at"] is None:
            updates["result_expires_at"] = (
                base_time
                + timedelta(seconds=configuration.result_retention_seconds)
            ).isoformat()
        if (
            row["model_metadata_path"] is not None
            and row["model_metadata_expires_at"] is None
        ):
            updates["model_metadata_expires_at"] = (
                base_time
                + timedelta(
                    seconds=configuration.model_metadata_retention_seconds
                )
            ).isoformat()
        if row["expires_at"] is None:
            updates["expires_at"] = (
                base_time
                + timedelta(
                    seconds=configuration.conversion_metadata_retention_seconds
                )
            ).isoformat()

        if not updates:
            continue

        assignments = ", ".join(
            "%s = ?" % column_name for column_name in updates
        )
        connection.execute(
            "UPDATE conversions SET %s WHERE conversion_id = ?" % assignments,
            (*updates.values(), row["conversion_id"]),
        )
        migrated += 1

    if migrated:
        logger.info(
            "Backfilled retention deadlines for %d legacy conversion(s)",
            migrated,
        )
    return migrated


def initialize_database(
    database: Database,
    configuration: Settings = settings,
) -> None:
    with database.connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(CREATE_CONVERSIONS_TABLE)

        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(conversions)")
        }
        if "conversion_id" not in existing_columns:
            raise RuntimeError(
                "Existing conversions table has no conversion_id column; "
                "it cannot be migrated automatically."
            )

        for column_name, declaration in _LEGACY_COLUMN_ADDITIONS.items():
            if column_name not in existing_columns:
                connection.execute(
                    "ALTER TABLE conversions ADD COLUMN %s %s"
                    % (column_name, declaration)
                )

        if "error" in existing_columns:
            connection.execute(
                "UPDATE conversions SET error_message = error "
                "WHERE error_message IS NULL AND error IS NOT NULL"
            )

        connection.execute(
            "UPDATE conversions SET updated_at = created_at "
            "WHERE updated_at IS NULL AND created_at IS NOT NULL"
        )

        _backfill_legacy_retention(connection, configuration)

        for query in CREATE_INDEXES:
            connection.execute(query)
