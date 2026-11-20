from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class ConversionStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(slots=True)
class Conversion:
    conversion_id: str
    status: ConversionStatus

    created_at: datetime
    updated_at: datetime

    input_path: Path

    result_path: Path | None = None

    error_code: str | None = None
    error_message: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    expires_at: datetime | None = None

    input_expires_at: datetime | None = None
    result_expires_at: datetime | None = None
    model_metadata_expires_at: datetime | None = None
    model_metadata_path: Path | None = None