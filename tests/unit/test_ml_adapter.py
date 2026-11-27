import json
from pathlib import Path

import pytest

from guitarcv_restapi.models.notes import Note
from guitarcv_restapi.processing.ml.adapter import (
    MLAdapter,
    MockMLAdapter,
    NoNotesDetectedError,
    RealMLAdapter,
    create_ml_adapter,
)


def test_mock_adapter_implements_shared_parent_and_returns_temporal_notes(
    tmp_path: Path,
) -> None:
    adapter: MLAdapter = MockMLAdapter()
    metadata_dir = tmp_path / "metadata"
    temporary_dir = tmp_path / "tmp"

    notes = adapter.extract_notes(
        video_path=tmp_path / "input.upload",
        metadata_dir=metadata_dir,
        temporary_dir=temporary_dir,
    )

    assert isinstance(adapter, MLAdapter)
    assert notes[0.0][0] == Note(
        string_number=1,
        fret_number=0,
        midi_note=64,
        duration_seconds=0.45,
    )
    assert (metadata_dir / "summary.json").is_file()
    assert json.loads(
        (metadata_dir / "summary.json").read_text(encoding="utf-8")
    )["mock"] is True
    assert temporary_dir.is_dir()


def test_real_adapter_parser_preserves_pitch_and_duration() -> None:
    summary = {
        "press_events": [
            {
                "start_sec": 1.25,
                "end_sec": 1.85,
                "pressed": [
                    {"string": 2, "fret": 3, "midi_note": 62, "note": "D4"},
                    {"string": 3, "fret": 5, "midi_note": 60, "note": "C4"},
                ],
            }
        ]
    }

    notes = RealMLAdapter.parse_summary(summary)

    assert len(notes[1.25]) == 2
    assert notes[1.25][0].midi_note == 62
    assert notes[1.25][0].duration_seconds == pytest.approx(0.6)
    assert notes[1.25][1].midi_note == 60


def test_real_adapter_parser_combines_events_with_same_start_time() -> None:
    summary = {
        "press_events": [
            {
                "start_sec": 0.5,
                "end_sec": 1.0,
                "pressed": [{"string": 1, "fret": 0, "midi_note": 64}],
            },
            {
                "start_sec": 0.5,
                "end_sec": 1.2,
                "pressed": [{"string": 2, "fret": 3, "midi_note": 62}],
            },
        ]
    }

    notes = RealMLAdapter.parse_summary(summary)

    assert len(notes[0.5]) == 2
    assert notes[0.5][0].duration_seconds == pytest.approx(0.5)
    assert notes[0.5][1].duration_seconds == pytest.approx(0.7)


def test_real_adapter_parser_rejects_empty_note_results() -> None:
    with pytest.raises(NoNotesDetectedError):
        RealMLAdapter.parse_summary({"press_events": []})


def test_real_adapter_parser_rejects_invalid_midi_pitch() -> None:
    summary = {
        "press_events": [
            {
                "start_sec": 0,
                "end_sec": 1,
                "pressed": [{"string": 1, "fret": 0, "midi_note": 128}],
            }
        ]
    }

    with pytest.raises(ValueError, match="invalid MIDI pitch"):
        RealMLAdapter.parse_summary(summary)


def test_adapter_factory_selects_mock_implementation(settings_fixture) -> None:
    adapter = create_ml_adapter(settings_fixture)

    assert isinstance(adapter, MockMLAdapter)
    assert isinstance(adapter, MLAdapter)


def test_real_adapter_parser_rejects_non_finite_timestamps() -> None:
    summary = {
        "press_events": [
            {
                "start_sec": float("nan"),
                "end_sec": 1.0,
                "pressed": [{"string": 1, "fret": 0, "midi_note": 64}],
            }
        ]
    }

    with pytest.raises(ValueError, match="finite"):
        RealMLAdapter.parse_summary(summary)


def test_real_adapter_does_not_silently_fall_back_when_weights_are_missing(
    settings_fixture,
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    production_settings = replace(
        settings_fixture,
        ml_mock_mode=False,
        models_dir=tmp_path,
    )

    with pytest.raises(FileNotFoundError, match="Required ML model"):
        create_ml_adapter(production_settings)
