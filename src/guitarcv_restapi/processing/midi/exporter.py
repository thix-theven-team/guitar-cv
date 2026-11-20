from dataclasses import dataclass
from pathlib import Path

from guitarcv_restapi.models.notes import TemporalNotes


@dataclass(frozen=True, slots=True)
class MidiExportOptions:
    tempo_bpm: int
    ticks_per_beat: int

    # MIDI pitch of each open guitar string, ordered according to the string-numbering convention
    # (the highest-pitched string is string 1, and the lowest-pitched string is string 6).
    open_string_midi_notes: tuple[int, ...]

    # Used when the duration of a note cannot be determined
    # from subsequent note events
    default_note_duration_seconds: float


class MidiExporter:
    def __init__(
        self,
        options: MidiExportOptions,
    ) -> None:
        ... # TODO

    def export(
        self,
        temporal_notes: TemporalNotes,
        output_path: Path,
    ) -> Path:
        ... # TODO
