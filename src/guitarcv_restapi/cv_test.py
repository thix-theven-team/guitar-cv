from guitarcv_restapi.core.logging import setup as logging_setup
from guitarcv_restapi.core.config import ROOT_PATH


if __name__ == "__main__":
    logging_setup()

    from guitarcv_restapi.ml.pipeline import MLPipeline
    from guitarcv_restapi.ml.models import ModelStore

    store = ModelStore(
        hand_model_path=str(ROOT_PATH / "models" / "hand_model.pt"),
        pose_model_path=str(ROOT_PATH / "models" / "pose_model.pt"),
        guitar_model_path=str(ROOT_PATH / "models" / "guitar_model.pt"),
    )

    pipeline = MLPipeline(store)

    pipeline.run(
        video_path="C:/Users/ki/Documents/guitarcv/testvideo.mp4",
        output_video="C:/Users/ki/Documents/guitarcv/output.avi",
    )
