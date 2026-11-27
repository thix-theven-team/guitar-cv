import json
import os

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# config.json is located in the repository root in local development and at
# /app/config.json in the Docker image
ROOT_PATH = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class MLPipelineSettings:
    device: str

    hand_imgsz: int
    pose_imgsz: int

    hand_conf: float
    pose_conf: float
    kp_conf: float
    cls_conf: float

    hand_pad: float
    pose_stride: int
    cls_period_sec: float
    cls_max_samples: int

    first_wire_is_nut: bool
    nut_side_fallback: str

    rect_h: int
    strings_6: tuple[int, ...]
    strings_4: tuple[int, ...]

    v_margin: float
    smooth_win: int
    min_stable_frames: int

    show_windows: bool
    show_crop_window: bool

    fingertips: dict[str, int]
    press_fingers: tuple[str, ...]
    finger_colors: dict[str, tuple[int, int, int]]

    tuning: dict[str, dict[str, int]]
    note_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    debug: bool
    create_debug_artifacts: bool

    data_dir: Path
    sqlite_path: Path
    upload_dir: Path
    result_dir: Path
    metadata_dir: Path
    temp_dir: Path
    log_dir: Path
    models_dir: Path
    mediapipe_model_path: Path

    allowed_video_mime_types: tuple[str, ...]

    ffprobe_timeout_seconds: float

    normalize_videos: bool
    normalized_video_extension: str
    ffmpeg_timeout_seconds: float
    video_codec: str
    fps: int
    max_video_dimension: int
    strip_audio: bool
    ml_mock_mode: bool

    cleanup_interval_seconds: int

    input_retention_seconds: int
    result_retention_seconds: int
    model_metadata_retention_seconds: int
    conversion_metadata_retention_seconds: int

    ml_pipeline_settings: MLPipelineSettings


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _load_ml_settings(data: dict[str, Any]) -> MLPipelineSettings:
    ml_data = dict(data)

    for key in ("strings_6", "strings_4", "press_fingers", "note_names"):
        ml_data[key] = tuple(ml_data[key])

    ml_data["finger_colors"] = {
        name: tuple(color)
        for name, color in ml_data["finger_colors"].items()
    }

    return MLPipelineSettings(**ml_data)


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        configured_path = os.environ.get("GUITARCV_CONFIG_PATH")
        config_path = (
            Path(configured_path)
            if configured_path
            else ROOT_PATH / "config.json"
        )

    config_path = config_path.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            "Configuration file not found: %s. Create config.json from "
            "config.json.example or set GUITARCV_CONFIG_PATH."
            % config_path
        )

    with config_path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)

    if not isinstance(data, dict):
        raise ValueError("The configuration root must be a JSON object.")

    if "environment" in data:
        raise ValueError(
            "Unsupported legacy setting 'environment'; use 'app_env'."
        )

    base_dir = config_path.parent
    path_keys = (
        "data_dir",
        "sqlite_path",
        "upload_dir",
        "result_dir",
        "metadata_dir",
        "temp_dir",
        "log_dir",
        "models_dir",
        "mediapipe_model_path",
    )
    for key in path_keys:
        if key not in data:
            raise ValueError("Missing required configuration key: %s" % key)
        data[key] = _resolve_path(data[key], base_dir)

    data["allowed_video_mime_types"] = tuple(
        mime_type.strip().lower()
        for mime_type in data["allowed_video_mime_types"]
    )
    data["ml_pipeline_settings"] = _load_ml_settings(
        data["ml_pipeline_settings"]
    )

    settings = Settings(**data)

    if settings.app_env not in {"development", "production"}:
        raise ValueError("app_env must be either 'development' or 'production'")
    if settings.cleanup_interval_seconds <= 0:
        raise ValueError("cleanup_interval_seconds must be positive")
    if settings.ffprobe_timeout_seconds <= 0:
        raise ValueError("ffprobe_timeout_seconds must be positive")
    if settings.ffmpeg_timeout_seconds <= 0:
        raise ValueError("ffmpeg_timeout_seconds must be positive")
    if not settings.allowed_video_mime_types:
        raise ValueError("allowed_video_mime_types must not be empty")

    retention_values = (
        settings.input_retention_seconds,
        settings.result_retention_seconds,
        settings.model_metadata_retention_seconds,
        settings.conversion_metadata_retention_seconds,
    )
    if any(value < 0 for value in retention_values):
        raise ValueError("Retention durations must not be negative")

    # These are independently scanned/deleted by LocalStorage
    # Overlap would let cleanup mistake logs, model files or another storage area
    # for rudimentary/orphaned conversion artifacts
    storage_roots = {
        "upload_dir": settings.upload_dir,
        "result_dir": settings.result_dir,
        "metadata_dir": settings.metadata_dir,
        "temp_dir": settings.temp_dir,
    }
    storage_items = list(storage_roots.items())
    for index, (left_name, left_path) in enumerate(storage_items):
        for right_name, right_path in storage_items[index + 1:]:
            if (
                left_path == right_path
                or left_path.is_relative_to(right_path)
                or right_path.is_relative_to(left_path)
            ):
                raise ValueError(
                    "%s and %s must be separate, non-overlapping directories"
                    % (left_name, right_name)
                )

    protected_paths = {
        "log_dir": settings.log_dir,
        "models_dir": settings.models_dir,
    }
    for protected_name, protected_path in protected_paths.items():
        for storage_name, storage_path in storage_items:
            if (
                protected_path == storage_path
                or protected_path.is_relative_to(storage_path)
                or storage_path.is_relative_to(protected_path)
            ):
                raise ValueError(
                    "%s must not overlap %s"
                    % (protected_name, storage_name)
                )

    for protected_name, protected_path in (
        ("sqlite_path", settings.sqlite_path),
        ("mediapipe_model_path", settings.mediapipe_model_path),
    ):
        for storage_name, storage_path in storage_items:
            if protected_path.is_relative_to(storage_path):
                raise ValueError(
                    "%s must not be located inside %s"
                    % (protected_name, storage_name)
                )

    return settings


settings = load_settings()
