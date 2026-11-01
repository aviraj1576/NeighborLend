import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, Listing
from app.services.auth import create_access_token, hash_password

class TestListingsAuthAndTrailingSlash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, follow_redirects=False)
        cls.db = SessionLocal()

        ts = int(datetime.utcnow().timestamp())
        cls.user = User(
            name=f"Listing Test User {ts}",
            username=f"listuser_{ts}",
            email=f"listuser_{ts}@test.com",
            password_hash=hash_password("password123"),
            trust_score=80.0
        )
        cls.db.add(cls.user)
        cls.db.commit()
        cls.db.refresh(cls.user)

        cls.token = create_access_token(cls.user.id)
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

        # Seed an initial listing
        cls.listing = Listing(
            owner_id=cls.user.id,
            name="Initial Test Lawn Mower",
            category="Tools",
            description="Lawn mower",
            price_per_day=30.0,
            security_deposit=100.0,
            lending_radius_km=10.0
        )
        cls.db.add(cls.listing)
        cls.db.commit()
        cls.db.refresh(cls.listing)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Listing).filter(Listing.owner_id == cls.user.id).delete()
        cls.db.query(User).filter(User.id == cls.user.id).delete()
        cls.db.commit()
        cls.db.close()

    def test_post_listing_without_trailing_slash_returns_200_no_redirect(self):
        """POST /api/listings (no trailing slash) must succeed with 200/201 and not issue a 307 redirect."""
        payload = {
            "name": "Cordless Drill",
            "category": "Tools",
            "description": "Powerful 18V drill",
            "price_per_day": 25.0,
            "security_deposit": 100.0,
            "lending_radius_km": 10.0
        }
        res = self.client.post("/api/listings", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["name"], "Cordless Drill")
        self.assertEqual(data["owner_id"], self.user.id)

    def test_post_listing_with_trailing_slash_returns_200(self):
        """POST /api/listings/ (with trailing slash) must also succeed with 200/201."""
        payload = {
            "name": "Camping Tent",
            "category": "Sports",
            "description": "4-person tent",
            "price_per_day": 35.0,
            "security_deposit": 150.0,
            "lending_radius_km": 15.0
        }
        res = self.client.post("/api/listings/", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["name"], "Camping Tent")

    def test_get_listings_without_trailing_slash_returns_200_no_redirect(self):
        """GET /api/listings (no trailing slash) must succeed with 200 and not issue a 307 redirect."""
        res = self.client.get("/api/listings", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_get_listings_with_trailing_slash_returns_200(self):
        """GET /api/listings/ (with trailing slash) must also succeed with 200."""
        res = self.client.get("/api/listings/", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)

    def test_unauthenticated_request_still_returns_401(self):
        """Requests without Authorization header must still be rejected with 401."""
        res = self.client.get("/api/listings")
        self.assertEqual(res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
