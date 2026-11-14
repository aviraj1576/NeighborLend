"""Non-destructive test fixtures for manual testing on a real (e.g. Supabase) database.

Unlike seed_data.py this NEVER drops or deletes anything and never changes existing
rows' passwords. It only creates what is missing:
  - users nl_test_admin (admin), nl_test_lender, nl_test_borrower, nl_support
  - one PAUSED listing "Test Power Drill" owned by the test lender (paused = hidden
    from Browse)
  - a conversation between them and one accepted lend in 'pending' handover state

Usage (from backend/):
    python seed_test_users.py               # create anything missing; reuse the pending lend
    python seed_test_users.py --new-lend    # also create a fresh pending lend (repeat a test run)
    python seed_test_users.py --reset-passwords   # new random passwords for the 3 test users

Passwords are random and printed ONCE when set; pass SEED_ADMIN_PASSWORD /
SEED_LENDER_PASSWORD / SEED_BORROWER_PASSWORD env vars to choose them instead.
"""
import os
import secrets
import sys
from datetime import datetime, timedelta

from app.database import Base, SessionLocal, engine, migrate_schema
from app.models import (
    BorrowRequest, BorrowRequestStatus, Conversation, HandoverStatus, Listing,
    ListingStatus, NegotiationOffer, OfferStatus, User,
)
from app.services.auth import hash_password

TEST_USERS = [
    # (key, username, name, is_admin, env var for password)
    ("admin", "nl_test_admin", "Test Admin", True, "SEED_ADMIN_PASSWORD"),
    ("lender", "nl_test_lender", "Test Lender", False, "SEED_LENDER_PASSWORD"),
    ("borrower", "nl_test_borrower", "Test Borrower", False, "SEED_BORROWER_PASSWORD"),
]
LEND_TITLE = "Rental: Test Power Drill"


def _email(username: str) -> str:
    return f"{username}@example.com"


def main(new_lend: bool, reset_passwords: bool) -> None:
    Base.metadata.create_all(bind=engine)  # additive only
    migrate_schema()                       # additive only
    db = SessionLocal()
    try:
        users, printed = {}, []
        for key, username, name, is_admin, env_name in TEST_USERS:
            user = db.query(User).filter(User.username == username).first()
            password = None
            if user is None:
                password = os.environ.get(env_name) or secrets.token_urlsafe(12)
                user = User(
                    name=name, username=username, email=_email(username),
                    password_hash=hash_password(password), is_admin=is_admin,
                )
                db.add(user)
            elif reset_passwords:
                password = os.environ.get(env_name) or secrets.token_urlsafe(12)
                user.password_hash = hash_password(password)
            if password:
                printed.append((username, password))
            users[key] = user

        support = db.query(User).filter(User.username == "nl_support").first()
        if support is None:
            support = User(
                name="NeighborLend Support", username="nl_support",
                email="support@neighborlend.local",
                password_hash=hash_password(secrets.token_urlsafe(24)),
            )
            db.add(support)
        db.flush()

        lender, borrower = users["lender"], users["borrower"]
        listing = db.query(Listing).filter(
            Listing.owner_id == lender.id, Listing.name == "Test Power Drill"
        ).first()
        if listing is None:
            listing = Listing(
                owner_id=lender.id, name="Test Power Drill", category="Drill",
                description="Fixture for manual testing. Paused so it is hidden from Browse.",
                price_per_day=150, status=ListingStatus.paused,
            )
            db.add(listing)
            db.flush()

        conversation = db.query(Conversation).filter(
            Conversation.borrower_id == borrower.id, Conversation.lender_id == lender.id
        ).first()
        if conversation is None:
            conversation = Conversation(borrower_id=borrower.id, lender_id=lender.id)
            db.add(conversation)
            db.flush()

        lend = None
        if not new_lend:
            lend = db.query(BorrowRequest).filter(
                BorrowRequest.borrower_id == borrower.id,
                BorrowRequest.listing_id == listing.id,
                BorrowRequest.title == LEND_TITLE,
                BorrowRequest.handover_status == HandoverStatus.pending.value,
            ).first()
        if lend is None:
            now = datetime.utcnow()
            start, end = now + timedelta(days=1), now + timedelta(days=4)
            lend = BorrowRequest(
                borrower_id=borrower.id, listing_id=listing.id, title=LEND_TITLE,
                category="Drill", description="Test lend created by seed_test_users.py",
                max_price_per_day=150, needed_from=start, needed_until=end, total_cost=450,
                status=BorrowRequestStatus.open, handover_status=HandoverStatus.pending.value,
            )
            db.add(lend)
            db.flush()
            db.add(NegotiationOffer(
                conversation_id=conversation.id, listing_id=listing.id,
                sender_id=borrower.id, daily_price=150, start_date=start, end_date=end,
                total_cost=450, status=OfferStatus.accepted, borrow_request_id=lend.id,
            ))
        db.commit()

        print("Test fixtures ready (nothing was dropped or deleted).")
        for username, password in printed:
            print(f"  NEW PASSWORD  {username}  /  {password}   (shown once; login by username)")
        if not printed:
            print("  Users already existed; passwords untouched (use --reset-passwords).")
        print(f"  Lend (lender={lender.username}, borrower={borrower.username}) id: {lend.id}")
        print(f"  Open as lender/borrower at: /borrow-requests/{lend.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main("--new-lend" in sys.argv, "--reset-passwords" in sys.argv)
