from pathlib import Path

from guitarcv_restapi.models.notes import TemporalNotes


class MLAdapter:
    def __init__(
        self,
        model: object, # TODO: Replace with actual model type
    ) -> None:
        ... # TODO

    def extract_notes(
        self,
        video_path: Path,
    ) -> TemporalNotes:
        ... # TODO
