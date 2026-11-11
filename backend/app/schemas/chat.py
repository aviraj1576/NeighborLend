from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.models import OfferStatus

class ParticipantOut(BaseModel):
    id: str
    name: str
    username: str
    avatar_url: Optional[str] = None
    trust_score: Optional[float] = 50.0

    model_config = ConfigDict(from_attributes=True)

class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_name: Optional[str] = None
    sender_username: Optional[str] = None
    content: str
    is_system: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MessageCreateIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

class OfferOut(BaseModel):
    id: str
    conversation_id: str
    listing_id: str
    sender_id: str
    sender_name: Optional[str] = None
    sender_username: Optional[str] = None
    daily_price: float
    start_date: datetime
    end_date: datetime
    total_cost: float
    borrower_id: Optional[str] = None
    lender_id: Optional[str] = None
    daily_rate_paise: Optional[int] = None
    rental_fee_paise: Optional[int] = None
    security_deposit_paise: Optional[int] = None
    total_amount_paise: Optional[int] = None
    message: Optional[str] = None
    status: OfferStatus
    parent_offer_id: Optional[str] = None
    borrow_request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class OfferCreateIn(BaseModel):
    listing_id: str
    daily_price: float = Field(..., gt=0, description="Proposed daily rental price in INR")
    start_date: datetime
    end_date: datetime
    message: Optional[str] = Field(None, max_length=500)

class OfferCounterIn(BaseModel):
    listing_id: str
    daily_price: float = Field(..., gt=0, description="Counter daily rental price in INR")
    start_date: datetime
    end_date: datetime
    message: Optional[str] = Field(None, max_length=500)

class ConversationCreateIn(BaseModel):
    lender_id: str
    initial_message: Optional[str] = Field(None, max_length=1000)

class ConversationSummaryOut(BaseModel):
    id: str
    borrower: ParticipantOut
    lender: ParticipantOut
    other_participant: ParticipantOut
    is_borrower: bool
    last_message: Optional[MessageOut] = None
    active_offer: Optional[OfferOut] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationDetailOut(BaseModel):
    id: str
    borrower: ParticipantOut
    lender: ParticipantOut
    is_borrower: bool
    messages: List[MessageOut] = []
    offers: List[OfferOut] = []
    active_offer: Optional[OfferOut] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
