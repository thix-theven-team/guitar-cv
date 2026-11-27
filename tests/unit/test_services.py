from io import BytesIO
from pathlib import Path

import pytest

from guitarcv_restapi.models.conversion import ConversionStatus
from guitarcv_restapi.processing.media.ffprobe import VideoProbeResult
from guitarcv_restapi.services.conversion_service import ConversionService
from guitarcv_restapi.services.submission_service import SubmissionService


class FakeFFprobe:
    def __init__(self, fail_validation: bool = False) -> None:
        self.fail_validation = fail_validation

    def validate_mime_type(self, content_type: str | None) -> None:
        if content_type != "video/mp4":
            raise ValueError("unsupported MIME type")

    def validate(
        self,
        file_path: Path,
        content_type: str | None,
    ) -> VideoProbeResult:
        if self.fail_validation:
            raise ValueError("invalid video")
        assert file_path.is_file()
        return VideoProbeResult("mov,mp4", 1.0, ("h264",))


def test_submission_service_saves_valid_upload_and_registers_conversion(
    repository,
    storage,
) -> None:
    service = SubmissionService(repository, storage, FakeFFprobe())

    conversion_id = service.submit_video(
        file=BytesIO(b"fake video bytes"),
        content_type="video/mp4",
    )

    conversion = repository.get_by_id(conversion_id)
    assert conversion is not None
    assert conversion.status is ConversionStatus.PROCESSING
    assert conversion.input_path is not None
    assert conversion.input_path.is_file()


def test_submission_service_removes_saved_upload_if_validation_fails(
    repository,
    storage,
) -> None:
    service = SubmissionService(
        repository,
        storage,
        FakeFFprobe(fail_validation=True),
    )

    with pytest.raises(ValueError, match="invalid video"):
        service.submit_video(
            file=BytesIO(b"not a video"),
            content_type="video/mp4",
        )

    assert list(storage.upload_dir.iterdir()) == []


def test_conversion_service_delegates_lookup_to_repository(
    repository,
    now,
) -> None:
    from guitarcv_restapi.models.conversion import Conversion

    conversion = Conversion(
        conversion_id="4" * 32,
        status=ConversionStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        input_path=None,
    )
    repository.create(conversion)

    result = ConversionService(repository).get_conversion(conversion.conversion_id)

    assert result is not None
    assert result.conversion_id == conversion.conversion_id
    assert ConversionService(repository).get_conversion("missing") is None
