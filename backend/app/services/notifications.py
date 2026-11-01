from typing import Optional

from sqlalchemy.orm import Session

from app.models import Notification


def create_notification(
    db: Session,
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    link_url: str,
    borrow_request_id: Optional[str] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        link_url=link_url,
        borrow_request_id=borrow_request_id,
    )
    db.add(notification)
    return notification
