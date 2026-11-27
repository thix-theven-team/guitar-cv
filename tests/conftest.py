from datetime import datetime, timezone
from pathlib import Path

import pytest

from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.database.schema import initialize_database
from guitarcv_restapi.repositories.conversion_repository import ConversionRepository
from guitarcv_restapi.storage.local_storage import LocalStorage


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(tmp_path / "data" / "test.sqlite3")
    initialize_database(instance)
    return instance


@pytest.fixture
def repository(database: Database) -> ConversionRepository:
    return ConversionRepository(database)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    instance = LocalStorage(
        upload_dir=tmp_path / "data" / "uploads",
        result_dir=tmp_path / "data" / "results",
        metadata_dir=tmp_path / "data" / "metadata",
        temp_dir=tmp_path / "data" / "tmp",
    )
    instance.ensure_directories()
    return instance


@pytest.fixture
def settings_fixture():
    from dataclasses import replace

    from guitarcv_restapi.core.config import settings

    return replace(settings, ml_mock_mode=True)
