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
    onnx_path = model_path.with_suffix(".onnx")
    from app.services.ai_identifier import _get_onnx_session, _model
    onnx_sess = _get_onnx_session()
    return {
        "yolo_library_available": YOLO_AVAILABLE,
        "configured_ai_model_path": settings.ai_model_path,
        "resolved_model_path": str(model_path),
        "file_exists": model_path.is_file(),
        "onnx_file_exists": onnx_path.is_file(),
        "onnx_loaded": onnx_sess is not None,
        "pytorch_loaded": _model is not None,
        "python_version": sys.version,
    }
