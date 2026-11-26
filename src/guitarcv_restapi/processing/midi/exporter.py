from dataclasses import dataclass
from pathlib import Path

import mido

from guitarcv_restapi.models.notes import Note, TemporalNotes


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
        if options.tempo_bpm <= 0:
            raise ValueError("tempo_bpm must be positive.")
        if options.ticks_per_beat <= 0:
            raise ValueError("ticks_per_beat must be positive.")
        if not options.open_string_midi_notes:
            raise ValueError("open_string_midi_notes must not be empty.")
        if options.default_note_duration_seconds <= 0:
            raise ValueError(
                "default_note_duration_seconds must be positive."
            )

        self.options = options

    def _note_to_midi_pitch(self, note: Note) -> int:
        string_count = len(self.options.open_string_midi_notes)
        if not (1 <= note.string_number <= string_count):
            raise ValueError(
                f"Invalid string_number {note.string_number}; "
                f"expected 1..{string_count}."
            )
        if note.fret_number < 0:
            raise ValueError(
                f"Invalid fret_number {note.fret_number}; must be >= 0."
            )

        open_pitch = self.options.open_string_midi_notes[
            note.string_number - 1
        ]
        pitch = open_pitch + note.fret_number
        if not (0 <= pitch <= 127):
            raise ValueError(
                f"Computed MIDI pitch {pitch} is out of range 0..127."
            )

        return pitch

    def _seconds_to_tick(self, seconds: float, tempo: int) -> int:
        tick = mido.second2tick(
            seconds,
            self.options.ticks_per_beat,
            tempo,
        )
        return max(0, int(round(tick)))

    def export(
        self,
        temporal_notes: TemporalNotes,
        output_path: Path,
    ) -> Path:
        mid = mido.MidiFile(ticks_per_beat=self.options.ticks_per_beat)
        track = mido.MidiTrack()
        mid.tracks.append(track)

        tempo = int(round(mido.bpm2tempo(self.options.tempo_bpm)))
        track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

        sorted_timestamps = sorted(temporal_notes.keys())

        # (tick, priority, event_type, pitch, velocity)
        # priority: 0 для note_off, 1 для note_on
        events: list[tuple[int, int, str, int, int]] = []

        for idx, start_sec in enumerate(sorted_timestamps):
            notes_at_time = temporal_notes[start_sec]
            if not notes_at_time:
                continue

            if idx + 1 < len(sorted_timestamps):
                end_sec = sorted_timestamps[idx + 1]
            else:
                end_sec = (
                    start_sec
                    + self.options.default_note_duration_seconds
                )

            start_tick = self._seconds_to_tick(start_sec, tempo)
            end_tick = max(
                start_tick,
                self._seconds_to_tick(end_sec, tempo),
            )

            for note in notes_at_time:
                pitch = self._note_to_midi_pitch(note)
                events.append((start_tick, 1, "note_on", pitch, 80))
                events.append((end_tick, 0, "note_off", pitch, 0))

        events.sort(key=lambda event: (event[0], event[1], event[3]))

        previous_tick = 0
        for tick, _, event_type, pitch, velocity in events:
            delta_time = tick - previous_tick
            track.append(
                mido.Message(
                    event_type,
                    note=pitch,
                    velocity=velocity,
                    time=delta_time,
                )
            )
            previous_tick = tick

        track.append(mido.MetaMessage("end_of_track", time=0))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        mid.save(str(output_path))
        return output_path
