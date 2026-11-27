from pathlib import Path

import mido

from guitarcv_restapi.models.notes import Note
from guitarcv_restapi.processing.midi.exporter import (
    MidiExportOptions,
    MidiExporter,
)


def make_exporter() -> MidiExporter:
    return MidiExporter(
        MidiExportOptions(
            tempo_bpm=120,
            ticks_per_beat=480,
            open_string_midi_notes=(64, 59, 55, 50, 45, 40),
            default_note_duration_seconds=0.2,
        )
    )


def test_exporter_prefers_ml_pitch_and_preserves_note_duration(
    tmp_path: Path,
) -> None:
    output = tmp_path / "results" / "test.mid"
    notes = {
        1.0: [
            Note(
                string_number=2,
                fret_number=3,
                midi_note=62,
                duration_seconds=0.5,
            )
        ]
    }

    result = make_exporter().export(notes, output)

    assert result == output
    midi = mido.MidiFile(output)
    events = [message for message in midi.tracks[0] if message.type in ("note_on", "note_off")]
    assert [event.type for event in events] == ["note_on", "note_off"]
    assert events[0].note == 62
    assert events[1].note == 62
    assert events[1].time > 0


def test_exporter_falls_back_to_string_and_fret_mapping(tmp_path: Path) -> None:
    output = tmp_path / "fallback.mid"
    notes = {0.0: [Note(string_number=1, fret_number=2)]}

    make_exporter().export(notes, output)

    midi = mido.MidiFile(output)
    note_on = next(message for message in midi.tracks[0] if message.type == "note_on")
    assert note_on.note == 66


def test_exporter_rejects_invalid_note_duration(tmp_path: Path) -> None:
    notes = {0.0: [Note(string_number=1, fret_number=0, midi_note=64, duration_seconds=0)]}

    try:
        make_exporter().export(notes, tmp_path / "invalid.mid")
    except ValueError as error:
        assert "duration" in str(error)
    else:
        raise AssertionError("Expected invalid note duration to be rejected")
