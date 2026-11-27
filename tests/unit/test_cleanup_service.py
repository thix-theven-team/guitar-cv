from datetime import timedelta
from pathlib import Path

from guitarcv_restapi.models.conversion import Conversion, ConversionStatus
from guitarcv_restapi.services.cleanup_service import CleanupService


def test_cleanup_removes_expired_artifacts_then_expired_record(
    repository,
    storage,
    now,
    tmp_path: Path,
) -> None:
    conversion_id = "1" * 32
    upload = storage.upload_path_for(conversion_id)
    result = storage.result_path_for(conversion_id)
    metadata = storage.metadata_path_for(conversion_id)
    upload.write_bytes(b"video")
    result.write_bytes(b"midi")
    metadata.mkdir()
    (metadata / "summary.json").write_text("{}", encoding="utf-8")

    expired = now - timedelta(seconds=1)
    conversion = Conversion(
        conversion_id=conversion_id,
        status=ConversionStatus.READY,
        created_at=now - timedelta(hours=4),
        updated_at=now - timedelta(hours=1),
        input_path=upload,
        result_path=result,
        model_metadata_path=metadata,
        finished_at=now - timedelta(hours=4),
        input_expires_at=expired,
        result_expires_at=expired,
        model_metadata_expires_at=expired,
        expires_at=now + timedelta(seconds=1),
    )
    repository.create(conversion)
    service = CleanupService(repository, storage)

    report = service.run_once(now)

    assert report.input_files_deleted == 1
    assert report.result_files_deleted == 1
    assert report.model_metadata_files_deleted == 1
    assert report.deletion_failures == 0
    assert not upload.exists()
    assert not result.exists()
    assert not metadata.exists()

    remaining = repository.get_by_id(conversion_id)
    assert remaining is not None
    assert remaining.input_path is None
    assert remaining.result_path is None
    assert remaining.model_metadata_path is None

    with database_connection(repository) as connection:
        connection.execute(
            "UPDATE conversions SET expires_at = ? WHERE conversion_id = ?",
            ((now - timedelta(seconds=1)).isoformat(), conversion_id),
        )

    second_report = service.run_once(now)
    assert second_report.conversion_records_deleted == 1
    assert repository.get_by_id(conversion_id) is None


def database_connection(repository):
    return repository.database.connection()


def test_cleanup_retains_database_reference_when_file_deletion_fails(
    repository,
    storage,
    now,
    monkeypatch,
) -> None:
    conversion_id = "2" * 32
    upload = storage.upload_path_for(conversion_id)
    upload.write_bytes(b"video")
    expired = now - timedelta(seconds=1)
    repository.create(
        Conversion(
            conversion_id=conversion_id,
            status=ConversionStatus.FAILED,
            created_at=now - timedelta(hours=1),
            updated_at=now,
            input_path=upload,
            input_expires_at=expired,
            expires_at=now + timedelta(hours=1),
        )
    )

    def fail_delete(path):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(storage, "delete_file", fail_delete)
    report = CleanupService(repository, storage).run_once(now)

    assert report.deletion_failures == 1
    loaded = repository.get_by_id(conversion_id)
    assert loaded is not None
    assert loaded.input_path == upload


def test_cleanup_is_safe_when_expired_file_is_already_missing(
    repository,
    storage,
    now,
) -> None:
    conversion_id = "3" * 32
    expired = now - timedelta(seconds=1)
    missing_path = storage.upload_path_for(conversion_id)
    repository.create(
        Conversion(
            conversion_id=conversion_id,
            status=ConversionStatus.FAILED,
            created_at=now - timedelta(hours=1),
            updated_at=now,
            input_path=missing_path,
            input_expires_at=expired,
            expires_at=now + timedelta(hours=1),
        )
    )

    report = CleanupService(repository, storage).run_once(now)

    assert report.deletion_failures == 0
    loaded = repository.get_by_id(conversion_id)
    assert loaded is not None
    assert loaded.input_path is None


def test_startup_orphan_pruning_removes_unreferenced_artifacts(
    repository,
    storage,
    now,
) -> None:
    conversion_id = "4" * 32
    referenced_upload = storage.upload_path_for(conversion_id)
    referenced_upload.write_bytes(b"video")

    orphan_upload = storage.upload_path_for("5" * 32)
    orphan_upload.write_bytes(b"orphan video")
    orphan_result = storage.result_path_for("6" * 32)
    orphan_result.write_bytes(b"orphan midi")
    orphan_metadata = storage.metadata_path_for("7" * 32)
    orphan_metadata.mkdir()
    (orphan_metadata / "summary.json").write_text("{}", encoding="utf-8")

    repository.create(
        Conversion(
            conversion_id=conversion_id,
            status=ConversionStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            input_path=referenced_upload,
        )
    )

    deleted, failures = CleanupService(
        repository, storage
    ).prune_orphaned_artifacts()

    assert deleted == 3
    assert failures == 0
    assert referenced_upload.is_file()
    assert not orphan_upload.exists()
    assert not orphan_result.exists()
    assert not orphan_metadata.exists()
