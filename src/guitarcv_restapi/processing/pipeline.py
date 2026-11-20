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
    ) -> None:
        ... # TODO

    def process(
        self,
        input_video: Path,
        output_midi: Path,
    ) -> Path:
        ... # TODO