import os

import cv2
import mediapipe as mp
import numpy as np

from guitarcv_restapi.core import settings
from guitarcv_restapi.core.logging import logger


class MediaPipeFingers:
    """Legacy mp.solutions (mediapipe < 0.10.31) ИЛИ Tasks API HandLandmarker (>= 0.10.31).
    process(crop_bgr, ts_ms) -> (landmarks | None, crop_со_скелетом).
    landmarks[i].x / .y — нормированные [0, 1], одинаково в обоих API."""

    HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),           # большой
        (0, 5), (5, 6), (6, 7), (7, 8),           # указательный
        (5, 9), (9, 10), (10, 11), (11, 12),      # средний
        (9, 13), (13, 14), (14, 15), (15, 16),    # безымянный
        (13, 17), (17, 18), (18, 19), (19, 20),   # мизинец
        (0, 17),
    ]
    MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                 "hand_landmarker/float16/1/hand_landmarker.task")

    def __init__(self, model_path="hand_landmarker.task"):
        self._last_ts = -1
        try:
            mp_hands = mp.solutions.hands

            self._hands = mp_hands.Hands(
                static_image_mode=False, max_num_hands=1, model_complexity=1,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)

            self._draw = mp.solutions.drawing_utils
            self._styles = mp.solutions.drawing_styles
            self._connections = mp_hands.HAND_CONNECTIONS
            self.mode = "legacy"
        except AttributeError:                                 # mediapipe >= 0.10.31
            if not os.path.exists(model_path):
                import urllib.request
                logger.info("Downloading hand_landmarker.task (~8 MB)...")
                urllib.request.urlretrieve(self.MODEL_URL, model_path)

            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5)

            self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
            self.mode = "tasks"

        logger.info(f"MediaPipe backend: {self.mode}")

    def process(self, crop_bgr, timestamp_ms):
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        annotated = crop_bgr.copy()

        if self.mode == "legacy":
            rgb.flags.writeable = False
            res = self._hands.process(rgb)

            if res.multi_hand_landmarks:
                hl = res.multi_hand_landmarks[0]
                self._draw.draw_landmarks(
                    annotated, hl, self._connections,
                    self._styles.get_default_hand_landmarks_style(),
                    self._styles.get_default_hand_connections_style())
                return hl.landmark, annotated

            return None, annotated

        # --- Tasks API: VIDEO-режим требует строго возрастающие timestamp'ы ---
        ts = max(int(timestamp_ms), self._last_ts + 1)
        self._last_ts = ts
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = self._landmarker.detect_for_video(mp_img, ts)

        if res.hand_landmarks:
            lms = res.hand_landmarks[0]                        # 21 NormalizedLandmark
            self._draw_skeleton(annotated, lms)
            return lms, annotated

        return None, annotated

    def _draw_skeleton(self, img, lms):
        h, w = img.shape[:2]
        pts = [(int(l.x * w), int(l.y * h)) for l in lms]
        for a, b in self.HAND_CONNECTIONS:
            cv2.line(img, pts[a], pts[b], (200, 200, 200), 1, cv2.LINE_AA)
        tips = set(settings.ml_pipeline_settings.fingertips.values())
        for i, p in enumerate(pts):
            cv2.circle(img, p, 3 if i in tips else 2,
                       (0, 0, 255) if i in tips else (0, 200, 255), -1)

    def close(self):
        if self.mode == "legacy":
            self._hands.close()
        else:
            self._landmarker.close()
