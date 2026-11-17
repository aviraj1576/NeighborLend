"""Derived, role-aware NeighborLend trust scores on a five-star scale."""

import math
from datetime import datetime
from threading import RLock
from weakref import WeakKeyDictionary

from sqlalchemy import inspect, or_, select

from app.models import BorrowRequest, BorrowRequestStatus, Dispute, DisputeStatus, HandoverStatus, TrustScoreSnapshot, User
from app.payment_models import RentalBooking, RentalDispute

RATING_PRIOR = 3.5
RATING_PRIOR_COUNT = 5
_snapshot_table_cache = WeakKeyDictionary()
_snapshot_table_cache_lock = RLock()


def _has_snapshot_table(db):
    """Check the optional legacy-compatible table once per engine.

    Inspect the Session's checked-out connection so this capability check never
    consumes a second Supabase session. A deployment schema change is picked up
    after the app process restarts; inspection errors still propagate.
    """
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    with _snapshot_table_cache_lock:
        if engine not in _snapshot_table_cache:
            _snapshot_table_cache[engine] = inspect(db.connection()).has_table(
                TrustScoreSnapshot.__tablename__
            )
        return _snapshot_table_cache[engine]


def _clamp(value):
    return max(0.0, min(5.0, float(value)))


def _rating_component(ratings):
    count = len(ratings)
    average = sum(ratings) / count if count else 0.0
    bayesian_average = (count * average + RATING_PRIOR_COUNT * RATING_PRIOR) / (count + RATING_PRIOR_COUNT)
    return _clamp((bayesian_average - 1.0) / 4.0 * 5.0), count, average


def calculate_trust_components(*, ratings, transactions, losses, neutral, verified):
    """Pure scoring function; all four inputs and outputs are normalized to 0–5."""
    rating, rating_count, average = _rating_component(ratings)
    reliability = _clamp(5.0 * (1.0 - (losses + 0.25 * neutral) / (transactions + 5.0)))
    experience = _clamp(5.0 * (1.0 - math.exp(-transactions / 20.0)))
    verification = 5.0 if verified else 0.0
    total = round(0.45 * rating + 0.30 * reliability + 0.15 * experience + 0.10 * verification, 2)
    return {
        "score": total,
        "rating_score": round(rating, 2),
        "reliability_score": round(reliability, 2),
        "experience_score": round(experience, 2),
        "verification_score": round(verification, 2),
        "rating_count": rating_count,
        "average_rating": round(average, 2),
        "completed_transactions": transactions,
        "losses": losses,
        "neutral_disputes": neutral,
    }


def _completed_and_outcome(db, request, booking, modern_dispute, legacy_dispute):
    if request.status == BorrowRequestStatus.cancelled:
        return False, None
    if booking is None:
        if request.handover_status == HandoverStatus.return_confirmed.value and not request.disputed_at:
            return True, None
        if (request.handover_status == HandoverStatus.dispute_resolved.value and legacy_dispute
                and legacy_dispute.status == DisputeStatus.resolved):
            legacy_role = {"lender": "borrower_lost", "borrower": "lender_lost", "partial": "partial"}
            return True, legacy_role.get(legacy_dispute.outcome)
        return False, None

    if not (
        booking.payment_status == "captured"
        and booking.booking_status == "completed"
        and booking.deposit_state == "settled"
        and request.returned_at is not None
    ):
        return False, None
    if modern_dispute is None:
        return True, None
    if modern_dispute.status not in {"settled_arbitrated", "settled_mutual"} or not modern_dispute.resolved_at:
        return False, None
    if modern_dispute.status == "settled_mutual":
        return True, "partial"
    approved = modern_dispute.approved_deduction_paise or 0
    if booking.security_deposit_paise > 0 and approved <= 0:
        return True, "lender_lost"
    if booking.security_deposit_paise > 0 and approved >= booking.security_deposit_paise:
        return True, "borrower_lost"
    return True, "partial"


def refresh_user_trust_score(db, user_or_id):
    """Rebuild a user's score from completed rentals and persisted rating fields.

    Counting is derived from unique borrow request rows, so retries cannot increment
    transaction experience twice. Open disputes are excluded from completed rentals.
    """
    user = user_or_id if isinstance(user_or_id, User) else db.get(User, user_or_id)
    if user is None:
        return None

    requests = db.scalars(
        select(BorrowRequest)
        .outerjoin(BorrowRequest.listing)
        .where(or_(BorrowRequest.borrower_id == user.id, BorrowRequest.listing.has(owner_id=user.id)))
    ).unique().all()
    request_ids = [item.id for item in requests]
    bookings = {}
    modern_disputes = {}
    legacy_disputes = {}
    if request_ids:
        for row in db.scalars(select(RentalBooking).where(RentalBooking.borrow_request_id.in_(request_ids))).all():
            bookings[row.borrow_request_id] = row
        booking_ids = [row.id for row in bookings.values()]
        if booking_ids:
            for row in db.scalars(select(RentalDispute).where(RentalDispute.booking_id.in_(booking_ids))).all():
                modern_disputes[row.booking_id] = row
        for row in db.scalars(select(Dispute).where(Dispute.borrow_request_id.in_(request_ids))).all():
            legacy_disputes[row.borrow_request_id] = row

    ratings = []
    completed = 0
    losses = 0
    neutral = 0
    for request in requests:
        lender_id = request.listing.owner_id if request.listing else None
        is_borrower = request.borrower_id == user.id
        is_lender = lender_id == user.id
        if not (is_borrower or is_lender):
            continue
        done, outcome = _completed_and_outcome(
            db, request, bookings.get(request.id),
            modern_disputes.get(bookings[request.id].id) if request.id in bookings else None,
            legacy_disputes.get(request.id),
        )
        if not done:
            continue
        rating = request.lender_rating if is_lender else request.borrower_rating
        if rating is not None:
            ratings.append(int(rating))
        completed += 1
        if outcome == "partial":
            neutral += 1
        elif (outcome == "borrower_lost" and is_borrower) or (outcome == "lender_lost" and is_lender):
            losses += 1

    components = calculate_trust_components(
        ratings=ratings,
        transactions=completed,
        losses=losses,
        neutral=neutral,
        verified=bool(user.is_verified),
    )
    values = {
        "trust_score": components["score"],
        "avg_rating": components["average_rating"],
        "rating_count": components["rating_count"],
        "completed_rentals_count": components["completed_transactions"],
        "disputes_against_count": losses,
    }
    changed = any(getattr(user, field) != value for field, value in values.items())
    for field, value in values.items():
        setattr(user, field, value)
    has_snapshot_table = _has_snapshot_table(db)
    snapshot = db.get(TrustScoreSnapshot, user.id) if has_snapshot_table else None
    now = datetime.utcnow()
    if has_snapshot_table:
        if snapshot is None:
            snapshot = TrustScoreSnapshot(user_id=user.id)
            db.add(snapshot)
            changed = True
            snapshot_changed = True
        else:
            snapshot_changed = any((
                snapshot.rating_component != components["rating_score"],
                snapshot.reliability_component != components["reliability_score"],
                snapshot.experience_component != components["experience_score"],
                snapshot.verification_component != components["verification_score"],
            ))
        snapshot.rating_component = components["rating_score"]
        snapshot.reliability_component = components["reliability_score"]
        snapshot.experience_component = components["experience_score"]
        snapshot.verification_component = components["verification_score"]
        if changed or snapshot_changed or snapshot.updated_at is None:
            snapshot.updated_at = now
        components["last_updated"] = snapshot.updated_at
    else:
        # Old installations remain usable without a schema mutation; the next
        # authorized read computes the breakdown from source data live.
        components["last_updated"] = now
    return components


def refresh_transaction_participants(db, request):
    """Refresh both roles after a completed transaction or resolved dispute."""
    lender_id = request.listing.owner_id if request.listing else None
    refresh_user_trust_score(db, request.borrower_id)
    if lender_id and lender_id != request.borrower_id:
        refresh_user_trust_score(db, lender_id)
