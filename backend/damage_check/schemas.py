from datetime import datetime, timezone
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

VIEWS = ("front", "back", "left", "right", "top", "bottom")
PHASES = ("before", "after")

Phase = Literal["before", "after"]
View = Literal["front", "back", "left", "right", "top", "bottom"]
Confidence = Literal["low", "medium", "high"]
CheckStatus = Literal["collecting", "processing", "done", "failed"]
Overall = Literal["clear", "possible_damage", "needs_review"]

FINDING_TYPES = ("scratch", "dent", "crack", "stain", "tear", "missing_part", "other")
LOCATIONS = (
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
    "unknown",
)

DISCLAIMER = "Warning, not a verdict. Only external, visible changes are checked."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Finding(BaseModel):
    type: str = "other"
    description: str = ""
    location: str = "unknown"


class ViewResult(BaseModel):
    view: str
    comparable: bool = True
    damage_detected: bool = False
    confidence: Confidence = "low"
    findings: List[Finding] = Field(default_factory=list)
    note: str = ""
    error: Optional[str] = None


class DamageReport(BaseModel):
    overall: Overall
    views: List[ViewResult] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    model: str = ""
    generated_at: datetime = Field(default_factory=utcnow)


class Decision(BaseModel):
    decision: Literal["confirmed", "dismissed"]
    comment: Optional[str] = None
    decided_by: str
    decided_at: datetime = Field(default_factory=utcnow)


class CheckRecord(BaseModel):
    """Everything the host app must persist for one check (a single JSON blob
    is enough). Photos are stored separately via the storage interface."""
    id: str
    request_id: Optional[str] = None
    lender_id: str
    borrower_id: str
    item_class: Optional[str] = None
    status: CheckStatus = "collecting"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    report: Optional[DamageReport] = None
    decision: Optional[Decision] = None
    error: Optional[str] = None


class CheckView(BaseModel):
    """What API clients receive."""
    id: str
    request_id: Optional[str] = None
    lender_id: str
    borrower_id: str
    item_class: Optional[str] = None
    status: CheckStatus
    created_at: datetime
    updated_at: datetime
    before_views: List[str] = Field(default_factory=list)
    after_views: List[str] = Field(default_factory=list)
    missing_before: List[str] = Field(default_factory=list)
    missing_after: List[str] = Field(default_factory=list)
    report: Optional[DamageReport] = None
    decision: Optional[Decision] = None
    error: Optional[str] = None


class CreateCheckRequest(BaseModel):
    request_id: Optional[Union[str, int]] = None
    lender_id: Union[str, int]
    borrower_id: Union[str, int]
    item_class: Optional[str] = Field(default=None, max_length=100)


class DecisionRequest(BaseModel):
    decision: Literal["confirmed", "dismissed"]
    comment: Optional[str] = Field(default=None, max_length=1000)


class PhotoAck(BaseModel):
    check_id: str
    phase: Phase
    view: View
    size_bytes: int
