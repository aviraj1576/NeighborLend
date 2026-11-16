from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import get_current_user
from app.services.trust_score import refresh_user_trust_score

router = APIRouter()


def _score_out(db: Session, user: User):
    details = refresh_user_trust_score(db, user)
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.id,
        "name": user.name,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "member_since": user.created_at,
        "score": details["score"],
        "rating_score": details["rating_score"],
        "reliability_score": details["reliability_score"],
        "experience_score": details["experience_score"],
        "verification_score": details["verification_score"],
        "average_rating": details["average_rating"],
        "rating_count": details["rating_count"],
        "completed_transactions": details["completed_transactions"],
        "last_updated": details["last_updated"],
    }


@router.get("/me")
def my_trust_score(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _score_out(db, current_user)


@router.get("/{user_id}")
def trust_score_for_user(
    user_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _score_out(db, user)
