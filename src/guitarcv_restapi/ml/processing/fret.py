import cv2
import numpy as np

from guitarcv_restapi.core import settings
from guitarcv_restapi.ml.utils import (
    transform_points
)


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


def build_fretboard(
    wires,
    rect_h=settings.ml_pipeline_settings.rect_h,
    first_is_nut=settings.ml_pipeline_settings.first_wire_is_nut
):
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
    if not (-settings.ml_pipeline_settings.v_margin * h <= v <= (1 + settings.ml_pipeline_settings.v_margin) * h):
        return None
    b = fb["bounds"]
    if u < b[0] or u >= b[-1]:
        return None
    fret = int(np.searchsorted(b, u, side="right"))      # лад 1..len(b)-1
    row = int(np.clip(v, 0, h - 1e-6) // (h / n_strings))
    row = min(max(row, 0), n_strings - 1)

    return {"string": int(strings_map[row]), "fret": fret}
