from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: str
    notification_type: str
    title: str
    message: str
    link_url: str
    borrow_request_id: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCountOut(BaseModel):
    unread_count: int


class DisputeCreateIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
