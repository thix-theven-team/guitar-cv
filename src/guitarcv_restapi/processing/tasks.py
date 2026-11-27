import logging

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from guitarcv_restapi.core.config import settings
from guitarcv_restapi.database.connection import Database
from guitarcv_restapi.models.conversion import ConversionStatus
from guitarcv_restapi.processing.media.ffmpeg import FFmpegProcessor
from guitarcv_restapi.processing.midi.exporter import MidiExportOptions, MidiExporter
from guitarcv_restapi.processing.ml.adapter import (
    MLAdapter,
    NoNotesDetectedError,
    create_ml_adapter,
)
from guitarcv_restapi.processing.pipeline import ConversionPipeline
from guitarcv_restapi.repositories.conversion_repository import ConversionRepository
from guitarcv_restapi.storage.local_storage import LocalStorage


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_conversion_pipeline() -> ConversionPipeline:
    ml_settings = settings.ml_pipeline_settings
    six_string_tuning = tuple(
        ml_settings.tuning["6"][str(string_number)]
        for string_number in range(1, 7)
    )

    ml_adapter: MLAdapter = create_ml_adapter(settings)
    midi_exporter = MidiExporter(
        MidiExportOptions(
            tempo_bpm=120,
            ticks_per_beat=480,
            open_string_midi_notes=six_string_tuning,
            default_note_duration_seconds=0.2,
        )
    )
    ffmpeg_processor = FFmpegProcessor(
        timeout_seconds=settings.ffmpeg_timeout_seconds,
        video_codec=settings.video_codec,
        fps=settings.fps,
        max_dimension=settings.max_video_dimension,
        strip_audio=settings.strip_audio,
    )

    return ConversionPipeline(
        ml_adapter=ml_adapter,
        midi_exporter=midi_exporter,
        ffmpeg_processor=ffmpeg_processor,
        normalize_video=settings.normalize_videos,
        normalized_video_extension=settings.normalized_video_extension,
    )


def process_conversion_task(conversion_id: str) -> None:
    database = Database(settings.sqlite_path)
    repository = ConversionRepository(database)
    storage = LocalStorage(
        upload_dir=settings.upload_dir,
        result_dir=settings.result_dir,
        metadata_dir=settings.metadata_dir,
        temp_dir=settings.temp_dir,
    )
    storage.ensure_directories()

    conversion = repository.get_by_id(conversion_id)
    if conversion is None:
        logger.warning(
            "Background task references missing conversion %s",
            conversion_id,
        )
        return
    if conversion.status != ConversionStatus.PROCESSING:
        logger.warning(
            "Skipping conversion %s because its status is %s",
            conversion_id,
            conversion.status.value,
        )
        return

    finished_at: datetime
    metadata_dir = storage.metadata_path_for(conversion_id)
    temporary_dir = storage.temporary_path_for(conversion_id)
    result_path = storage.result_path_for(conversion_id)

    if conversion.input_path is None or not storage.file_exists(conversion.input_path):
        finished_at = datetime.now(timezone.utc)
        repository.mark_failed(
            conversion_id=conversion_id,
            error_code="INPUT_FILE_MISSING",
            error_message="The uploaded video is no longer available for processing.",
            model_metadata_path=None,
            finished_at=finished_at,
            input_expires_at=finished_at,
            model_metadata_expires_at=finished_at + timedelta(
                seconds=settings.model_metadata_retention_seconds
            ),
            expires_at=finished_at + timedelta(
                seconds=settings.conversion_metadata_retention_seconds
            ),
        )
        return

    started_at = datetime.now(timezone.utc)
    if not repository.mark_processing(conversion_id, started_at):
        logger.warning(
            "Could not mark conversion %s as processing",
            conversion_id,
        )
        return

    try:
        metadata_dir.mkdir(parents=True, exist_ok=True)
        temporary_dir.mkdir(parents=True, exist_ok=True)
        if not repository.set_model_metadata_path(conversion_id, metadata_dir):
            raise RuntimeError("Could not persist the conversion metadata path.")

        pipeline = get_conversion_pipeline()
        temporary_result_path = temporary_dir / "output.mid"

        pipeline.process(
            input_video=conversion.input_path,
            output_midi=temporary_result_path,
            metadata_dir=metadata_dir,
            temporary_dir=temporary_dir,
        )

        if (
            not temporary_result_path.is_file()
            or temporary_result_path.stat().st_size == 0
        ):
            raise RuntimeError(
                "The MIDI exporter did not produce a valid output file."
            )

        # publish only complete results!!!!!!!!
        # LocalStorage stages the copy beside the destination
        # before an atomic rename
        storage.publish_file(temporary_result_path, result_path)

        finished_at = datetime.now(timezone.utc)
        marked_ready = repository.mark_ready(
            conversion_id=conversion_id,
            result_path=result_path,
            model_metadata_path=metadata_dir,
            finished_at=finished_at,
            input_expires_at=finished_at + timedelta(
                seconds=settings.input_retention_seconds
            ),
            result_expires_at=finished_at + timedelta(
                seconds=settings.result_retention_seconds
            ),
            model_metadata_expires_at=finished_at + timedelta(
                seconds=settings.model_metadata_retention_seconds
            ),
            expires_at=finished_at + timedelta(
                seconds=settings.conversion_metadata_retention_seconds
            ),
        )
        if not marked_ready:
            raise RuntimeError(
                "Could not persist ready state for conversion %s." % conversion_id
            )
        logger.info("Conversion %s completed successfully", conversion_id)

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        logger.exception("Conversion %s failed", conversion_id)
        try:
            storage.delete_file(result_path)
        except (OSError, ValueError):
            logger.exception(
                "Could not remove partial MIDI output for %s",
                conversion_id,
            )

        if isinstance(exc, NoNotesDetectedError):
            error_code = "NO_NOTES_DETECTED"
            error_message = "No guitar notes were detected in the uploaded video."
        else:
            error_code = "PROCESSING_FAILED"
            error_message = "The video could not be converted. Please try another video."

        try:
            marked_failed = repository.mark_failed(
                conversion_id=conversion_id,
                error_code=error_code,
                error_message=error_message,
                model_metadata_path=(metadata_dir if metadata_dir.exists() else None),
                finished_at=finished_at,
                input_expires_at=finished_at + timedelta(
                    seconds=settings.input_retention_seconds
                ),
                model_metadata_expires_at=finished_at + timedelta(
                    seconds=settings.model_metadata_retention_seconds
                ),
                expires_at=finished_at + timedelta(
                    seconds=settings.conversion_metadata_retention_seconds
                ),
            )
            if not marked_failed:
                logger.error(
                    "Could not transition conversion %s to failed",
                    conversion_id,
                )
        except Exception:
            logger.exception(
                "Could not persist failure state for conversion %s",
                conversion_id,
            )
    finally:
        try:
            storage.delete_directory(temporary_dir)
        except (OSError, ValueError):
            logger.exception(
                "Could not remove temporary directory for conversion %s",
                conversion_id,
            )
