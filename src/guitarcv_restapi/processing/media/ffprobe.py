from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from guitarcv_restapi.core.exceptions import ApiException


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
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not executable.strip():
            raise ValueError("executable must not be empty")

        normalized_mime_types = tuple(
            mime_type.strip().lower()
            for mime_type in allowed_mime_types
            if mime_type.strip()
        )
        if not normalized_mime_types:
            raise ValueError("allowed_mime_types must not be empty")

        self.timeout_seconds = timeout_seconds
        self.allowed_mime_types = normalized_mime_types
        self.executable = executable

    @staticmethod
    def _normalize_mime_type(content_type: str | None) -> str | None:
        if content_type is None:
            return None

        base_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        return base_type or None

    @staticmethod
    def _parse_duration(raw_duration: Any) -> float | None:
        if raw_duration is None or raw_duration == "N/A":
            return None

        try:
            duration = float(raw_duration)
        except (TypeError, ValueError) as exc:
            raise ApiException(
                status_code=400,
                code="INVALID_VIDEO",
                message="Video duration metadata is invalid.",
            ) from exc

        return duration

    def validate_mime_type(
        self,
        content_type: str | None,
    ) -> None:
        normalized = self._normalize_mime_type(content_type)
        if normalized is None:
            raise ApiException(
                status_code=415,
                code="MISSING_CONTENT_TYPE",
                message="Video Content-Type header is missing.",
            )

        if normalized not in self.allowed_mime_types:
            allowed = ", ".join(self.allowed_mime_types)
            raise ApiException(
                status_code=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                message=(
                    f"Unsupported video media type '{normalized}'. "
                    f"Allowed types: {allowed}."
                ),
            )

    def probe_video(
        self,
        file_path: Path,
    ) -> VideoProbeResult:
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Video file not found: {file_path}")

        if file_path.stat().st_size == 0:
            raise ApiException(
                status_code=400,
                code="EMPTY_VIDEO",
                message="Uploaded video file is empty.",
            )

        command = [
            self.executable,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApiException(
                status_code=504,
                code="VIDEO_VALIDATION_TIMEOUT",
                message="Video validation timed out.",
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Failed to execute ffprobe '{self.executable}': {exc}"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() or "unknown ffprobe error"
            raise ApiException(
                status_code=400,
                code="INVALID_VIDEO",
                message=f"Invalid or corrupted video file: {stderr}",
            )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ApiException(
                status_code=500,
                code="INVALID_FFPROBE_OUTPUT",
                message="Failed to parse video metadata from ffprobe.",
            ) from exc

        format_info = payload.get("format") or {}
        streams = payload.get("streams") or []

        format_name = format_info.get("format_name")
        duration_seconds = self._parse_duration(format_info.get("duration"))
        if duration_seconds is not None and duration_seconds <= 0:
            raise ApiException(
                status_code=400,
                code="INVALID_VIDEO_DURATION",
                message="Video duration must be greater than zero.",
            )

        video_codec_names = tuple(
            str(stream.get("codec_name") or "unknown")
            for stream in streams
            if isinstance(stream, dict)
            and stream.get("codec_type") == "video"
            and not (
                isinstance(stream.get("disposition"), dict)
                and stream["disposition"].get("attached_pic") == 1
            )
        )
        if not video_codec_names:
            raise ApiException(
                status_code=415,
                code="NO_VIDEO_STREAM",
                message="Uploaded file does not contain a video stream.",
            )

        return VideoProbeResult(
            format_name=format_name,
            duration_seconds=duration_seconds,
            video_codec_names=video_codec_names,
        )

    def validate(
        self,
        file_path: Path,
        content_type: str | None,
    ) -> VideoProbeResult:
        self.validate_mime_type(content_type)
        return self.probe_video(file_path)
