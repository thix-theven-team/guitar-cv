from guitarcv_restapi.ml.models import ModelStore
from guitarcv_restapi.ml import MediaPipeFingers, PressTracker

from guitarcv_restapi.ml.processing.classification import (
    classify_guitar, n_strings_for_class
)

from guitarcv_restapi.ml.processing.fret import (
    extract_fret_wires, sort_wires_nut_first, build_fretboard, locate_on_fretboard
)

from guitarcv_restapi.ml.utils import (
    put_ascii, transform_points, expand_bbox
)

from guitarcv_restapi.core import settings
from guitarcv_restapi.core.logging import logger

import json
import os
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np


class MLPipeline:
    model_store: ModelStore
    mediapipe_model_path: str | Path

    def __init__(
        self,
        model_store: ModelStore,
        mediapipe_model_path: str | Path = "hand_landmarker.task",
    ):
        self.model_store = model_store
        self.mediapipe_model_path = mediapipe_model_path

    def run(
        self,
        video_path: str | Path,
        output_video: str | Path = "output.avi",
        frames_jsonl: str | Path = "frames.jsonl",
        summary_json: str | Path = "summary.json",
    ):
        video_path_str = str(video_path)
        output_video_str = str(output_video)
        frames_jsonl_path = Path(frames_jsonl)
        summary_json_path = Path(summary_json)

        Path(output_video_str).parent.mkdir(parents=True, exist_ok=True)
        frames_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        summary_json_path.parent.mkdir(parents=True, exist_ok=True)

        mediapipe_path = Path(self.mediapipe_model_path)
        mediapipe_path.parent.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(video_path_str)
        if not cap.isOpened():
            logger.error(f"Could not open video at path {video_path_str}.")
            raise ValueError(f"Could not open video at path {video_path_str}.")

        logger.info(f"Processing video at path {video_path_str}.")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        out = cv2.VideoWriter(output_video_str, cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))

        if settings.ml_pipeline_settings.show_windows:
            cv2.namedWindow("Pipeline", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Pipeline", 1280, 720)

        finger_tracker = MediaPipeFingers(model_path=str(mediapipe_path))

        tracker = PressTracker(settings.ml_pipeline_settings.min_stable_frames)

        smooth = {
            name: deque(maxlen=settings.ml_pipeline_settings.smooth_win)
            for name
            in settings.ml_pipeline_settings.fingertips.keys()
        }

        wires_cache, fb_cache = [], None
        guitar_name, guitar_conf, guitar_bbox = None, 0.0, None
        last_cls_t, votes, guitar_timeline = -1e9, Counter(), []
        frame_idx, t0 = 0, time.time()
        fjson = open(frames_jsonl_path, "w", encoding="utf-8")
    
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                t = frame_idx / fps
                annotated = frame.copy()
    
                # --- 1) ГИТАРА: раз в CLS_PERIOD_SEC, между запусками — кэш ---
                if t - last_cls_t >= settings.ml_pipeline_settings.cls_period_sec:
                    last_cls_t = t

                    name, conf, bbox = classify_guitar(self.model_store, frame, settings.ml_pipeline_settings.cls_conf)
                    guitar_timeline.append({"time_sec": round(t, 2), "class": name, "confidence": conf})

                    if name:
                        guitar_name, guitar_conf, guitar_bbox = name, conf, bbox
                        votes[name] += conf                       # голосование, взвешенное по уверенности

                        if bbox:
                            x1, y1, x2, y2 = map(int, bbox)
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

                n_strings = n_strings_for_class(guitar_name)
                strings_map = settings.ml_pipeline_settings.strings_4 \
                    if n_strings == 4 \
                    else settings.ml_pipeline_settings.strings_6
    
                # --- 2) РУКА: YOLO каждый кадр ---
                rh = self.model_store.model_hand.predict(
                    frame,
                    imgsz=settings.ml_pipeline_settings.hand_imgsz,
                    conf=settings.ml_pipeline_settings.hand_conf,
                    device=settings.ml_pipeline_settings.device, verbose=False
                )[0]

                hand_box, hand_conf = None, 0.0
                if rh.boxes is not None and len(rh.boxes):
                    i = int(rh.boxes.conf.argmax())

                    hand_box = [float(v) for v in rh.boxes.xyxy[i].tolist()]
                    hand_conf = float(rh.boxes.conf[i])
                    x1, y1, x2, y2 = map(int, hand_box)

                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
                    put_ascii(annotated, f"hand {hand_conf:.2f}", (x1, max(15, y1 - 8)), color=(0, 255, 255))
    
                # --- 3) ЛАДЫ: YOLO-pose каждый POSE_STRIDE-й кадр, между — кэш ---
                pose_refreshed = (frame_idx % settings.ml_pipeline_settings.pose_stride == 0)
                if pose_refreshed:
                    rp = self.model_store.model_pose.predict(frame,
                        imgsz=settings.ml_pipeline_settings.pose_imgsz,
                        conf=settings.ml_pipeline_settings.pose_conf,
                        device=settings.ml_pipeline_settings.device,
                        verbose=False
                    )[0]

                    wires = sort_wires_nut_first(
                        extract_fret_wires(
                            rp,
                            settings.ml_pipeline_settings.pose_conf,
                            settings.ml_pipeline_settings.kp_conf),
                        settings.ml_pipeline_settings.nut_side_fallback)

                    if len(wires) >= 2:
                        fb = build_fretboard(wires)

                        if fb is not None:
                            wires_cache, fb_cache = wires, fb

                wires, fb = wires_cache, fb_cache
    
                # --- 4) ПАЛЬЦЫ: MediaPipe на кропе руки -> глобальные координаты -> (струна, лад) ---
                fingers, presses, crop_vis = [], set(), None
                if hand_box is not None:
                    bx1, by1, bx2, by2 = expand_bbox(hand_box, settings.ml_pipeline_settings.hand_pad, width, height)
                    crop = frame[by1:by2, bx1:bx2]

                    if crop.size and crop.shape[0] >= 40 and crop.shape[1] >= 40:
                        lms, crop_vis = finger_tracker.process(crop, int(t * 1000))

                        if lms is not None:
                            ch, cw = crop.shape[:2]
                            for fname, lid in settings.ml_pipeline_settings.fingertips.items():
                                lm = lms[lid]
                                gx, gy = bx1 + lm.x * cw, by1 + lm.y * ch   # кроп -> полный кадр

                                rec = {
                                    "finger": fname,
                                    "landmark_id": lid,
                                    "crop_norm": [round(lm.x, 4), round(lm.y, 4)],
                                    "global_xy": [round(gx, 1), round(gy, 1)],
                                    "rect_xy": None,
                                    "string": None,
                                    "fret": None,
                                    "on_fretboard": False,
                                    "press_candidate": False
                                }

                                if fb is not None:
                                    uv = transform_points(fb["H"], [(gx, gy)])[0]
                                    smooth[fname].append(uv)
                                    uv_s = np.median(np.array(smooth[fname]), axis=0)
                                    rec["rect_xy"] = [round(float(uv_s[0]), 1), round(float(uv_s[1]), 1)]
                                    loc = locate_on_fretboard(uv_s, fb, n_strings, strings_map)

                                    if loc:
                                        rec.update(string=loc["string"], fret=loc["fret"], on_fretboard=True)
                                        if fname in settings.ml_pipeline_settings.press_fingers:
                                            rec["press_candidate"] = True
                                            presses.add((loc["string"], loc["fret"]))
                                fingers.append(rec)

                                color = settings.ml_pipeline_settings.finger_colors[fname]
                                label = f"s{rec['string']}f{rec['fret']}" if rec["string"] else fname
                                cv2.circle(annotated, (int(gx), int(gy)), 5, color, -1)
                                put_ascii(annotated, label, (int(gx) + 6, int(gy) - 6), 0.5, color)
                                put_ascii(crop_vis, label, (int(lm.x * cw) + 4, int(lm.y * ch) - 4), 0.45, color)

                        else:
                            for d in smooth.values():
                                d.clear()
                else:
                    for d in smooth.values():
                        d.clear()
                tracker.update(t, presses)
    
                # --- 5) ОТРИСОВКА ГРИФА ---
                for i, w in enumerate(wires):
                    p1, p2 = tuple(w["top"].astype(int)), tuple(w["bottom"].astype(int))
                    cv2.line(annotated, p1, p2, (255, 200, 0), 2)
                    num = ("nut" if i == 0 else str(i)) if settings.ml_pipeline_settings.first_wire_is_nut else str(i + 1)
                    put_ascii(annotated, num, (p1[0] - 6, max(12, p1[1] - 8)), 0.45, (255, 200, 0))

                if fb is not None:
                    for r in range(1, n_strings):             # линии струн — через обратную гомографию
                        v = r * fb["h"] / n_strings
                        a, b = transform_points(fb["Hinv"], [(fb["bounds"][0], v), (fb["w"], v)])
                        cv2.line(annotated, tuple(a.astype(int)), tuple(b.astype(int)), (170, 170, 170), 1)

                    if not settings.ml_pipeline_settings.first_wire_is_nut:                 # оценённый порожек
                        a, b = transform_points(fb["Hinv"], [(fb["bounds"][0], 0), (fb["bounds"][0], fb["h"])])
                        cv2.line(annotated, tuple(a.astype(int)), tuple(b.astype(int)), (0, 255, 255), 1)
                        put_ascii(annotated, "nut~", (int(a[0]) - 10, max(12, int(a[1]) - 8)), 0.45, (0, 255, 255))

                banner = f"Guitar: {guitar_name or '...'} {guitar_conf:.2f} | strings={n_strings} | t={t:.2f}s"
                cv2.rectangle(annotated, (5, 5), (10 + 8 * len(banner), 32), (0, 0, 0), -1)
                put_ascii(annotated, banner, (10, 26), 0.6, (255, 255, 255))

                # --- 6) ПОТОКОВЫЙ JSONL ---
                geom = "cached"
                if pose_refreshed and fb is not None:
                    geom = {
                        "n_wires": len(wires),
                        "wires": [
                            {
                                "top": [round(float(x), 1) for x in w["top"]],
                                "bottom": [round(float(x), 1) for x in w["bottom"]],
                                "conf": w["conf"]
                            } for w in wires
                        ],
                        "homography": fb["H"].round(5).tolist(),
                        "fret_bounds": fb["bounds"].round(1).tolist(),
                        "rect_size": [round(fb["w"], 1), fb["h"]]
                    }

                entry = {
                    "frame": frame_idx,
                    "time_sec": round(t, 3),
                    "guitar": {
                        "class": guitar_name,
                        "confidence": guitar_conf,
                        "bbox": guitar_bbox,
                        "n_strings": n_strings
                    },
                    "hand": {
                        "bbox": [round(v, 1) for v in hand_box],
                        "confidence": round(hand_conf, 3)} if hand_box else None,
                    "fretboard": geom,
                    "fingers": fingers,
                    "press_candidates": [{"string": s, "fret": f} for s, f in sorted(presses)]
                }

                fjson.write(json.dumps(entry, ensure_ascii=False) + "\n")
                if frame_idx % 30 == 0:
                    fjson.flush()
    
                # --- 7) ВИДЕО / ОКНА ---
                out.write(annotated)

                if settings.ml_pipeline_settings.show_windows:
                    cv2.imshow("Pipeline", annotated)
                    if settings.ml_pipeline_settings.show_crop_window and crop_vis is not None:
                        scale = min(2.0, 640.0 / max(1, crop_vis.shape[1]))
                        cv2.imshow("Hand crop + MediaPipe", cv2.resize(crop_vis, None, fx=scale, fy=scale))
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                if frame_idx % 150 == 0:
                    logger.info(f"[{t:.1f}s] frame {frame_idx}/{total} | guitar: {guitar_name} | candidates: {len(presses)}")
                frame_idx += 1

        finally:
            tracker.finish(frame_idx / fps)
            cap.release()
            out.release()
            finger_tracker.close()
            fjson.close()
            cv2.destroyAllWindows()
    
        # --- ИТОГ: класс по голосованию + события с MIDI-нотами ---
        final_class = votes.most_common(1)[0][0] if votes else None
        n_final = n_strings_for_class(final_class)

        for ev in tracker.events:
            for p in ev["pressed"]:
                midi = settings.ml_pipeline_settings.tuning[n_final][p["string"]] + p["fret"]
                p["midi_note"] = midi
                p["note"] = settings.ml_pipeline_settings.note_names[midi % 12] + str(midi // 12 - 1)

        summary = {
            "video": video_path_str,
            "frames_processed": frame_idx,
            "source_fps": fps,
            "processing_time_sec": round(time.time() - t0, 1),
            "guitar_class_final": final_class,
            "guitar_votes": dict(votes),
            "guitar_timeline": guitar_timeline,
            "n_strings": n_final,
            "press_events": tracker.events,
            "config": {
                "FIRST_WIRE_IS_NUT": settings.ml_pipeline_settings.first_wire_is_nut,
                "POSE_STRIDE": settings.ml_pipeline_settings.pose_stride,
                "CLS_PERIOD_SEC": settings.ml_pipeline_settings.cls_period_sec,
                "MIN_STABLE_FRAMES": settings.ml_pipeline_settings.min_stable_frames,
                "strings_top_to_bottom": settings.ml_pipeline_settings.strings_4 if n_final == 4 else settings.ml_pipeline_settings.strings_6,
                "tuning_midi": settings.ml_pipeline_settings.tuning[n_final]
            }
        }

        with open(summary_json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        logger.info(f"Done. Guitar class: {final_class}. Press events: {len(tracker.events)}")
        logger.info(f"Video: {os.path.abspath(output_video_str)}\nJSONL: {os.path.abspath(frames_jsonl_path)}"
                    f"\nSummary: {os.path.abspath(summary_json_path)}")
