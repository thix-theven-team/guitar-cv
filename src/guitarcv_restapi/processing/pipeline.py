from pathlib import Path

from guitarcv_restapi.processing.media.ffmpeg import FFmpegProcessor
from guitarcv_restapi.processing.ml.adapter import MLAdapter
from guitarcv_restapi.processing.midi.exporter import MidiExporter


class ConversionPipeline:
    def __init__(
        self,
        ml_adapter: MLAdapter,
        midi_exporter: MidiExporter,
        ffmpeg_processor: FFmpegProcessor | None = None,
        normalize_video: bool = False,
        normalized_video_extension: str = ".mp4",
    ) -> None:
        if normalize_video and ffmpeg_processor is None:
            raise ValueError("ffmpeg_processor is required when normalization is enabled")

        self.ml_adapter = ml_adapter
        self.midi_exporter = midi_exporter
        self.ffmpeg_processor = ffmpeg_processor
        self.normalize_video = normalize_video
        self.normalized_video_extension = normalized_video_extension

    def process(
        self,
        input_video: Path,
        output_midi: Path,
        metadata_dir: Path,
        temporary_dir: Path,
    ) -> Path:
        input_video = Path(input_video)
        output_midi = Path(output_midi)
        metadata_dir = Path(metadata_dir)
        temporary_dir = Path(temporary_dir)

        if not input_video.is_file():
            raise FileNotFoundError(f"Input video does not exist: {input_video}")

        metadata_dir.mkdir(parents=True, exist_ok=True)
        temporary_dir.mkdir(parents=True, exist_ok=True)
        output_midi.parent.mkdir(parents=True, exist_ok=True)

        processing_video = input_video
        if self.normalize_video:
            extension = self.normalized_video_extension.lstrip(".")
            normalized_path = temporary_dir / f"normalized.{extension}"
            assert self.ffmpeg_processor is not None
            processing_video = self.ffmpeg_processor.normalize_video(
                input_path=input_video,
                output_path=normalized_path,
                target_format=extension,
            )

        temporal_notes = self.ml_adapter.extract_notes(
            video_path=processing_video,
            metadata_dir=metadata_dir,
            temporary_dir=temporary_dir,
        )

        return self.midi_exporter.export(
            temporal_notes=temporal_notes,
            output_path=output_midi,
        )
