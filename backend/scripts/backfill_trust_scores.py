"""Recompute cached trust scores after applying trust-score SQL to an existing DB."""

import argparse

from sqlalchemy.orm import Session

from app.database import engine
from app.database import require_generic_schema_target_allowed
from app.models import User
from app.services.trust_score import refresh_user_trust_score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-shared-database",
        action="store_true",
        help="Required before recomputing derived scores in a hosted database.",
    )
    args = parser.parse_args()
    is_hosted = bool(engine.url.host and (engine.url.host.endswith(".supabase.co") or engine.url.host.endswith(".supabase.com")))
    if is_hosted and not args.confirm_shared_database:
        parser.error("Refusing to update hosted user scores without --confirm-shared-database")
    if not is_hosted:
        require_generic_schema_target_allowed(engine)

    with Session(engine) as db:
        users = db.query(User).all()
        for user in users:
            refresh_user_trust_score(db, user)
        db.commit()
    print(f"Recomputed trust scores for {len(users)} users.")


if __name__ == "__main__":
    main()
