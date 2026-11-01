from fastapi import APIRouter, UploadFile, File
from app.schemas.ai import AIIdentifyOut
from app.services.ai_identifier import identify_item

router = APIRouter()

@router.post("/identify", response_model=AIIdentifyOut)
async def identify(image: UploadFile = File(...)):
    contents = await image.read()
    return identify_item(contents)
