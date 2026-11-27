import argparse
from pathlib import Path

from guitarcv_restapi.core.config import settings
from guitarcv_restapi.core.logging import setup as logging_setup


def main():
    parser = argparse.ArgumentParser(
        description="Run GuitarCV ML on a local video"
    )
    parser.add_argument("video", type=Path, help="Input video path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to the configured temporary directory)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or settings.temp_dir / "cv-test"
    output_dir.mkdir(parents=True, exist_ok=True)

    logging_setup()

    from guitarcv_restapi.ml.models import ModelStore
    from guitarcv_restapi.ml.pipeline import MLPipeline

    model_store = ModelStore(
        hand_model_path=str(settings.models_dir / "hand_model.pt"),
        pose_model_path=str(settings.models_dir / "pose_model.pt"),
        guitar_model_path=str(settings.models_dir / "guitar_model.pt"),
    )
    pipeline = MLPipeline(
        model_store=model_store,
        mediapipe_model_path=settings.mediapipe_model_path,
    )
    pipeline.run(
        video_path=args.video,
        output_video=output_dir / "annotated.avi",
        frames_jsonl=output_dir / "frames.jsonl",
        summary_json=output_dir / "summary.json",
    )


if __name__ == "__main__":
    main()
