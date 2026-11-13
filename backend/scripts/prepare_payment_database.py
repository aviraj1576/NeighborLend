"""Explicit schema preparation. No migration is performed by importing the application."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".test-tools"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-local-demo",
        action="store_true",
        required=True,
        help="Only a NEW SQLite file beneath backend/.payment-demo is accepted",
    )
    parser.parse_args()
    from sqlalchemy.engine import make_url

    url = make_url(os.environ.get("DATABASE_URL", ""))
    target = Path(url.database or "").resolve()
    if (
        url.drivername != "sqlite"
        or not target.is_relative_to((ROOT / ".payment-demo").resolve())
        or target.exists()
    ):
        raise RuntimeError("Schema preparation requires a NEW isolated local demo database")
    from app.config import get_settings
    from app.services.razorpay_service import configured_provider

    configured_provider(get_settings())
    target.parent.mkdir(parents=True, exist_ok=True)
    from app import models  # noqa: F401
    from app.database import Base, engine, migrate_schema

    Base.metadata.create_all(engine)
    migrate_schema(engine)
    engine.dispose()
    print("Initialized a new isolated demo schema. Existing databases were not touched.")


if __name__ == "__main__":
    main()
