"""Seed a NEW local-only demo database; never overwrite an existing database."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".test-tools"))


def main():
    from sqlalchemy.engine import make_url

    if (
        os.environ.get("APP_ENV") != "demo"
        or os.environ.get("PAYMENT_PROVIDER") != "mock"
        or os.environ.get("PAYMENT_DEMO_MODE", "").lower() != "true"
    ):
        raise RuntimeError("Explicit local mock demo configuration is required")
    url = make_url(os.environ["DATABASE_URL"])
    directory = ROOT / ".payment-demo"
    target = Path(url.database or "").resolve()
    if (
        url.drivername != "sqlite"
        or not target.is_relative_to(directory.resolve())
        or not target.is_relative_to(ROOT.resolve())
        or target.exists()
    ):
        raise RuntimeError("Use a NEW SQLite database strictly beneath backend/.payment-demo/")
    password = os.environ.get("PAYMENT_DEMO_PASSWORD", "")
    if not 12 <= len(password.encode()) <= 72:
        raise RuntimeError(
            "PAYMENT_DEMO_PASSWORD must be 12-72 UTF-8 bytes; never pass it as a CLI argument"
        )
    directory.mkdir(exist_ok=True)
    from app.config import get_settings
    from app.database import Base, SessionLocal, engine, migrate_schema
    from app.models import Listing, ListingStatus, User
    from app.services.auth import hash_password
    from app.services.razorpay_service import configured_provider

    configured_provider(get_settings())

    Base.metadata.create_all(engine)
    migrate_schema()
    with SessionLocal() as db:
        lender = User(
            name="Demo Lender",
            username="demo_lender",
            email="lender@neighborlend.test",
            password_hash=hash_password(password),
            is_verified=True,
        )
        borrower = User(
            name="Demo Borrower",
            username="demo_borrower",
            email="borrower@neighborlend.test",
            password_hash=hash_password(password),
            is_verified=True,
        )
        administrator = User(
            name="Demo Administrator",
            username="demo_admin",
            email="admin@neighborlend.test",
            password_hash=hash_password(password),
            is_verified=True,
            is_admin=True,
        )
        db.add_all([lender, borrower, administrator])
        db.flush()
        db.add(
            Listing(
                owner_id=lender.id,
                name="Demo neighborhood drill",
                category="Tools",
                description="Local test-mode rental; no real payment or regulated escrow.",
                price_per_day=200,
                min_price_per_day=100,
                security_deposit=500,
                status=ListingStatus.published,
            )
        )
        db.commit()
    print(
        "Created local demo accounts: lender@neighborlend.test, borrower@neighborlend.test, admin@neighborlend.test"
    )
    print("Use your environment-supplied demo password. No email was sent; no payment was made.")


if __name__ == "__main__":
    main()
