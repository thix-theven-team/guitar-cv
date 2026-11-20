from pathlib import Path
from typing import BinaryIO

from guitarcv_restapi.models.conversion import Conversion
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
        ... # TODO

    def submit_video(
        self,
        file: BinaryIO,
        content_type: str | None,
    ) -> str:
        ... # TODO

    def _validate_video(
        self,
        file_path: Path,
        content_type: str | None,
    ) -> VideoProbeResult:
        ... # TODO

    def _register_conversion(
        self,
        conversion_id: str,
        input_path: Path,
    ) -> Conversion:
        ... # TODO
