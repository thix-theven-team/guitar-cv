import json
from dataclasses import fields
from pathlib import Path

import pytest

from guitarcv_restapi.core.config import (
    MLPipelineSettings,
    Settings,
    load_settings,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_example_config_matches_runtime_config_schema() -> None:
    example = json.loads((PROJECT_ROOT / "config.json.example").read_text())
    runtime = json.loads((PROJECT_ROOT / "config.json").read_text())

    assert set(example) == set(runtime)
    assert set(example["ml_pipeline_settings"]) == set(
        runtime["ml_pipeline_settings"]
    )
    assert "app_env" in example
    assert "environment" not in example
    assert "environment" not in runtime


def test_relative_paths_are_resolved_against_config_directory(
    tmp_path: Path,
) -> None:
    source = json.loads((PROJECT_ROOT / "config.json.example").read_text())
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps(source), encoding="utf-8")

    settings = load_settings(config_path)

    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.sqlite_path == (tmp_path / "data" / "conversions.sqlite3").resolve()
    assert settings.upload_dir == (tmp_path / "data" / "uploads").resolve()
    assert settings.result_dir == (tmp_path / "data" / "results").resolve()
    assert settings.metadata_dir == (tmp_path / "data" / "metadata").resolve()
    assert settings.temp_dir == (tmp_path / "data" / "tmp").resolve()
    assert settings.log_dir == (tmp_path / "data" / "logs").resolve()
    assert settings.models_dir == (tmp_path / "models").resolve()
    assert settings.mediapipe_model_path == (
        tmp_path / "data" / "ml-assets" / "hand_landmarker.task"
    ).resolve()


def test_legacy_environment_key_is_rejected(tmp_path: Path) -> None:
    source = json.loads((PROJECT_ROOT / "config.json.example").read_text())
    source["environment"] = source["app_env"]
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="legacy setting 'environment'"):
        load_settings(config_path)


def test_server_configuration_disables_gui_windows() -> None:
    settings = load_settings(PROJECT_ROOT / "config.json.example")

    assert settings.ml_pipeline_settings.show_windows is False
    assert settings.ml_pipeline_settings.show_crop_window is False


def test_storage_directories_must_not_overlap(tmp_path: Path) -> None:
    source = json.loads((PROJECT_ROOT / "config.json.example").read_text())
    source["temp_dir"] = source["upload_dir"]
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="must be separate, non-overlapping"):
        load_settings(config_path)


def test_json_configuration_keys_match_settings_dataclasses() -> None:
    expected = {field.name for field in fields(Settings)}
    expected_ml = {field.name for field in fields(MLPipelineSettings)}

    for filename in ("config.json", "config.json.example"):
        configuration = json.loads((PROJECT_ROOT / filename).read_text())
        assert set(configuration) == expected
        assert set(configuration["ml_pipeline_settings"]) == expected_ml
        load_settings(PROJECT_ROOT / filename)
