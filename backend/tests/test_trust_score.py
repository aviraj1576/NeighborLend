from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    BorrowRequest, BorrowRequestStatus, Conversation, Dispute, DisputeStatus,
    HandoverStatus, Listing, ListingStatus, NegotiationOffer, OfferStatus, User,
)
from app.payment_models import RentalBooking, RentalDispute
from app.services.auth import create_access_token
from app.services.trust_score import calculate_trust_components, refresh_user_trust_score


def _user(db, label, *, verified=True):
    key = uuid4().hex
    user = User(
        name=label, username=f"trust_{key}", email=f"{key}@trust.test",
        password_hash="synthetic", is_verified=verified,
    )
    db.add(user)
    db.flush()
    return user


def _completed_legacy(db, lender, borrower, *, outcome=None, rating_lender=None, rating_borrower=None):
    listing = Listing(
        owner_id=lender.id, name="Trust test item", category="Tools",
        price_per_day=10, status=ListingStatus.published,
    )
    db.add(listing)
    db.flush()
    disputed = outcome is not None
    request = BorrowRequest(
        borrower_id=borrower.id, listing_id=listing.id, title="Trust test rental",
        category="Tools", status=BorrowRequestStatus.closed,
        handover_status=HandoverStatus.dispute_resolved.value if disputed else HandoverStatus.return_confirmed.value,
        returned_at=datetime.utcnow(), disputed_at=datetime.utcnow() if disputed else None,
        lender_rating=rating_lender, borrower_rating=rating_borrower,
    )
    db.add(request)
    db.flush()
    if disputed:
        db.add(Dispute(
            borrow_request_id=request.id, raised_by=lender.id, reason="Synthetic test dispute",
            status=DisputeStatus.resolved, outcome=outcome, resolved_at=datetime.utcnow(),
        ))
    return request


def test_components_are_bayesian_weighted_and_bounded():
    new_user = calculate_trust_components(
        ratings=[], transactions=0, losses=0, neutral=0, verified=False,
    )
    assert new_user["score"] == 2.91
    assert new_user["rating_score"] == 3.12
    assert new_user["reliability_score"] == 5
    assert new_user["experience_score"] == 0

    many_fives = calculate_trust_components(
        ratings=[5] * 100, transactions=100, losses=0, neutral=0, verified=True,
    )
    assert many_fives["score"] <= 5
    assert many_fives["rating_score"] > new_user["rating_score"]
    assert many_fives["completed_transactions"] == 100


def test_completed_rentals_count_once_and_ratings_update_each_role():
    with SessionLocal() as db:
        lender = _user(db, "Trust lender")
        borrower = _user(db, "Trust borrower")
        _completed_legacy(db, lender, borrower, rating_lender=5, rating_borrower=4)
        db.commit()

        lender_score = refresh_user_trust_score(db, lender)
        borrower_score = refresh_user_trust_score(db, borrower)
        db.commit()
        refresh_user_trust_score(db, lender)
        db.commit()

        assert lender.completed_rentals_count == borrower.completed_rentals_count == 1
        assert lender.rating_count == borrower.rating_count == 1
        assert lender_score["score"] <= 5 and borrower_score["score"] <= 5
        assert lender_score["rating_score"] > borrower_score["rating_score"]


def test_unresolved_and_cancelled_requests_do_not_count_or_penalize():
    with SessionLocal() as db:
        lender = _user(db, "Trust lender")
        borrower = _user(db, "Trust borrower")
        listing = Listing(owner_id=lender.id, name="Pending item", category="Tools", price_per_day=10)
        db.add(listing)
        db.flush()
        db.add_all([
            BorrowRequest(
                borrower_id=borrower.id, listing_id=listing.id, title="Open dispute",
                category="Tools", status=BorrowRequestStatus.fulfilled,
                handover_status=HandoverStatus.disputed.value, disputed_at=datetime.utcnow(),
            ),
            BorrowRequest(
                borrower_id=borrower.id, listing_id=listing.id, title="Cancelled",
                category="Tools", status=BorrowRequestStatus.cancelled,
                handover_status=HandoverStatus.not_applicable.value,
            ),
        ])
        db.commit()
        result = refresh_user_trust_score(db, borrower)
        db.commit()
        assert result["completed_transactions"] == 0
        assert result["losses"] == 0


def test_resolved_dispute_is_role_specific_and_authenticated_api_returns_breakdown():
    with SessionLocal() as db:
        lender = _user(db, "Trust lender")
        borrower = _user(db, "Trust borrower")
        _completed_legacy(db, lender, borrower, outcome="lender")
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(borrower.id)}"}
        response = TestClient(app).get(f"/api/trust/{borrower.id}", headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["score"] <= 5
        assert result["completed_transactions"] == 1
        assert result["reliability_score"] < 5
        assert {"rating_score", "experience_score", "verification_score", "last_updated"} <= result.keys()
        assert response.headers["cache-control"] == "no-store"
        assert TestClient(app).get(f"/api/trust/{borrower.id}").status_code == 401


def test_settled_payment_dispute_counts_once_and_penalizes_borrower_role():
    with SessionLocal() as db:
        lender = _user(db, "Trust lender")
        borrower = _user(db, "Trust borrower")
        listing = Listing(owner_id=lender.id, name="Paid item", category="Tools", price_per_day=10)
        db.add(listing)
        db.flush()
        request = BorrowRequest(
            borrower_id=borrower.id, listing_id=listing.id, title="Paid rental",
            category="Tools", status=BorrowRequestStatus.closed,
            handover_status=HandoverStatus.return_confirmed.value,
            returned_at=datetime.utcnow(),
        )
        db.add(request)
        db.flush()
        conversation = Conversation(borrower_id=borrower.id, lender_id=lender.id, listing_id=listing.id)
        db.add(conversation)
        db.flush()
        offer = NegotiationOffer(
            conversation_id=conversation.id, listing_id=listing.id, sender_id=borrower.id,
            daily_price=10, start_date=datetime.utcnow(), end_date=datetime.utcnow(),
            total_cost=10, status=OfferStatus.accepted, borrow_request_id=request.id,
        )
        db.add(offer)
        db.flush()
        booking = RentalBooking(
            borrow_request_id=request.id, offer_id=offer.id, listing_id=listing.id,
            borrower_id=borrower.id, lender_id=lender.id,
            start_date=datetime.utcnow(), end_date=datetime.utcnow(), duration_days=1,
            daily_rate_paise=1000, rental_fee_paise=1000,
            security_deposit_paise=5000, total_amount_paise=6000,
            provider="mock", booking_status="completed", payment_status="captured",
            deposit_state="settled", refunded_paise=0, deduction_paise=5000,
        )
        db.add(booking)
        db.flush()
        db.add(RentalDispute(
            booking_id=booking.id, claimed_deduction_paise=5000,
            approved_deduction_paise=5000, status="settled_arbitrated",
            lender_claim_notes="Synthetic test claim", resolved_at=datetime.utcnow(),
        ))
        db.commit()

        refresh_user_trust_score(db, borrower)
        refresh_user_trust_score(db, lender)
        db.commit()
        refresh_user_trust_score(db, borrower)
        db.commit()
        assert borrower.completed_rentals_count == lender.completed_rentals_count == 1
        assert borrower.disputes_against_count == 1
        assert lender.disputes_against_count == 0
