from pathlib import Path
from typing import BinaryIO


class LocalStorage:
    def __init__(
        self,
        upload_dir: Path,
        result_dir: Path,
        metadata_dir: Path,
    ) -> None:
        ... # TODO

    def ensure_directories(self) -> None:
        ... # TODO

    def save_upload(
        self,
        file: BinaryIO,
        conversion_id: str,
    ) -> Path:
        ... # TODO

    def upload_path_for(
        self,
        conversion_id: str,
    ) -> Path:
        ... # TODO

    def result_path_for(
        self,
        conversion_id: str,
    ) -> Path:
        ... # TODO

    def metadata_path_for(
        self,
        conversion_id: str,
    ) -> Path:
        ... # TODO

    def delete_file(
        self,
        path: Path,
    ) -> bool:
        ... # TODO

    def file_exists(
        self,
        path: Path,
    ) -> bool:
        ... # TODO
