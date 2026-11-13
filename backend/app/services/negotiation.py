from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import Listing, ListingStatus, NegotiationOffer, OfferStatus, BorrowRequest, BorrowRequestStatus, Conversation


def snapshot_offer_terms(offer, listing, conversation):
    from app.services.escrow_service import paise

    days, _ = calculate_rental_duration_and_cost(offer.daily_price, offer.start_date, offer.end_date)
    daily = paise(offer.daily_price)
    deposit = paise(listing.security_deposit or 0)
    if daily <= 0 or days > 3650 or daily * days + deposit > 1_000_000_000:
        raise ValueError("Offer amount or duration outside supported limits")
    offer.borrower_id_snapshot = conversation.borrower_id
    offer.lender_id_snapshot = listing.owner_id
    offer.daily_rate_paise = daily
    offer.rental_fee_paise = daily * days
    offer.security_deposit_paise = deposit
    offer.total_amount_paise = daily * days + deposit
    # Legacy display fields are derived from the authoritative minor-unit terms.
    offer.daily_price = daily / 100
    offer.total_cost = offer.rental_fee_paise / 100

def calculate_rental_duration_and_cost(daily_price: float, start_date: datetime, end_date: datetime) -> Tuple[int, float]:
    """
    Consistent rental duration and cost calculation.
    - If end_date < start_date, raises ValueError.
    - If end_date == start_date, counts as a 1-day rental.
    - Otherwise duration is (end_date.date() - start_date.date()).days.
    - total_cost = daily_price * duration_days.
    """
    start_d = start_date.date() if isinstance(start_date, datetime) else start_date
    end_d = end_date.date() if isinstance(end_date, datetime) else end_date

    if end_d < start_d:
        raise ValueError("End date cannot be earlier than start date.")

    days = (end_d - start_d).days
    if days == 0:
        days = 1  # Same-day rental counts as 1 day

    total_cost = round(days * float(daily_price), 2)
    return days, total_cost

def check_listing_availability(
    db: Session,
    listing_id: str,
    start_date: datetime,
    end_date: datetime,
    exclude_offer_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Checks whether a listing is published and not booked for overlapping dates.
    Two date intervals [S1, E1] and [S2, E2] overlap iff S1 <= E2 and E1 >= S2.
    """
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        return False, "Listing does not exist."
    if listing.status != ListingStatus.published:
        return False, f"Listing is currently '{listing.status.value}' and not available for rent."

    # Check for accepted negotiation offers on the same listing
    query = (
        db.query(NegotiationOffer)
        .join(Conversation, NegotiationOffer.conversation_id == Conversation.id)
        .filter(
            NegotiationOffer.listing_id == listing_id,
            NegotiationOffer.status == OfferStatus.accepted,
            NegotiationOffer.start_date <= end_date,
            NegotiationOffer.end_date >= start_date
        )
    )
    if exclude_offer_id:
        query = query.filter(NegotiationOffer.id != exclude_offer_id)

    conflict_offer = query.first()
    if conflict_offer:
        s_str = conflict_offer.start_date.strftime("%b %d, %Y")
        e_str = conflict_offer.end_date.strftime("%b %d, %Y")
        return False, f"Item is already booked from {s_str} to {e_str}."

    # Check for fulfilled borrow requests on the same listing
    conflict_borrow = (
        db.query(BorrowRequest)
        .filter(
            BorrowRequest.listing_id == listing_id,
            BorrowRequest.status == BorrowRequestStatus.fulfilled,
            BorrowRequest.returned_at.is_(None),
            BorrowRequest.needed_from.isnot(None),
            BorrowRequest.needed_until.isnot(None),
            func.coalesce(BorrowRequest.borrowing_started_at, BorrowRequest.needed_from) <= end_date,
            func.coalesce(BorrowRequest.return_due_at, BorrowRequest.needed_until) >= start_date
        )
        .first()
    )
    if conflict_borrow:
        s_str = conflict_borrow.needed_from.strftime("%b %d, %Y")
        e_str = conflict_borrow.needed_until.strftime("%b %d, %Y")
        return False, f"Item has an active booking from {s_str} to {e_str}."

    return True, ""
