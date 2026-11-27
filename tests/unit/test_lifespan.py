from dataclasses import replace
from datetime import datetime, timedelta, timezone

from guitarcv_restapi.core.config import settings
from guitarcv_restapi.core.lifespan import recover_interrupted_conversions


class FakeRepository:
    def __init__(self) -> None:
        self.arguments = None

    def mark_interrupted_as_failed(self, **kwargs) -> int:
        self.arguments = kwargs
        return 2


def test_recovery_marks_interrupted_jobs_with_configured_retention() -> None:
    configuration = replace(
        settings,
        input_retention_seconds=60,
        model_metadata_retention_seconds=120,
        conversion_metadata_retention_seconds=180,
    )
    now = datetime(2026, 11, 27, 0, 0, tzinfo=timezone.utc)
    repository = FakeRepository()

    recovered = recover_interrupted_conversions(
        repository,
        configuration,
        now=now,
    )

    assert recovered == 2
    assert repository.arguments == {
        "finished_at": now,
        "input_expires_at": now + timedelta(seconds=60),
        "model_metadata_expires_at": now + timedelta(seconds=120),
        "expires_at": now + timedelta(seconds=180),
    }
