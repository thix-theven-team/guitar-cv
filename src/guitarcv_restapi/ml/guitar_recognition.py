"""
Пайплайн: YOLO-рука + YOLO-pose (лады) + MediaPipe (пальцы) + YOLO-гитара (1 раз/сек).

Выход:
  output.avi    — размеченное видео
  frames.jsonl  — ПОТОКОВЫЙ лог: одна JSON-строка на кадр (рука, пальцы, струна/лад, геометрия)
  summary.json  — класс гитары (голосование), таймлайн классификации, события зажатий + MIDI-ноты
"""
import cv2
import json
import os
import time
from collections import Counter, deque

import numpy as np
import mediapipe as mp
from ultralytics import YOLO

# ============================== НАСТРОЙКИ ==============================
DEVICE = "cpu"
HAND_IMGSZ, POSE_IMGSZ = 640, 960
HAND_CONF, POSE_CONF, KP_CONF, CLS_CONF = 0.35, 0.30, 0.30, 0.25

HAND_PAD = 1.5                  # во сколько раз расширить бокс руки для кропа MediaPipe
POSE_STRIDE = 1                 # запускать pose каждый N-й кадр (2–3 ускоряет на CPU)
CLS_PERIOD_SEC = 1.0            # классификатор гитары — раз в секунду
FIRST_WIRE_IS_NUT = False       # True, если pose-модель помечает верхний порожек как fret_wire
NUT_SIDE_FALLBACK = "right"     # сторона головки грифа, если видно < 4 ладов
RECT_H = 240                    # высота выпрямленного грифа, условные px
STRINGS_6 = [6, 5, 4, 3, 2, 1]  # струны СВЕРХУ ВНИЗ на кадре (вид спереди, правша)
STRINGS_4 = [4, 3, 2, 1]        # бас.
V_MARGIN = 0.18                 # допуск выхода кончика за верх/низ грифа (доля высоты)
SMOOTH_WIN = 3                  # медианный фильтр координат кончиков (кадров)
MIN_STABLE_FRAMES = 3           # сколько кадров подряд держать (струна, лад) для события
SHOW_WINDOWS = True
SHOW_CROP_WINDOW = True

FINGERTIPS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
PRESS_FINGERS = ("index", "middle", "ring", "pinky")  # большой палец не считаем зажимающим
FINGER_COLORS = {"thumb": (160, 160, 255), "index": (0, 255, 0),
                 "middle": (255, 160, 0), "ring": (0, 160, 255), "pinky": (255, 0, 255)}
TUNING = {6: {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40},   # EADGBE, MIDI открытых струн
          4: {1: 43, 2: 38, 3: 33, 4: 28}}                # EADG (бас)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# ========================================================================


def put_ascii(img, text, org, scale=0.55, color=(255, 255, 255), thick=1):
    """cv2.putText не умеет кириллицу — безопасно заменяем не-ASCII символы."""
    cv2.putText(img, text.encode("ascii", "replace").decode(), org,
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def transform_points(M, pts):
    arr = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(arr, M).reshape(-1, 2)


def expand_bbox(xyxy, pad, w, h):
    x1, y1, x2, y2 = xyxy
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    bw, bh = (x2 - x1) * pad, (y2 - y1) * pad
    return (max(0, int(cx - bw / 2)), max(0, int(cy - bh / 2)),
            min(w, int(cx + bw / 2)), min(h, int(cy + bh / 2)))


# ---------------------- ГЕОМЕТРИЯ ГРИФА (YOLO-pose) ----------------------
def extract_fret_wires(res, pose_conf, kp_conf):
    """Из pose-результата: список ладов {top, bottom, mid, conf}.
    K>=2 keypoints: берём крайние по Y как концы проволоки.
    K==1 или низкая уверенность keypoints: fallback на вертикальные границы бокса."""
    wires = []
    if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
        return wires
    kxy = res.keypoints.xy.cpu().numpy()                     # (N, K, 2)
    kconf = res.keypoints.conf
    kconf = kconf.cpu().numpy() if kconf is not None else np.ones(kxy.shape[:2])
    for i in range(len(res.boxes)):
        if float(res.boxes.conf[i]) < pose_conf:
            continue
        pts = kxy[i]
        good = pts[kconf[i] >= kp_conf]
        if len(good) >= 2:
            top = good[np.argmin(good[:, 1])]
            bot = good[np.argmax(good[:, 1])]
        else:
            x1, y1, x2, y2 = res.boxes.xyxy[i].cpu().numpy()
            cx = (x1 + x2) / 2
            top, bot = np.array([cx, y1]), np.array([cx, y2])
        if np.linalg.norm(bot - top) < 5:
            continue
        wires.append({"top": top.astype(float), "bottom": bot.astype(float),
                      "mid": ((top + bot) / 2).astype(float),
                      "conf": round(float(res.boxes.conf[i]), 3)})
    return wires


def sort_wires_nut_first(wires, nut_side_fallback="right"):
    """Сортировка вдоль оси грифа (PCA) + определение стороны порожка:
    у головки грифа промежутки между ладами БОЛЬШЕ (мензура, 2^(-1/12))."""
    if len(wires) < 2:
        return wires
    mids = np.array([w["mid"] for w in wires])
    mean = mids.mean(axis=0)
    evals, evecs = np.linalg.eigh(np.cov((mids - mean).T))
    axis = evecs[:, np.argmax(evals)]
    t = (mids - mean) @ axis
    order = np.argsort(t)
    wires = [wires[i] for i in order]
    t = t[order]
    if len(wires) >= 4:
        gaps = np.diff(t)
        k = min(3, max(1, len(gaps) // 2))
        if gaps[:k].mean() < gaps[-k:].mean():   # начало — плотная сторона (корпус)
            wires = wires[::-1]
    else:
        if nut_side_fallback == "right" and wires[0]["mid"][0] < wires[-1]["mid"][0]:
            wires = wires[::-1]
    return wires


def build_fretboard(wires, rect_h=RECT_H, first_is_nut=FIRST_WIRE_IS_NUT):
    """Гомография квада (крайние лады) -> прямоугольник; границы ладов в rect-пространстве."""
    if len(wires) < 2:
        return None
    src = np.array([wires[0]["top"], wires[-1]["top"],
                    wires[-1]["bottom"], wires[0]["bottom"]], dtype=np.float32)
    rect_w = max(64.0, float(np.linalg.norm(wires[-1]["mid"] - wires[0]["mid"])))
    dst = np.array([[0, 0], [rect_w, 0], [rect_w, rect_h], [0, rect_h]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    Hinv = np.linalg.inv(H)
    u = transform_points(H, [w["mid"] for w in wires])[:, 0]
    u = np.maximum.accumulate(u)                 # защита от локальных перестановок из-за дрожания
    gaps = np.diff(u)
    if len(gaps) == 0 or np.median(gaps) <= 1e-3:
        return None
    if first_is_nut:
        bounds = list(u)                         # wires[0] — порожек
    else:
        nut_u = u[0] - gaps[0] * (2 ** (1 / 12))  # экстраполяция порожка по мензуре
        bounds = [nut_u] + list(u)
    bounds.append(bounds[-1] + (bounds[-1] - bounds[-2]) * (2 ** (-1 / 12)))  # последний лад
    return {"H": H, "Hinv": Hinv, "w": rect_w, "h": float(rect_h),
            "u": u, "bounds": np.array(bounds)}


def locate_on_fretboard(rect_xy, fb, n_strings, strings_map):
    """(u, v) -> {string, fret} или None, если палец вне грифа."""
    u, v = float(rect_xy[0]), float(rect_xy[1])
    h = fb["h"]
    if not (-V_MARGIN * h <= v <= (1 + V_MARGIN) * h):
        return None
    b = fb["bounds"]
    if u < b[0] or u >= b[-1]:
        return None
    fret = int(np.searchsorted(b, u, side="right"))      # лад 1..len(b)-1
    row = int(np.clip(v, 0, h - 1e-6) // (h / n_strings))
    row = min(max(row, 0), n_strings - 1)
    return {"string": int(strings_map[row]), "fret": fret}


# ---------------------- КЛАССИФИКАЦИЯ ГИТАРЫ (1 Гц) ----------------------
def classify_guitar(model, frame, conf_thr):
    """Поддерживает и classify-модель (probs), и detect-модель (boxes)."""
    imgsz = 224 if model.task == "classify" else 640
    r = model.predict(frame, imgsz=imgsz, device=DEVICE, verbose=False)[0]
    if r.probs is not None:                              # classification
        conf = float(r.probs.top1conf)
        if conf >= conf_thr:
            return r.names[int(r.probs.top1)], round(conf, 3), None
        return None, 0.0, None
    if r.boxes is not None and len(r.boxes):             # detection
        i = int(r.boxes.conf.argmax())
        conf = float(r.boxes.conf[i])
        if conf >= conf_thr:
            bbox = [round(float(v), 1) for v in r.boxes.xyxy[i].tolist()]
            return r.names[int(r.boxes.cls[i])], round(conf, 3), bbox
    return None, 0.0, None


def n_strings_for_class(name):
    s = (name or "").lower()
    return 4 if ("bass" in s or "бас" in s) else 6


# ---------------------- СОБЫТИЯ ЗАЖАТИЙ (временная стабильность) ----------------------
class PressTracker:
    """Регистрирует событие, только если набор (струна, лад) держится >= min_stable кадров."""
    def __init__(self, min_stable):
        self.min_stable = min_stable
        self.streak, self.first_seen = {}, {}
        self.events, self.current = [], None

    def update(self, t, keys):
        keys = set(keys)
        for k in list(self.streak):
            if k not in keys:
                del self.streak[k], self.first_seen[k]
        for k in keys:
            if k not in self.streak:
                self.streak[k] = 0
                self.first_seen[k] = t
            self.streak[k] += 1
        stable = frozenset(k for k, c in self.streak.items() if c >= self.min_stable)
        if self.current is not None and stable != self.current["keys"]:
            self._close(t)
        if self.current is None and stable:
            self.current = {"start": min(self.first_seen[k] for k in stable), "keys": stable}

    def _close(self, t):
        c = self.current
        if c is not None and t > c["start"]:
            self.events.append({"start_sec": round(c["start"], 3), "end_sec": round(t, 3),
                                "pressed": [{"string": s, "fret": f} for s, f in sorted(c["keys"])]})
        self.current = None

    def finish(self, t):
        self._close(t)

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
                print("Скачиваю hand_landmarker.task (~8 МБ)...")
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
        print(f"MediaPipe backend: {self.mode}")

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
        tips = set(FINGERTIPS.values())
        for i, p in enumerate(pts):
            cv2.circle(img, p, 3 if i in tips else 2,
                       (0, 0, 255) if i in tips else (0, 200, 255), -1)

    def close(self):
        if self.mode == "legacy":
            self._hands.close()
        else:
            self._landmarker.close()

# ============================== ОСНОВНОЙ ЦИКЛ ==============================
def run_pipeline(video_path, hand_model_path, guitar_model_path, pose_model_path,
                 output_video="output.avi", frames_jsonl="frames.jsonl", summary_json="summary.json"):
    print("=== PIPELINE: hand(YOLO) + frets(YOLO-pose) + fingers(MediaPipe) + guitar(1 Hz) ===")
    model_hand = YOLO(hand_model_path)
    model_pose = YOLO(pose_model_path)
    model_guitar = YOLO(guitar_model_path)
    if model_pose.task != "pose":
        raise ValueError(f"Fretboard model should be 'pose', but it is currently '{model_pose.task}'.")
    print(f"Задачи моделей: hand={model_hand.task}, frets={model_pose.task}, guitar={model_guitar.task}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Ошибка: не удалось открыть видео.")
        return
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    Hf = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = cv2.VideoWriter(output_video, cv2.VideoWriter_fourcc(*"MJPG"), fps, (W, Hf))
    if SHOW_WINDOWS:
        cv2.namedWindow("Pipeline", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Pipeline", 1280, 720)

    finger_tracker = MediaPipeFingers()

    tracker = PressTracker(MIN_STABLE_FRAMES)
    smooth = {name: deque(maxlen=SMOOTH_WIN) for name in FINGERTIPS}
    wires_cache, fb_cache = [], None
    guitar_name, guitar_conf, guitar_bbox = None, 0.0, None
    last_cls_t, votes, guitar_timeline = -1e9, Counter(), []
    frame_idx, t0 = 0, time.time()
    fjson = open(frames_jsonl, "w", encoding="utf-8")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            t = frame_idx / fps
            annotated = frame.copy()

            # --- 1) ГИТАРА: раз в CLS_PERIOD_SEC, между запусками — кэш ---
            if t - last_cls_t >= CLS_PERIOD_SEC:
                last_cls_t = t
                name, conf, bbox = classify_guitar(model_guitar, frame, CLS_CONF)
                guitar_timeline.append({"time_sec": round(t, 2), "class": name, "confidence": conf})
                if name:
                    guitar_name, guitar_conf, guitar_bbox = name, conf, bbox
                    votes[name] += conf                       # голосование, взвешенное по уверенности
                    if bbox:
                        x1, y1, x2, y2 = map(int, bbox)
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            n_strings = n_strings_for_class(guitar_name)
            strings_map = STRINGS_4 if n_strings == 4 else STRINGS_6

            # --- 2) РУКА: YOLO каждый кадр ---
            rh = model_hand.predict(frame, imgsz=HAND_IMGSZ, conf=HAND_CONF,
                                    device=DEVICE, verbose=False)[0]
            hand_box, hand_conf = None, 0.0
            if rh.boxes is not None and len(rh.boxes):
                i = int(rh.boxes.conf.argmax())
                hand_box = [float(v) for v in rh.boxes.xyxy[i].tolist()]
                hand_conf = float(rh.boxes.conf[i])
                x1, y1, x2, y2 = map(int, hand_box)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
                put_ascii(annotated, f"hand {hand_conf:.2f}", (x1, max(15, y1 - 8)), color=(0, 255, 255))

            # --- 3) ЛАДЫ: YOLO-pose каждый POSE_STRIDE-й кадр, между — кэш ---
            pose_refreshed = (frame_idx % POSE_STRIDE == 0)
            if pose_refreshed:
                rp = model_pose.predict(frame, imgsz=POSE_IMGSZ, conf=POSE_CONF,
                                        device=DEVICE, verbose=False)[0]
                wires = sort_wires_nut_first(extract_fret_wires(rp, POSE_CONF, KP_CONF), NUT_SIDE_FALLBACK)
                if len(wires) >= 2:
                    fb = build_fretboard(wires)
                    if fb is not None:
                        wires_cache, fb_cache = wires, fb
            wires, fb = wires_cache, fb_cache

            # --- 4) ПАЛЬЦЫ: MediaPipe на кропе руки -> глобальные координаты -> (струна, лад) ---
            fingers, presses, crop_vis = [], set(), None
            if hand_box is not None:
                bx1, by1, bx2, by2 = expand_bbox(hand_box, HAND_PAD, W, Hf)
                crop = frame[by1:by2, bx1:bx2]
                if crop.size and crop.shape[0] >= 40 and crop.shape[1] >= 40:
                    lms, crop_vis = finger_tracker.process(crop, int(t * 1000))
                    if lms is not None:
                        ch, cw = crop.shape[:2]
                        for fname, lid in FINGERTIPS.items():
                            lm = lms[lid]
                            gx, gy = bx1 + lm.x * cw, by1 + lm.y * ch   # кроп -> полный кадр
                            rec = {"finger": fname, "landmark_id": lid,
                                   "crop_norm": [round(lm.x, 4), round(lm.y, 4)],
                                   "global_xy": [round(gx, 1), round(gy, 1)],
                                   "rect_xy": None, "string": None, "fret": None,
                                   "on_fretboard": False, "press_candidate": False}
                            if fb is not None:
                                uv = transform_points(fb["H"], [(gx, gy)])[0]
                                smooth[fname].append(uv)
                                uv_s = np.median(np.array(smooth[fname]), axis=0)
                                rec["rect_xy"] = [round(float(uv_s[0]), 1), round(float(uv_s[1]), 1)]
                                loc = locate_on_fretboard(uv_s, fb, n_strings, strings_map)
                                if loc:
                                    rec.update(string=loc["string"], fret=loc["fret"], on_fretboard=True)
                                    if fname in PRESS_FINGERS:
                                        rec["press_candidate"] = True
                                        presses.add((loc["string"], loc["fret"]))
                            fingers.append(rec)
                            color = FINGER_COLORS[fname]
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
                num = ("nut" if i == 0 else str(i)) if FIRST_WIRE_IS_NUT else str(i + 1)
                put_ascii(annotated, num, (p1[0] - 6, max(12, p1[1] - 8)), 0.45, (255, 200, 0))
            if fb is not None:
                for r in range(1, n_strings):             # линии струн — через обратную гомографию
                    v = r * fb["h"] / n_strings
                    a, b = transform_points(fb["Hinv"], [(fb["bounds"][0], v), (fb["w"], v)])
                    cv2.line(annotated, tuple(a.astype(int)), tuple(b.astype(int)), (170, 170, 170), 1)
                if not FIRST_WIRE_IS_NUT:                 # оценённый порожек
                    a, b = transform_points(fb["Hinv"], [(fb["bounds"][0], 0), (fb["bounds"][0], fb["h"])])
                    cv2.line(annotated, tuple(a.astype(int)), tuple(b.astype(int)), (0, 255, 255), 1)
                    put_ascii(annotated, "nut~", (int(a[0]) - 10, max(12, int(a[1]) - 8)), 0.45, (0, 255, 255))
            banner = f"Guitar: {guitar_name or '...'} {guitar_conf:.2f} | strings={n_strings} | t={t:.2f}s"
            cv2.rectangle(annotated, (5, 5), (10 + 8 * len(banner), 32), (0, 0, 0), -1)
            put_ascii(annotated, banner, (10, 26), 0.6, (255, 255, 255))

            # --- 6) ПОТОКОВЫЙ JSONL ---
            geom = "cached"
            if pose_refreshed and fb is not None:
                geom = {"n_wires": len(wires),
                        "wires": [{"top": [round(float(x), 1) for x in w["top"]],
                                   "bottom": [round(float(x), 1) for x in w["bottom"]],
                                   "conf": w["conf"]} for w in wires],
                        "homography": fb["H"].round(5).tolist(),
                        "fret_bounds": fb["bounds"].round(1).tolist(),
                        "rect_size": [round(fb["w"], 1), fb["h"]]}
            entry = {"frame": frame_idx, "time_sec": round(t, 3),
                     "guitar": {"class": guitar_name, "confidence": guitar_conf,
                                "bbox": guitar_bbox, "n_strings": n_strings},
                     "hand": {"bbox": [round(v, 1) for v in hand_box],
                              "confidence": round(hand_conf, 3)} if hand_box else None,
                     "fretboard": geom,
                     "fingers": fingers,
                     "press_candidates": [{"string": s, "fret": f} for s, f in sorted(presses)]}
            fjson.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if frame_idx % 30 == 0:
                fjson.flush()

            # --- 7) ВИДЕО / ОКНА ---
            out.write(annotated)
            if SHOW_WINDOWS:
                cv2.imshow("Pipeline", annotated)
                if SHOW_CROP_WINDOW and crop_vis is not None:
                    scale = min(2.0, 640.0 / max(1, crop_vis.shape[1]))
                    cv2.imshow("Hand crop + MediaPipe", cv2.resize(crop_vis, None, fx=scale, fy=scale))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if frame_idx % 150 == 0:
                print(f"[{t:.1f}s] кадр {frame_idx}/{total} | гитара: {guitar_name} | кандидатов: {len(presses)}")
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
            midi = TUNING[n_final][p["string"]] + p["fret"]
            p["midi_note"] = midi
            p["note"] = NOTE_NAMES[midi % 12] + str(midi // 12 - 1)
    summary = {"video": video_path, "frames_processed": frame_idx, "source_fps": fps,
               "processing_time_sec": round(time.time() - t0, 1),
               "guitar_class_final": final_class, "guitar_votes": dict(votes),
               "guitar_timeline": guitar_timeline, "n_strings": n_final,
               "press_events": tracker.events,
               "config": {"FIRST_WIRE_IS_NUT": FIRST_WIRE_IS_NUT, "POSE_STRIDE": POSE_STRIDE,
                          "CLS_PERIOD_SEC": CLS_PERIOD_SEC, "MIN_STABLE_FRAMES": MIN_STABLE_FRAMES,
                          "strings_top_to_bottom": STRINGS_4 if n_final == 4 else STRINGS_6,
                          "tuning_midi": TUNING[n_final]}}
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nГотово. Класс гитары: {final_class}. Событий зажатия: {len(tracker.events)}")
    print(f"Видео: {os.path.abspath(output_video)}\nJSONL: {os.path.abspath(frames_jsonl)}"
          f"\nSummary: {os.path.abspath(summary_json)}")


if __name__ == "__main__":
    run_pipeline(
        video_path="ссылка\на\видео.mp4",
        hand_model_path="hand_model.pt",
        guitar_model_path="guitar_model.pt",
        pose_model_path="fretboard_recognition.pt",
    )

