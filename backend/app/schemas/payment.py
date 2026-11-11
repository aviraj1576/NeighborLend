from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    booking_id: UUID


class VerifyPayment(PaymentInput):
    order_id: str = Field(min_length=1, max_length=128)
    payment_id: str = Field(min_length=1, max_length=128)
    signature: str = Field(min_length=64, max_length=64)


class DemoPayment(PaymentInput):
    outcome: Literal["success", "failed", "pending", "cancelled"] = "success"
    payment_id: str | None = Field(default=None, max_length=128)


class RefundAction(PaymentInput):
    demo_outcome: Literal["processed", "pending", "failed"] = "processed"
    retry_failed: bool = False
    gateway_refund_approved: bool = Field(default=False, strict=True)


class Claim(PaymentInput):
    claimed_deduction_paise: int = Field(strict=True, ge=0, le=1_000_000_000)
    reason: str = Field(min_length=1, max_length=2000)
    inspection_id: UUID | None = None
    cv_run_id: UUID | None = None
    assessment_id: UUID | None = None


class ClaimResponse(PaymentInput):
    accepted: bool
    claim_version: int = Field(strict=True, ge=1)
    notes: str = Field(default="", max_length=2000)


class Resolution(PaymentInput):
    approved_deduction_paise: int = Field(strict=True, ge=0, le=1_000_000_000)
    reason: str = Field(default="", max_length=2000)


class IssueResolution(PaymentInput):
    action: Literal["continue", "cancel", "return"]
    reason: str = Field(min_length=1, max_length=2000)
