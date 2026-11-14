from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models import BorrowRequestStatus, HandoverStatus

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
    handover_status: HandoverStatus = HandoverStatus.not_applicable
    handover_marked_at: Optional[datetime] = None
    handover_confirmed_at: Optional[datetime] = None
    handover_confirmed_by: Optional[str] = None
    handover_issue_description: Optional[str] = None
    handover_issue_reported_at: Optional[datetime] = None
    handover_photos: Optional[List[str]] = []
    handover_confirmed_photos: Optional[List[str]] = []
    return_photos: Optional[List[str]] = []
    damage_check_id: Optional[str] = None
    damage_link_token: Optional[str] = None
    return_confirmed_at: Optional[datetime] = None
    return_confirmed_by: Optional[str] = None
    borrowing_started_at: Optional[datetime] = None
    return_due_at: Optional[datetime] = None
    lender_rating: Optional[int] = None
    borrower_rating: Optional[int] = None
    lender_rating_comment: Optional[str] = None
    borrower_rating_comment: Optional[str] = None
    lender_rated_at: Optional[datetime] = None
    borrower_rated_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    distance_km: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
