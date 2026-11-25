import cv2
import numpy as np


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
