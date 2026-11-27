import os
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Iterator


_CONVERSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class LocalStorage:
    def __init__(
        self,
        upload_dir: Path,
        result_dir: Path,
        metadata_dir: Path,
        temp_dir: Path,
    ) -> None:
        self.upload_dir = Path(upload_dir).resolve()
        self.result_dir = Path(result_dir).resolve()
        self.metadata_dir = Path(metadata_dir).resolve()
        self.temp_dir = Path(temp_dir).resolve()

        self._managed_roots = (
            self.upload_dir,
            self.result_dir,
            self.metadata_dir,
            self.temp_dir,
        )

    def ensure_directories(self) -> None:
        for directory in self._managed_roots:
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_conversion_id(conversion_id: str) -> None:
        if not _CONVERSION_ID_PATTERN.fullmatch(conversion_id):
            raise ValueError("conversion_id must be a 32-character UUID hex string")

    def upload_path_for(self, conversion_id: str) -> Path:
        self._validate_conversion_id(conversion_id)
        return self.upload_dir / f"{conversion_id}.upload"

    def result_path_for(self, conversion_id: str) -> Path:
        self._validate_conversion_id(conversion_id)
        return self.result_dir / f"{conversion_id}.mid"

    def metadata_path_for(self, conversion_id: str) -> Path:
        self._validate_conversion_id(conversion_id)
        return self.metadata_dir / conversion_id

    def temporary_path_for(self, conversion_id: str) -> Path:
        self._validate_conversion_id(conversion_id)
        return self.temp_dir / conversion_id

    def save_upload(
        self,
        file: BinaryIO,
        conversion_id: str,
    ) -> Path:
        destination = self.upload_path_for(conversion_id)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.upload_dir / (
            ".%s.%s.part" % (conversion_id, uuid.uuid4().hex)
        )

        try:
            try:
                file.seek(0)
            except (AttributeError, OSError):
                # Some BinaryIO implementations are not seekable (wtf?),in that case
                # copy from their current position
                pass

            with temporary.open("wb") as output:
                shutil.copyfileobj(file, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())

            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return destination

    def _validate_managed_path(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        for root in self._managed_roots:
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            if relative == Path("."):
                raise ValueError("Refusing to delete a storage root directory")
            return resolved

        raise ValueError(f"Path is outside application storage: {path}")

    def publish_file(self, source: Path, destination: Path) -> Path:
        """атомарная операция отправки завершенного файла в управляемую директорию.

        итоговое переименование остается в файловой системе получателя, даже если
        упаси боже temp_dir и result_dir окажутся на разных mount-ах.
        """
        source_path = self._validate_managed_path(source)
        destination_path = self._validate_managed_path(destination)
        if not source_path.is_file():
            raise FileNotFoundError("Source artifact does not exist: %s" % source_path)

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = destination_path.with_name(
            ".%s.%s.part" % (destination_path.name, uuid.uuid4().hex)
        )
        try:
            shutil.copyfile(source_path, staging_path)
            staging_path.replace(destination_path)
        except Exception:
            staging_path.unlink(missing_ok=True)
            raise

        return destination_path

    def delete_file(self, path: Path) -> bool:
        managed_path = self._validate_managed_path(path)
        if not managed_path.exists():
            return True
        if managed_path.is_dir():
            raise IsADirectoryError(managed_path)
        managed_path.unlink()
        return True

    def delete_directory(self, path: Path) -> bool:
        managed_path = self._validate_managed_path(path)
        if not managed_path.exists():
            return True
        if not managed_path.is_dir():
            raise NotADirectoryError(managed_path)
        shutil.rmtree(managed_path)
        return True

    def file_exists(self, path: Path) -> bool:
        managed_path = self._validate_managed_path(path)
        return managed_path.is_file()

    def directory_exists(self, path: Path) -> bool:
        managed_path = self._validate_managed_path(path)
        return managed_path.is_dir()

    def iter_persistent_artifacts(self) -> Iterator[Path]:
        for root in (self.upload_dir, self.result_dir, self.metadata_dir):
            if not root.is_dir():
                continue
            yield from root.iterdir()

    def clear_temporary_storage(self) -> int:
        """Remove all transient artifacts left by a previous process run
        This is intended for application startup, before new background tasks
        are accepted. It is safe only while this application is the sole
        process using the configured data directory.
        """
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        removed = 0
        for child in self.temp_dir.iterdir():
            if child.is_dir():
                self.delete_directory(child)
            else:
                self.delete_file(child)
            removed += 1
        return removed
