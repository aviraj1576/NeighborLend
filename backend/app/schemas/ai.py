from typing import Optional
from pydantic import BaseModel, ConfigDict

class AIPrediction(BaseModel):
    label: str
    confidence: float

class AIIdentifyOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_available: bool
    predictions: list[AIPrediction] = []
    suggested_category: Optional[str] = None
    suggested_name: Optional[str] = None
    message: str
