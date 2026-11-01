from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.storage_service import save_upload_from_bytes
from app.services.ml_service import detect_objects

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Uploading must still work when the optional model is missing, fails to
    # load, or cannot process a particular image.
    try:
        detections = detect_objects(image_bytes)
    except Exception:
        detections = []

    url = save_upload_from_bytes(
        image_bytes,
        file.filename,
        file.content_type,
        "images"
    )

    best_detection = max(
        detections,
        key=lambda x: x["confidence"],
        default=None
    )

    return {
        "url": url,
        "ai_label": best_detection["class"] if best_detection else None,
        "ai_confidence": best_detection["confidence"] if best_detection else None,
        "detections": detections
    }
