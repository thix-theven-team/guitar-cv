from guitarcv_restapi.core import settings


def classify_guitar(models, frame, conf_thr):
    """Поддерживает и classify-модель (probs), и detect-модель (boxes)."""
    imgsz = 224 if models.model_guitar.task == "classify" else 640
    r = models.model_guitar.predict(frame, imgsz=imgsz, device=settings.ml_pipeline_settings.device, verbose=False)[0]

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
