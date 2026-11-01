from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models import BorrowRequestStatus

class BorrowRequestCreateIn(BaseModel):
    title: str
    category: str
    description: str = ""
    max_price_per_day: Optional[float] = None
    needed_from: Optional[datetime] = None
    needed_until: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = 10.0
    address_text: str = ""

class BorrowRequestUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    max_price_per_day: Optional[float] = None
    status: Optional[BorrowRequestStatus] = None

class BorrowRequestOut(BaseModel):
    id: str
    borrower_id: str
    borrower_name: Optional[str] = None
    borrower_trust_score: Optional[float] = 50.0
    title: str
    category: str
    description: str
    max_price_per_day: Optional[float] = None
    needed_from: Optional[datetime] = None
    needed_until: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float
    address_text: str
    status: BorrowRequestStatus
    listing_id: Optional[str] = None
    lender_id: Optional[str] = None
    returned_at: Optional[datetime] = None
    disputed_at: Optional[datetime] = None
    distance_km: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
