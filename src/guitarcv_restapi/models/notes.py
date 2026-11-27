from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Note:
    string_number: int
    fret_number: int
    midi_note: int | None = None
    duration_seconds: float | None = None


TemporalNotes: TypeAlias = dict[float, list[Note]]
