import json
from dataclasses import dataclass
from pathlib import Path


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

    data_dir: Path
    sqlite_path: Path
    upload_dir: Path
    result_dir: Path

    allowed_video_mime_types: tuple[str, ...]

    ffprobe_timeout_seconds: float

    normalize_videos: bool
    normalized_video_extension: str
    ffmpeg_timeout_seconds: float

    cleanup_interval_seconds: int

    input_retention_seconds: int
    result_retention_seconds: int
    model_metadata_retention_seconds: int
    conversion_metadata_retention_seconds: int

    ml_pipeline_settings: MLPipelineSettings

    @property
    def metadata_dir(self) -> Path:
        return self.data_dir / "metadata"


def load_settings() -> Settings:
    with (ROOT_PATH / "config.json").open("r", encoding="utf-8") as file:
        data = json.load(file)

    # Convert JSON values to their Python equivalents.
    for key in ("data_dir", "sqlite_path", "upload_dir", "result_dir"):
        data[key] = Path(data[key])

    data["allowed_video_mime_types"] = tuple(
        data["allowed_video_mime_types"]
    )

    ml_data = data["ml_pipeline_settings"]

    for key in ("strings_6", "strings_4", "press_fingers", "note_names"):
        ml_data[key] = tuple(ml_data[key])

    ml_data["finger_colors"] = {
        name: tuple(color)
        for name, color in ml_data["finger_colors"].items()
    }

    data["ml_pipeline_settings"] = MLPipelineSettings(**ml_data)

    return Settings(**data)


settings = load_settings()
