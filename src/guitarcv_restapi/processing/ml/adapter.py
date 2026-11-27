import json
import math
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any

from guitarcv_restapi.core.config import Settings, settings
from guitarcv_restapi.models.notes import Note, TemporalNotes


class NoNotesDetectedError(RuntimeError):
    """Raised when the model completed successfully but detected no notes."""


class MLAdapter(ABC):
    @abstractmethod
    def extract_notes(
        self,
        video_path: Path,
        metadata_dir: Path,
        temporary_dir: Path,
    ) -> TemporalNotes:
        """Run inference and return the normalized temporal note structure."""
        raise NotImplementedError


class RealMLAdapter(MLAdapter):
    MODEL_FILENAMES = {
        "hand": "hand_model.pt",
        "pose": "pose_model.pt",
        "guitar": "guitar_model.pt",
    }

    def __init__(
        self,
        models_dir: Path,
        mediapipe_model_path: Path,
    ) -> None:
        from guitarcv_restapi.ml.models import ModelStore
        from guitarcv_restapi.ml.pipeline import MLPipeline

        models_dir = Path(models_dir)
        model_paths = {
            name: models_dir / filename
            for name, filename in self.MODEL_FILENAMES.items()
        }
        missing_models = [
            path for path in model_paths.values() if not path.is_file()
        ]
        if missing_models:
            missing = ", ".join(str(path) for path in missing_models)
            raise FileNotFoundError(f"Required ML model file(s) not found: {missing}")

        model_store = ModelStore(
            hand_model_path=str(model_paths["hand"]),
            pose_model_path=str(model_paths["pose"]),
            guitar_model_path=str(model_paths["guitar"]),
        )
        self.pipeline = MLPipeline(
            model_store=model_store,
            mediapipe_model_path=Path(mediapipe_model_path),
        )
        # Ultralytics/model objects are reused, ensure no oevrlaps/races
        # from fastapi threadpool background task execution
        self._run_lock = Lock()

    @staticmethod
    def parse_summary(summary: dict[str, Any]) -> TemporalNotes:
        press_events = summary.get("press_events")
        if not isinstance(press_events, list):
            raise ValueError("ML summary does not contain a valid press_events list")

        temporal_notes: TemporalNotes = {}
        for event in press_events:
            if not isinstance(event, dict):
                continue

            try:
                start_sec = float(event["start_sec"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("ML press event has an invalid start_sec") from exc
            if not math.isfinite(start_sec) or start_sec < 0:
                raise ValueError(
                    "ML press event start_sec must be a finite non-negative number"
                )

            end_value = event.get("end_sec")
            duration_seconds: float | None = None
            if end_value is not None:
                try:
                    end_sec = float(end_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("ML press event has an invalid end_sec") from exc
                if not math.isfinite(end_sec):
                    raise ValueError("ML press event end_sec must be finite")
                duration_seconds = end_sec - start_sec
                if duration_seconds <= 0:
                    raise ValueError("ML press event end_sec must exceed start_sec")

            pressed = event.get("pressed")
            if not isinstance(pressed, list):
                continue

            for pressed_note in pressed:
                if not isinstance(pressed_note, dict):
                    continue
                try:
                    string_number = int(pressed_note["string"])
                    fret_number = int(pressed_note["fret"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "ML pressed note must contain integer string and fret values"
                    ) from exc

                raw_midi_note = pressed_note.get("midi_note")
                midi_note = (
                    int(raw_midi_note)
                    if raw_midi_note is not None
                    else None
                )
                if midi_note is not None and not 0 <= midi_note <= 127:
                    raise ValueError("ML pressed note has an invalid MIDI pitch")
                if string_number < 1 or fret_number < 0:
                    raise ValueError("ML pressed note has invalid string/fret values")

                temporal_notes.setdefault(start_sec, []).append(
                    Note(
                        string_number=string_number,
                        fret_number=fret_number,
                        midi_note=midi_note,
                        duration_seconds=duration_seconds,
                    )
                )

        if not temporal_notes:
            raise NoNotesDetectedError("No guitar notes were detected")

        return temporal_notes

    def extract_notes(
        self,
        video_path: Path,
        metadata_dir: Path,
        temporary_dir: Path,
    ) -> TemporalNotes:
        video_path = Path(video_path)
        metadata_dir = Path(metadata_dir)
        temporary_dir = Path(temporary_dir)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        temporary_dir.mkdir(parents=True, exist_ok=True)

        summary_path = metadata_dir / "summary.json"
        frames_path = metadata_dir / "frames.jsonl"
        annotated_video_path = temporary_dir / "annotated.avi"

        with self._run_lock:
            self.pipeline.run(
                video_path=str(video_path),
                output_video=str(annotated_video_path),
                frames_jsonl=str(frames_path),
                summary_json=str(summary_path),
            )

        with summary_path.open("r", encoding="utf-8") as summary_file:
            summary = json.load(summary_file)
        if not isinstance(summary, dict):
            raise ValueError("ML summary must be a JSON object")

        return self.parse_summary(summary)


class MockMLAdapter(MLAdapter):
    def extract_notes(
        self,
        video_path: Path,
        metadata_dir: Path,
        temporary_dir: Path,
    ) -> TemporalNotes:
        metadata_dir = Path(metadata_dir)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        Path(temporary_dir).mkdir(parents=True, exist_ok=True)

        temporal_notes: TemporalNotes = {
            0.0: [
                Note(
                    string_number=1,
                    fret_number=0,
                    midi_note=64,
                    duration_seconds=0.45,
                ),
                Note(
                    string_number=2,
                    fret_number=3,
                    midi_note=62,
                    duration_seconds=0.7,
                ),
            ],
            0.8: [
                Note(
                    string_number=3,
                    fret_number=2,
                    midi_note=57,
                    duration_seconds=0.35,
                ),
            ],
        }

        summary = {
            "video": str(video_path),
            "mock": True,
            "press_events": [
                {
                    "start_sec": start_sec,
                    "end_sec": start_sec + (note.duration_seconds or 0.0),
                    "pressed": [{
                        "string": note.string_number,
                        "fret": note.fret_number,
                        "midi_note": note.midi_note,
                    }],
                }
                for start_sec, notes in temporal_notes.items()
                for note in notes
            ],
        }
        with (metadata_dir / "summary.json").open("w", encoding="utf-8") as summary_file:
            json.dump(summary, summary_file, ensure_ascii=False, indent=2)

        return temporal_notes


def create_ml_adapter(configuration: Settings | None = None) -> MLAdapter:
    configuration = configuration or settings
    if configuration.ml_mock_mode:
        return MockMLAdapter()
    return RealMLAdapter(
        models_dir=configuration.models_dir,
        mediapipe_model_path=configuration.mediapipe_model_path,
    )
