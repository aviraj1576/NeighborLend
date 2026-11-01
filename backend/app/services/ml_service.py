from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parents[2] / "ai_service" / "best_model.pt"

_model = None
_model_loaded = False


def _get_model():
    global _model, _model_loaded
    if _model_loaded:
        return _model

    _model_loaded = True
    try:
        from ultralytics import YOLO
        _model = YOLO(str(MODEL_PATH))
    except Exception as exc:
        # Keep the API and photo upload flow available when model weights or
        # optional inference dependencies are unavailable.
        print(f"Object detection unavailable: {exc}")
    return _model


def detect_objects(image_bytes: bytes):
    model = _get_model()
    if model is None:
        return []

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp:
        temp.write(image_bytes)
        temp_path = temp.name

    try:
        results = model(temp_path, conf=0.25, verbose=False)

        detections = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])

                detections.append({
                    "class": model.names[class_id],
                    "confidence": round(confidence, 4)
                })

        return detections

    finally:
        Path(temp_path).unlink(missing_ok=True)
