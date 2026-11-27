from pathlib import Path

from guitarcv_restapi.models.notes import Note
from guitarcv_restapi.processing.pipeline import ConversionPipeline


class FakeMLAdapter:
    def __init__(self) -> None:
        self.arguments = None

    def extract_notes(self, **kwargs):
        self.arguments = kwargs
        return {0.0: [Note(1, 0, midi_note=64, duration_seconds=0.25)]}


class FakeMidiExporter:
    def __init__(self) -> None:
        self.arguments = None

    def export(self, temporal_notes, output_path):
        self.arguments = (temporal_notes, output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"midi")
        return output_path


class FakeFFmpegProcessor:
    def __init__(self) -> None:
        self.called = False

    def normalize_video(self, input_path, output_path, target_format):
        self.called = True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"normalized")
        return output_path


def test_pipeline_connects_ml_adapter_and_midi_exporter(tmp_path: Path) -> None:
    input_video = tmp_path / "input.upload"
    input_video.write_bytes(b"video")
    adapter = FakeMLAdapter()
    exporter = FakeMidiExporter()
    output = tmp_path / "results" / "output.mid"

    pipeline = ConversionPipeline(adapter, exporter)
    result = pipeline.process(
        input_video=input_video,
        output_midi=output,
        metadata_dir=tmp_path / "metadata",
        temporary_dir=tmp_path / "tmp",
    )

    assert result == output
    assert output.read_bytes() == b"midi"
    assert adapter.arguments["video_path"] == input_video
    assert adapter.arguments["metadata_dir"].is_dir()
    assert exporter.arguments[0][0.0][0].midi_note == 64


def test_pipeline_normalizes_video_only_when_enabled(tmp_path: Path) -> None:
    input_video = tmp_path / "input.upload"
    input_video.write_bytes(b"video")
    adapter = FakeMLAdapter()
    exporter = FakeMidiExporter()
    ffmpeg = FakeFFmpegProcessor()
    pipeline = ConversionPipeline(
        ml_adapter=adapter,
        midi_exporter=exporter,
        ffmpeg_processor=ffmpeg,
        normalize_video=True,
        normalized_video_extension=".mp4",
    )

    pipeline.process(
        input_video=input_video,
        output_midi=tmp_path / "result.mid",
        metadata_dir=tmp_path / "metadata",
        temporary_dir=tmp_path / "tmp",
    )

    assert ffmpeg.called
    assert adapter.arguments["video_path"].name == "normalized.mp4"
