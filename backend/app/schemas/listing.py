from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from app.models import ListingStatus

class ListingCreateIn(BaseModel):
    name: str
    category: str
    description: str = ""
    years_owned: float = 0
    price_bought: float = 0
    price_per_day: float
    min_price_per_day: Optional[float] = None
    security_deposit: float = 0
    lending_radius_km: float = 10
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_text: str = ""
    photo_urls: List[str] = Field(default_factory=list)
    ai_label: Optional[str] = None
    ai_confidence: Optional[float] = None

    @field_validator('min_price_per_day')

    def validate_min_price(cls, v, values):
        if v is not None and 'price_per_day' in values.data and v > values.data['price_per_day']:
            raise ValueError("min_price_per_day cannot be greater than price_per_day")
        return v

class ListingUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_per_day: Optional[float] = None
    min_price_per_day: Optional[float] = None
    security_deposit: Optional[float] = None
    lending_radius_km: Optional[float] = None
    status: Optional[ListingStatus] = None

class OwnerOut(BaseModel):
    id: str
    name: str
    username: str
    trust_score: float = 50.0
    rating: float = 0.0
    rating_count: int = 0

class ListingOut(BaseModel):
    id: str
    owner_id: str
    owner_name: Optional[str] = None
    owner_username: Optional[str] = None
    owner: Optional[OwnerOut] = None
    owner_trust_score: Optional[float] = 50.0
    owner_avg_rating: Optional[float] = 0.0
    owner_rating_count: Optional[int] = 0
    name: str
    title: Optional[str] = None
    category: str
    description: str
    years_owned: float
    price_bought: float
    price_per_day: float
    security_deposit: float
    lending_radius_km: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_text: str = ""
    address: Optional[str] = None
    status: ListingStatus
    moderation_reason: Optional[str] = None
    ai_label: Optional[str] = None
    ai_confidence: Optional[float] = None
    photos: List[str] = []
    is_currently_rented: bool = False
    distance_km: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True

class SuggestPriceIn(BaseModel):
    purchase_price: Optional[float] = None
    original_price: Optional[float] = None
    price_bought: Optional[float] = None
    age_years: Optional[float] = None
    item_age: Optional[float] = None
    years_owned: Optional[float] = None
    category: Optional[str] = "Other"

    def get_purchase_price(self) -> float:
        for val in (self.purchase_price, self.original_price, self.price_bought):
            if val is not None:
                return float(val)
        return 0.0

    def get_age_years(self) -> float:
        for val in (self.age_years, self.item_age, self.years_owned):
            if val is not None:
                return float(val)
        return 0.0

class SuggestPriceOut(BaseModel):
    current_value: float
    daily_rent: float
    security_deposit: float
    suggested_price_per_day: float
    current_value_estimate: float
    daily_rate_used: float = 0.04
    explanation: str = ""

