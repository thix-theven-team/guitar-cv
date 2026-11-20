from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "GuitarCV REST API"
    environment: str = "development"
    debug: bool = False

    data_dir: Path = Path("/app/data")

    allowed_video_mime_types: tuple[str, ...] = (
        "video/mp4",
        "video/webm",
        "video/quicktime",
    )

    ffprobe_timeout_seconds: float = 5.0

    normalize_videos: bool = False
    normalized_video_extension: str = ".mp4"
    ffmpeg_timeout_seconds: float = 120.0

    cleanup_interval_seconds: int = 300

    input_retention_seconds: int = 3600
    result_retention_seconds: int = 3600
    model_metadata_retention_seconds: int = 10800
    conversion_metadata_retention_seconds: int = 10800

    @property
    def database_path(self) -> Path:
        return self.data_dir / "conversions.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def result_dir(self) -> Path:
        return self.data_dir / "results"

    @property
    def metadata_dir(self) -> Path:
        return self.data_dir / "metadata"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    ... # TODO
