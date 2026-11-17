from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.models import User
from app.services.auth import get_current_user

from app.services.storage_service import save_upload_from_bytes
from app.services.ml_service import detect_objects

router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if not (file.content_type or "").lower().startswith("image/"):
        raise HTTPException(status_code=415, detail="Please upload an image file.")
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
        "images",
        require_supabase=True,
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
