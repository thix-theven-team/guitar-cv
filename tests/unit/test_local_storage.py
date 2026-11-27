from io import BytesIO
from pathlib import Path

import pytest


def test_ensure_directories_creates_all_configured_storage_roots(storage) -> None:
    assert storage.upload_dir.is_dir()
    assert storage.result_dir.is_dir()
    assert storage.metadata_dir.is_dir()
    assert storage.temp_dir.is_dir()


def test_save_upload_uses_generated_conversion_id_and_atomic_staging(
    storage,
) -> None:
    conversion_id = "0123456789abcdef0123456789abcdef"

    saved_path = storage.save_upload(
        file=BytesIO(b"video-bytes"),
        conversion_id=conversion_id,
    )

    assert saved_path == storage.upload_path_for(conversion_id)
    assert saved_path.name == conversion_id + ".upload"
    assert saved_path.read_bytes() == b"video-bytes"
    assert not list(storage.upload_dir.glob("*.part"))
    assert not list(storage.upload_dir.glob(".*.part"))
    assert not (storage.temp_dir / (conversion_id + ".upload.part")).exists()


def test_storage_builds_deterministic_conversion_paths(storage) -> None:
    conversion_id = "f" * 32

    assert storage.upload_path_for(conversion_id).parent == storage.upload_dir
    assert storage.result_path_for(conversion_id).parent == storage.result_dir
    assert storage.metadata_path_for(conversion_id).parent == storage.metadata_dir
    assert storage.temporary_path_for(conversion_id).parent == storage.temp_dir


def test_storage_rejects_malformed_conversion_ids(storage) -> None:
    with pytest.raises(ValueError):
        storage.upload_path_for("../../outside")


def test_delete_file_and_directory_are_idempotent(storage, tmp_path: Path) -> None:
    conversion_id = "a" * 32
    upload = storage.upload_path_for(conversion_id)
    upload.write_bytes(b"video")
    metadata = storage.metadata_path_for(conversion_id)
    metadata.mkdir()
    (metadata / "summary.json").write_text("{}", encoding="utf-8")

    assert storage.delete_file(upload)
    assert storage.delete_file(upload)
    assert storage.delete_directory(metadata)
    assert storage.delete_directory(metadata)


def test_storage_refuses_paths_outside_managed_roots(storage, tmp_path) -> None:
    outside = tmp_path / "not-managed.txt"
    outside.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="outside application storage"):
        storage.delete_file(outside)

    assert outside.read_text(encoding="utf-8") == "keep"


def test_clear_temporary_storage_removes_abandoned_files_and_directories(
    storage,
) -> None:
    (storage.temp_dir / "partial.upload.part").write_bytes(b"partial")
    abandoned = storage.temp_dir / ("b" * 32)
    abandoned.mkdir()
    (abandoned / "annotated.avi").write_bytes(b"temporary")

    removed = storage.clear_temporary_storage()

    assert removed == 2
    assert list(storage.temp_dir.iterdir()) == []


def test_publish_file_atomically_copies_between_managed_roots(storage) -> None:
    conversion_id = "b" * 32
    source = storage.temporary_path_for(conversion_id) / "output.mid"
    destination = storage.result_path_for(conversion_id)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"complete-midi")

    published = storage.publish_file(source, destination)

    assert published == destination
    assert destination.read_bytes() == b"complete-midi"
    assert source.is_file()
    assert not list(storage.result_dir.glob("*.part"))
    assert not list(storage.result_dir.glob(".*.part"))
