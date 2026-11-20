from dataclasses import dataclass
from pathlib import Path

from typing import Any


@dataclass(frozen=True, slots=True)
class VideoProbeResult:
    format_name: str | None
    duration_seconds: float | None
    video_codec_names: tuple[str, ...]


class FFprobeValidator:
    def __init__(
        self,
        timeout_seconds: float,
        allowed_mime_types: tuple[str, ...],
        executable: str = "ffprobe",
    ) -> None:
        ... # TODO

    def validate_mime_type(
        self,
        content_type: str | None,
    ) -> None:
        ... # TODO

    def probe_video(
        self,
        file_path: Path,
    ) -> VideoProbeResult:
        ... # TODO

    def validate(
        self,
        file_path: Path,
        content_type: str | None,
    ) -> VideoProbeResult:
        ... # TODO