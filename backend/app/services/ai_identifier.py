import os
import io
from app.config import get_settings

settings = get_settings()

try:
    from ultralytics import YOLO
    from PIL import Image
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

_model = None

CLASS_MAP = {
    "bicycle": "Bicycle",
    "book": "Book",
    "drill": "Drill",
    "hammer": "Hammer",
    "headphones": "Headphones",
    "ladder": "Ladder"
}

def _get_model():
    global _model
    if not YOLO_AVAILABLE:
        return None
    if _model is None and os.path.exists(settings.ai_model_path):
        try:
            _model = YOLO(settings.ai_model_path)
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
    return _model

def identify_item(image_bytes: bytes) -> dict:
    model = _get_model()
    if model is None:
        return {
            "model_available": False,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": "AI model not available on the server."
        }
    
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = model(image, verbose=False)
        
        predictions = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = model.names[cls_id]
                
                if conf >= settings.ai_confidence_threshold:
                    mapped_label = CLASS_MAP.get(label.lower(), label)
                    predictions.append({"label": mapped_label, "confidence": conf})
        
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        
        suggested_category = None
        suggested_name = None
        if predictions:
            best_pred = predictions[0]
            suggested_category = best_pred["label"]
            suggested_name = best_pred["label"]
            msg = f"Identified as {best_pred['label']} ({int(best_pred['confidence']*100)}% confidence)"
        else:
            msg = "Could not identify item clearly."
            
        return {
            "model_available": True,
            "predictions": predictions,
            "suggested_category": suggested_category,
            "suggested_name": suggested_name,
            "message": msg
        }
    except Exception as e:
        return {
            "model_available": True,
            "predictions": [],
            "suggested_category": None,
            "suggested_name": None,
            "message": f"Error processing image: {str(e)}"
        }
