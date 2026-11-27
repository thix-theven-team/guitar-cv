from datetime import datetime, timezone
from pathlib import Path

from guitarcv_restapi.models.conversion import Conversion, ConversionStatus
from guitarcv_restapi.processing import tasks


class FakePipeline:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def process(
        self,
        input_video: Path,
        output_midi: Path,
        metadata_dir: Path,
        temporary_dir: Path,
    ) -> Path:
        if self.fail:
            raise RuntimeError("simulated ML failure")
        output_midi.parent.mkdir(parents=True, exist_ok=True)
        output_midi.write_bytes(b"MThd\x00\x00")
        return output_midi


def prepare_task_environment(
    monkeypatch, repository, storage, conversion_id: str, pipeline: FakePipeline
) -> Path:
    input_path = storage.upload_path_for(conversion_id)
    input_path.write_bytes(b"video")
    now = datetime.now(timezone.utc)
    repository.create(
        Conversion(
            conversion_id=conversion_id,
            status=ConversionStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            input_path=input_path,
        )
    )

    monkeypatch.setattr(tasks, "Database", lambda _path: repository.database)
    monkeypatch.setattr(tasks, "LocalStorage", lambda **_kwargs: storage)
    monkeypatch.setattr(tasks, "get_conversion_pipeline", lambda: pipeline)
    return input_path


def test_background_task_publishes_result_and_marks_ready(
    monkeypatch, repository, storage
) -> None:
    conversion_id = "a" * 32
    prepare_task_environment(
        monkeypatch, repository, storage, conversion_id, FakePipeline()
    )

    tasks.process_conversion_task(conversion_id)

    conversion = repository.get_by_id(conversion_id)
    result_path = storage.result_path_for(conversion_id)
    assert conversion is not None
    assert conversion.status is ConversionStatus.READY
    assert conversion.result_path == result_path
    assert result_path.is_file()
    assert not storage.temporary_path_for(conversion_id).exists()


def test_background_task_records_failure_and_cleans_temporary_files(
    monkeypatch, repository, storage
) -> None:
    conversion_id = "b" * 32
    prepare_task_environment(
        monkeypatch, repository, storage, conversion_id, FakePipeline(fail=True)
    )

    tasks.process_conversion_task(conversion_id)

    conversion = repository.get_by_id(conversion_id)
    assert conversion is not None
    assert conversion.status is ConversionStatus.FAILED
    assert conversion.error_code == "PROCESSING_FAILED"
    assert not storage.temporary_path_for(conversion_id).exists()
    assert not storage.result_path_for(conversion_id).exists()
