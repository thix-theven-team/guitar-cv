from pathlib import Path


class FFmpegProcessor:
    def __init__(
        self,
        timeout_seconds: float,
        executable: str = "ffmpeg",
    ) -> None:
        ... #TODO

    def normalize_video(
        self,
        input_path: Path,
        output_path: Path,
        target_format: str = "mp4",
    ) -> Path:
        ... #TODO
