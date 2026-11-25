from ultralytics import YOLO

from guitarcv_restapi.core.logging import logger


class ModelStore:
    model_hand: YOLO
    model_pose: YOLO
    model_guitar: YOLO

    def __init__(
        self,
        hand_model_path: str,
        pose_model_path: str,
        guitar_model_path: str,
    ):
        self.model_hand = YOLO(hand_model_path)
        self.model_pose = YOLO(pose_model_path)
        self.model_guitar = YOLO(guitar_model_path)

        if self.model_pose.task != "pose":
            raise ValueError(f"Fretboard model should be 'pose', but it is currently '{self.model_pose.task}'.")

        logger.info(
            f"Initialized ModelStore with the following tasks:\n"
            f"- hand={self.model_hand.task}\n"
            f"- frets={self.model_pose.task}\n"
            f"- guitar={self.model_guitar.task}"
        )
