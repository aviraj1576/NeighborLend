
import io
import gc
import logging
import platform
import ctypes
import re
import types
from pathlib import Path
from threading import Lock

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    import torch
    torch.set_num_threads(1)
    from ultralytics import YOLOE
    from PIL import Image, UnidentifiedImageError

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    torch = None

_model = None
_model_lock = Lock()
_onnx_session = None
_onnx_lock = Lock()

def _trim_memory():
    gc.collect()
    if platform.system() == "Linux":
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

YOLOE_NAMES = {
    0: 'electric_drill', 1: 'screwdriver', 2: 'wrench', 3: 'hammer',
    4: 'smartphone', 5: 'laptop', 6: 'camera', 7: 'headphones',
    8: 'keyboard', 9: 'drone', 10: 'bicycle', 11: 'scooter',
    12: 'tent', 13: 'umbrella', 14: 'basketball', 15: 'dumbbell',
    16: 'barbell', 17: 'microwave', 18: 'kettle', 19: 'blender',
    20: 'backpack', 21: 'camping_chair', 22: 'suitcase', 23: 'guitar'
}

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
    "smartphone": "Smartphone",
    "laptop": "Laptop",
    "camera": "Camera",
    "keyboard": "Keyboard",
    "drone": "Drone",
    "scooter": "Scooter",
    "tent": "Tent",
    "umbrella": "Umbrella",
    "basketball": "Basketball",
    "barbell": "Barbell",
    "microwave": "Microwave",
    "kettle": "Kettle",
    "blender": "Blender",
    "backpack": "Backpack",
    "camping_chair": "Camping Chair",
    "suitcase": "Suitcase",
    "guitar": "Guitar",
    "screwdriver": "Screwdriver",
    "wrench": "Wrench",
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

            if len(allowed) != 23:
                raise ValueError(
                    f"Expected 23 active rental classes, got {len(allowed)}. "
                    "Set AI_MODEL_PATH to ai_service/models/neighborlend_yoloe_best.pt."
                )

            # Bind forward_fuse method for any fused BNContrastiveHead modules to prevent
            # "missing 1 required positional argument: 'w'" during inference.
            if hasattr(loaded, "model") and hasattr(loaded.model, "modules"):
                for mod in loaded.model.modules():
                    if "BNContrastiveHead" in type(mod).__name__:
                        if hasattr(mod, "forward_fuse"):
                            mod.forward = types.MethodType(type(mod).forward_fuse, mod)

            _model = loaded

            logger.info(
                "YOLOE loaded from %s: %d trained classes, %d active classes",
                model_path.name,
                len(loaded.names),
                len(allowed),
            )

        except Exception:
            logger.exception("Failed to load YOLOE checkpoint")
            return None

    return _model


def _ensure_onnx_model():
    """Ensure static ONNX graph exists, exporting once if missing."""
    model_path = Path(settings.ai_model_path_abs)
    target_onnx = model_path.with_suffix(".onnx")
    if target_onnx.is_file():
        return target_onnx
    pt_file = model_path if model_path.suffix == ".pt" else model_path.with_suffix(".pt")
    if not pt_file.is_file():
        pt_file = model_path.parent / "neighborlend_yoloe_best.pt"
    if not pt_file.is_file():
        return None
    try:
        from ultralytics import YOLOE
        loaded = YOLOE(str(pt_file))
        if hasattr(loaded, "model") and hasattr(loaded.model, "modules"):
            for mod in loaded.model.modules():
                if "BNContrastiveHead" in type(mod).__name__:
                    if hasattr(mod, "forward_fuse"):
                        mod.forward = types.MethodType(type(mod).forward_fuse, mod)
        loaded.export(format="onnx", imgsz=640, dynamic=False, simplify=False)
        if target_onnx.is_file():
            logger.info("Auto-exported static ONNX model to %s", target_onnx.name)
            return target_onnx
    except Exception as exc:
        logger.warning("ONNX auto-export skipped: %s", exc)
    return None


def _get_onnx_session():
    global _onnx_session
    if _onnx_session is not None:
        return _onnx_session
    try:
        import onnxruntime as ort
        model_path = Path(settings.ai_model_path_abs)
        candidates = [
            model_path.with_suffix(".onnx"),
            model_path.parent / "neighborlend_yoloe_best.onnx",
        ]
        onnx_file = next((c for c in candidates if c.is_file()), None)
        if onnx_file is None:
            onnx_file = _ensure_onnx_model()

        if onnx_file is not None and onnx_file.is_file():
            with _onnx_lock:
                if _onnx_session is not None:
                    return _onnx_session
                opts = ort.SessionOptions()
                opts.enable_cpu_mem_arena = False
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                _onnx_session = ort.InferenceSession(
                    str(onnx_file), opts, providers=["CPUExecutionProvider"]
                )
                logger.info("Loaded ONNX session from %s (static memory mode)", onnx_file.name)
    except Exception as exc:
        logger.warning("ONNX runtime session init skipped: %s", exc)
    return _onnx_session


def _run_onnx_inference(session, image_bytes: bytes) -> list[dict]:
    import numpy as np

    with Image.open(io.BytesIO(image_bytes)) as img:
        resized = img.convert("RGB").resize((640, 640))
    arr = np.ascontiguousarray(np.array(resized, dtype=np.float32).transpose(2, 0, 1) / 255.0)
    arr = np.expand_dims(arr, 0)

    input_name = session.get_inputs()[0].name
    out = session.run(None, {input_name: arr})[0][0].T  # Shape: (8400, 28)
    boxes = out[:, :4]
    scores = out[:, 4:]

    max_scores = np.max(scores, axis=1)
    best_classes = np.argmax(scores, axis=1)

    conf_thresh = settings.ai_confidence_threshold
    mask = max_scores >= conf_thresh

    filtered_boxes = boxes[mask]
    filtered_scores = max_scores[mask]
    filtered_classes = best_classes[mask]

    if len(filtered_scores) == 0:
        return []

    x = filtered_boxes[:, 0] - filtered_boxes[:, 2] / 2
    y = filtered_boxes[:, 1] - filtered_boxes[:, 3] / 2
    w = filtered_boxes[:, 2]
    h = filtered_boxes[:, 3]
    xywh = np.stack([x, y, w, h], axis=1).tolist()
    scores_list = [float(s) for s in filtered_scores]

    try:
        import cv2
        indices = cv2.dnn.NMSBoxes(xywh, scores_list, conf_thresh, 0.45)
        if hasattr(indices, "flatten"):
            keep_indices = indices.flatten()
        else:
            keep_indices = [i[0] if isinstance(i, (list, tuple)) else i for i in indices]
    except Exception:
        keep_indices = range(len(scores_list))

    predictions = []
    for idx in keep_indices:
        cls_id = int(filtered_classes[idx])
        conf = float(filtered_scores[idx])
        label = YOLOE_NAMES.get(cls_id, "")
        if normalize_class_name(label) in EXCLUDED_CLASSES:
            continue
        mapped_label = CLASS_MAP.get(label.lower().replace(" ", "_"), label.replace("_", " ").title())
        predictions.append({
            "label": mapped_label,
            "confidence": conf,
        })

    predictions.sort(key=lambda item: item["confidence"], reverse=True)
    return predictions


def identify_item(image_bytes: bytes) -> dict:
    """Identify rental objects using trained YOLOE."""
    global _model

    # Use fast, static-memory ONNX session if available and _model is not explicitly set/mocked
    onnx_sess = None
    if _model is None:
        onnx_sess = _get_onnx_session()

    if onnx_sess is None and _get_model() is None:
        return {
            "model_available": False,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": "AI model not available on the server.",
        }

    try:
        if onnx_sess is not None:
            predictions = _run_onnx_inference(onnx_sess, image_bytes)
        else:
            model = _get_model()
            with Image.open(io.BytesIO(image_bytes)) as img:
                image = img.convert("RGB")

            allowed_classes = get_allowed_classes(model)

            # Exclude dumbbells at the inference level with minimal memory overhead
            if torch is not None:
                with torch.inference_mode():
                    results = model.predict(
                        source=image,
                        imgsz=640,
                        conf=settings.ai_confidence_threshold,
                        classes=allowed_classes,
                        verbose=False,
                    )
            else:
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

        _trim_memory()

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
