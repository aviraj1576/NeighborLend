
import io
import logging
import os
import re
from pathlib import Path
from threading import Lock

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLOE
    from PIL import Image, UnidentifiedImageError

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

_model = None
_model_lock = Lock()

# Exclude dumbbells from application predictions
EXCLUDED_CLASSES = {"dumbbell", "dumbbells"}

# Display names for supported categories
CLASS_MAP = {
    "bicycle": "Bicycle",
    "book": "Book",
    "drill": "Drill",
    "electric_drill": "Drill",
    "hammer": "Hammer",
    "headphones": "Headphones",
    "ladder": "Ladder",
}


def normalize_class_name(name: str) -> str:
    """Normalize names to detect excluded classes."""
    return re.sub(r"[\s_-]+", "", str(name).strip().lower())


def get_allowed_classes(model):
    """Preserve original class IDs while excluding dumbbells."""
    return [
        int(class_id)
        for class_id, name in model.names.items()
        if normalize_class_name(name)
        not in EXCLUDED_CLASSES
    ]


def _get_model():
    """Load the trained YOLOE checkpoint once."""
    global _model

    if not YOLO_AVAILABLE:
        logger.error("YOLOE or Pillow is not installed")
        return None

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        model_path = Path(settings.ai_model_path_abs)

        if not model_path.is_file():
            logger.error("Model not found: %s", model_path)
            return None

        try:
            loaded = YOLOE(str(model_path))

            if not loaded.names:
                raise ValueError("Checkpoint contains no class names")

            allowed = get_allowed_classes(loaded)

            if not allowed:
                raise ValueError("No supported classes available")

            _model = loaded

            logger.info(
                "YOLOE loaded: %d trained classes, %d active classes",
                len(loaded.names),
                len(allowed),
            )

        except Exception:
            logger.exception("Failed to load YOLOE checkpoint")
            return None

    return _model


def identify_item(image_bytes: bytes) -> dict:
    """Identify rental objects using trained YOLOE."""
    model = _get_model()

    if model is None:
        return {
            "model_available": False,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": "AI model not available on the server.",
        }

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            image = img.convert("RGB")

        allowed_classes = get_allowed_classes(model)

        # Exclude dumbbells at the inference level
        results = model.predict(
            source=image,
            imgsz=640,
            conf=settings.ai_confidence_threshold,
            classes=allowed_classes,
            verbose=False,
        )

        predictions = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                conf = float(box.conf.item())
                cls_id = int(box.cls.item())
                label = str(model.names[cls_id])

                # Second filtering layer for safety
                if normalize_class_name(label) in EXCLUDED_CLASSES:
                    continue

                if conf < settings.ai_confidence_threshold:
                    continue

                mapped_label = CLASS_MAP.get(
                    label.lower().replace(" ", "_"),
                    label.replace("_", " ").title(),
                )

                predictions.append({
                    "label": mapped_label,
                    "confidence": conf,
                })

        predictions.sort(
            key=lambda item: item["confidence"],
            reverse=True,
        )

        if predictions:
            best = predictions[0]
            suggested_category = best["label"]
            suggested_name = best["label"]

            message = (
                f"Identified as {best['label']} "
                f"({int(best['confidence'] * 100)}% confidence)"
            )
        else:
            suggested_category = None
            suggested_name = None
            message = "Could not identify a supported item clearly."

        return {
            "model_available": True,
            "predictions": predictions,
            "suggested_category": suggested_category,
            "suggested_name": suggested_name,
            "message": message,
        }

    except (UnidentifiedImageError, OSError, ValueError):
        logger.exception("Invalid image or inference input")
        return {
            "model_available": True,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": "Unable to process the supplied image.",
        }

    except Exception:
        logger.exception("YOLOE inference failed")
        return {
            "model_available": True,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": "Error processing image.",
        }
