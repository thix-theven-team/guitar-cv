from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
import uuid

from guitarcv_restapi.models.conversion import Conversion, ConversionStatus
from guitarcv_restapi.processing.media.ffprobe import (
    FFprobeValidator,
    VideoProbeResult,
)
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)
from guitarcv_restapi.storage.local_storage import LocalStorage


class SubmissionService:
    def __init__(
        self,
        repository: ConversionRepository,
        storage: LocalStorage,
        ffprobe: FFprobeValidator,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.ffprobe = ffprobe

    def submit_video(
        self,
        file: BinaryIO,
        content_type: str | None,
    ) -> str:
        # Reject unsupported MIME types before writing the upload to disk.
        self.ffprobe.validate_mime_type(content_type)

        conversion_id = uuid.uuid4().hex
        input_path = self.storage.save_upload(
            file=file,
            conversion_id=conversion_id,
        )

        try:
            self._validate_video(
                file_path=input_path,
                content_type=content_type,
            )
            self._register_conversion(
                conversion_id=conversion_id,
                input_path=input_path,
            )
        except Exception:
            self.storage.delete_file(input_path)
            raise

        return conversion_id

    def _validate_video(
        self,
        file_path: Path,
        content_type: str | None,
    ) -> VideoProbeResult:
        return self.ffprobe.validate(
            file_path=file_path,
            content_type=content_type,
        )

    def _register_conversion(
        self,
        conversion_id: str,
        input_path: Path,
    ) -> Conversion:
        now = datetime.now(timezone.utc)
        conversion = Conversion(
            conversion_id=conversion_id,
            status=ConversionStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            input_path=input_path,
        )
        self.repository.create(conversion)
        return conversion
