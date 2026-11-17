import sys
from pathlib import Path
from fastapi import APIRouter, UploadFile, File
from app.config import get_settings
from app.schemas.ai import AIIdentifyOut
from app.services.ai_identifier import identify_item, _get_model, YOLO_AVAILABLE

router = APIRouter()

@router.post("/identify", response_model=AIIdentifyOut)
async def identify(image: UploadFile = File(...)):
    contents = await image.read()
    return identify_item(contents)

@router.get("/status")
def ai_status():
    settings = get_settings()
    model_path = Path(settings.ai_model_path_abs)
    model = _get_model()
    return {
        "yolo_library_available": YOLO_AVAILABLE,
        "configured_ai_model_path": settings.ai_model_path,
        "resolved_model_path": str(model_path),
        "file_exists": model_path.is_file(),
        "file_size": model_path.stat().st_size if model_path.is_file() else None,
        "model_loaded": model is not None,
        "python_version": sys.version,
    }
