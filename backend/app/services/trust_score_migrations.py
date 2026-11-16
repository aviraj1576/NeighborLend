"""Add the persisted 0–5 trust breakdown to local/isolated databases."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session


def migrate_trust_scores(target_engine):
    inspector = inspect(target_engine)
    if "users" not in inspector.get_table_names():
        return
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "id" not in user_columns:
        return

    from app.models import TrustScoreSnapshot
    TrustScoreSnapshot.__table__.create(bind=target_engine, checkfirst=True)
    table_names = set(inspect(target_engine).get_table_names())

    # Rebuild legacy 0–100 scores from the source of truth instead of merely
    # dividing old values: role-specific resolutions and completed rentals matter.
    if not {"id", "name", "username", "email", "password_hash"} <= user_columns or not {
        "borrow_requests", "listings", "rental_bookings", "rental_disputes", "disputes"
    } <= table_names:
        return

    from app.models import User
    from app.services.trust_score import refresh_user_trust_score

    with Session(target_engine) as db:
        for user in db.query(User).all():
            refresh_user_trust_score(db, user)
        db.commit()
