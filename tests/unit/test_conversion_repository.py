from datetime import datetime, timedelta, timezone
from pathlib import Path

from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.database.schema import initialize_database
from guitarcv_restapi.models.conversion import Conversion, ConversionStatus
from guitarcv_restapi.repositories.conversion_repository import ConversionRepository


def make_conversion(
    conversion_id: str,
    now: datetime,
    input_path: Path | None = None,
) -> Conversion:
    return Conversion(
        conversion_id=conversion_id,
        status=ConversionStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        input_path=input_path,
    )


def test_create_and_get_conversion_round_trip(repository, now, tmp_path) -> None:
    source = make_conversion(
        "0123456789abcdef0123456789abcdef",
        now,
        tmp_path / "uploads" / "input.upload",
    )

    repository.create(source)
    loaded = repository.get_by_id(source.conversion_id)

    assert loaded is not None
    assert loaded.conversion_id == source.conversion_id
    assert loaded.status is ConversionStatus.PROCESSING
    assert loaded.created_at == now
    assert loaded.updated_at == now
    assert loaded.input_path == source.input_path
    assert loaded.result_path is None


def test_get_by_id_returns_none_for_unknown_id(repository) -> None:
    assert repository.get_by_id("missing") is None


def test_mark_ready_persists_result_and_expiration_fields(
    repository,
    now,
    tmp_path,
) -> None:
    conversion = make_conversion("a" * 32, now, tmp_path / "input.upload")
    repository.create(conversion)

    finished = now + timedelta(minutes=2)
    result_path = tmp_path / "results" / "a.mid"
    metadata_path = tmp_path / "metadata" / conversion.conversion_id
    assert repository.mark_ready(
        conversion_id=conversion.conversion_id,
        result_path=result_path,
        model_metadata_path=metadata_path,
        finished_at=finished,
        input_expires_at=finished + timedelta(hours=1),
        result_expires_at=finished + timedelta(hours=1),
        model_metadata_expires_at=finished + timedelta(hours=3),
        expires_at=finished + timedelta(hours=3),
    )

    loaded = repository.get_by_id(conversion.conversion_id)
    assert loaded is not None
    assert loaded.status is ConversionStatus.READY
    assert loaded.result_path == result_path
    assert loaded.model_metadata_path == metadata_path
    assert loaded.finished_at == finished
    assert loaded.result_expires_at == finished + timedelta(hours=1)


def test_mark_failed_persists_safe_error_and_metadata(
    repository,
    now,
    tmp_path,
) -> None:
    conversion = make_conversion("b" * 32, now, tmp_path / "input.upload")
    repository.create(conversion)
    finished = now + timedelta(minutes=1)
    metadata = tmp_path / "metadata" / conversion.conversion_id

    assert repository.mark_failed(
        conversion_id=conversion.conversion_id,
        error_code="PROCESSING_FAILED",
        error_message="The video could not be converted.",
        model_metadata_path=metadata,
        finished_at=finished,
        input_expires_at=finished + timedelta(hours=1),
        model_metadata_expires_at=finished + timedelta(hours=3),
        expires_at=finished + timedelta(hours=3),
    )

    loaded = repository.get_by_id(conversion.conversion_id)
    assert loaded is not None
    assert loaded.status is ConversionStatus.FAILED
    assert loaded.error_code == "PROCESSING_FAILED"
    assert loaded.error_message == "The video could not be converted."
    assert loaded.result_path is None


def test_mark_interrupted_as_failed_updates_only_processing_records(
    repository,
    now,
    tmp_path,
) -> None:
    conversion = make_conversion("c" * 32, now, tmp_path / "input.upload")
    repository.create(conversion)
    finished = now + timedelta(minutes=10)

    updated = repository.mark_interrupted_as_failed(
        finished_at=finished,
        input_expires_at=finished + timedelta(hours=1),
        model_metadata_expires_at=finished + timedelta(hours=3),
        expires_at=finished + timedelta(hours=3),
    )

    loaded = repository.get_by_id(conversion.conversion_id)
    assert updated == 1
    assert loaded is not None
    assert loaded.status is ConversionStatus.FAILED
    assert loaded.error_code == "PROCESS_INTERRUPTED"
    assert loaded.finished_at == finished


def test_expired_artifact_references_can_be_cleared_and_record_deleted(
    repository,
    now,
    tmp_path,
) -> None:
    conversion = make_conversion("d" * 32, now, tmp_path / "input.upload")
    repository.create(conversion)
    expired = now - timedelta(seconds=1)
    result_path = tmp_path / "result.mid"
    metadata_path = tmp_path / "metadata"
    assert repository.mark_ready(
        conversion_id=conversion.conversion_id,
        result_path=result_path,
        model_metadata_path=metadata_path,
        finished_at=now,
        input_expires_at=expired,
        result_expires_at=expired,
        model_metadata_expires_at=expired,
        expires_at=expired,
    )

    expired_files = repository.find_expired_files(now)
    assert [item.conversion_id for item in expired_files] == [conversion.conversion_id]

    repository.clear_expired_file_paths(conversion.conversion_id, now)
    loaded = repository.get_by_id(conversion.conversion_id)
    assert loaded is not None
    assert loaded.input_path is None
    assert loaded.result_path is None
    assert loaded.model_metadata_path is None

    expired_records = repository.find_expired_records(now)
    assert [item.conversion_id for item in expired_records] == [conversion.conversion_id]
    assert repository.delete_by_id(conversion.conversion_id)
    assert repository.get_by_id(conversion.conversion_id) is None


def test_schema_initialization_migrates_legacy_error_column(tmp_path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    with database.connection() as connection:
        connection.execute(
            """CREATE TABLE conversions (
                conversion_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                result_path TEXT,
                error TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO conversions VALUES (?, ?, ?, ?, ?)",
            (
                "e" * 32,
                "failed",
                datetime.now(timezone.utc).isoformat(),
                None,
                "Legacy failure description",
            ),
        )

    initialize_database(database)
    loaded = ConversionRepository(database).get_by_id("e" * 32)

    assert loaded is not None
    assert loaded.status is ConversionStatus.FAILED
    assert loaded.error_message == "Legacy failure description"
    assert loaded.updated_at == loaded.created_at


def test_mark_processing_only_claims_a_conversion_once(repository, now) -> None:
    conversion = make_conversion("f" * 32, now)
    repository.create(conversion)

    assert repository.mark_processing(conversion.conversion_id, now)
    assert not repository.mark_processing(
        conversion.conversion_id, now + timedelta(seconds=1)
    )


def test_legacy_naive_datetimes_are_interpreted_as_utc(repository, tmp_path) -> None:
    naive = datetime(2026, 1, 2, 3, 4, 5)
    conversion = make_conversion("9" * 32, naive)
    repository.create(conversion)

    loaded = repository.get_by_id(conversion.conversion_id)

    assert loaded is not None
    assert loaded.created_at.tzinfo is timezone.utc
    assert loaded.updated_at.tzinfo is timezone.utc


def test_schema_initialization_backfills_legacy_retention_deadlines(tmp_path) -> None:
    from dataclasses import replace

    from guitarcv_restapi.core.config import settings

    database = Database(tmp_path / "legacy-retention.sqlite3")
    completed_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    upload_path = tmp_path / "legacy-upload.mp4"
    result_path = tmp_path / "legacy-result.mid"
    metadata_path = tmp_path / "legacy-metadata"

    with database.connection() as connection:
        connection.execute(
            """CREATE TABLE conversions (
                conversion_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                input_path TEXT,
                result_path TEXT,
                model_metadata_path TEXT,
                error TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO conversions (
                conversion_id, status, created_at, updated_at,
                input_path, result_path, model_metadata_path, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "d" * 32,
                "ready",
                completed_at.isoformat(),
                completed_at.isoformat(),
                str(upload_path),
                str(result_path),
                str(metadata_path),
                None,
            ),
        )

    configuration = replace(
        settings,
        input_retention_seconds=60,
        result_retention_seconds=120,
        model_metadata_retention_seconds=180,
        conversion_metadata_retention_seconds=240,
    )
    initialize_database(database, configuration)

    conversion = ConversionRepository(database).get_by_id("d" * 32)
    assert conversion is not None
    assert conversion.input_expires_at == completed_at + timedelta(seconds=60)
    assert conversion.result_expires_at == completed_at + timedelta(seconds=120)
    assert conversion.model_metadata_expires_at == completed_at + timedelta(seconds=180)
    assert conversion.expires_at == completed_at + timedelta(seconds=240)


def test_mark_failed_updates_conversion_and_retention_fields(
    repository,
    now,
    tmp_path,
) -> None:
    conversion = make_conversion("e" * 32, now, tmp_path / "input.upload")
    repository.create(conversion)
    finished = now + timedelta(minutes=1)
    metadata = tmp_path / "metadata" / conversion.conversion_id

    assert repository.mark_failed(
        conversion_id=conversion.conversion_id,
        error_code="PROCESSING_FAILED",
        error_message="Safe client-facing failure message.",
        model_metadata_path=metadata,
        finished_at=finished,
        input_expires_at=finished + timedelta(hours=1),
        model_metadata_expires_at=finished + timedelta(hours=3),
        expires_at=finished + timedelta(hours=3),
    )

    loaded = repository.get_by_id(conversion.conversion_id)
    assert loaded is not None
    assert loaded.status is ConversionStatus.FAILED
    assert loaded.error_code == "PROCESSING_FAILED"
    assert loaded.error_message == "Safe client-facing failure message."
    assert loaded.model_metadata_path == metadata
    assert loaded.result_path is None
