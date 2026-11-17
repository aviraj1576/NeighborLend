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
            trust_score=4.1
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

    def test_published_listing_is_saved_and_appears_in_public_feed(self):
        payload = {
            "name": "Persisted Test Listing",
            "category": "Tools",
            "description": "Verify publish persistence",
            "price_per_day": 25.0,
            "security_deposit": 100.0,
            "lending_radius_km": 10.0,
            "publish": True,
        }
        response = self.client.post("/api/listings", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        listing_id = response.json()["id"]

        saved = self.db.query(Listing).filter(Listing.id == listing_id).one()
        self.assertEqual(saved.status.value if hasattr(saved.status, "value") else saved.status, "published")

        feed = self.client.get("/api/listings/search?radius_km=500")
        self.assertEqual(feed.status_code, 200, feed.text)
        self.assertIn(listing_id, {item["id"] for item in feed.json()})

    def test_draft_listing_is_saved_and_visible_in_my_listings_only(self):
        payload = {
            "name": "Persisted Draft Listing",
            "category": "Tools",
            "description": "Verify draft persistence",
            "price_per_day": 25.0,
            "security_deposit": 100.0,
            "lending_radius_km": 10.0,
            "publish": False,
        }
        response = self.client.post("/api/listings", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        listing_id = response.json()["id"]

        saved = self.db.query(Listing).filter(Listing.id == listing_id).one()
        status_value = saved.status.value if hasattr(saved.status, "value") else saved.status
        self.assertEqual(status_value, "draft")

        mine = self.client.get("/api/listings", headers=self.headers)
        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertIn(listing_id, {item["id"] for item in mine.json()})

        feed = self.client.get("/api/listings/search?radius_km=500")
        self.assertEqual(feed.status_code, 200, feed.text)
        self.assertNotIn(listing_id, {item["id"] for item in feed.json()})

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

    def test_delete_listing_by_owner_succeeds(self):
        """Owner can delete their own listing; status becomes removed and GET returns 404."""
        payload = {
            "name": "Deletable Lawn Mower",
            "category": "Tools",
            "description": "Will be deleted",
            "price_per_day": 20.0,
            "security_deposit": 50.0,
            "lending_radius_km": 5.0
        }
        create_res = self.client.post("/api/listings", json=payload, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)
        listing_id = create_res.json()["id"]

        del_res = self.client.delete(f"/api/listings/{listing_id}", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"status": "ok"})

        get_res = self.client.get(f"/api/listings/{listing_id}")
        self.assertEqual(get_res.status_code, 404)

        del_again = self.client.delete(f"/api/listings/{listing_id}", headers=self.headers)
        self.assertEqual(del_again.status_code, 404)

    def test_delete_listing_with_trailing_slash_succeeds(self):
        """DELETE with trailing slash succeeds without redirect."""
        payload = {
            "name": "Slash Deletable Item",
            "category": "Tools",
            "description": "Will be deleted with slash",
            "price_per_day": 15.0,
            "security_deposit": 40.0,
            "lending_radius_km": 5.0
        }
        create_res = self.client.post("/api/listings", json=payload, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)
        listing_id = create_res.json()["id"]

        del_res = self.client.delete(f"/api/listings/{listing_id}/", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"status": "ok"})

    def test_delete_listing_by_non_owner_returns_403(self):
        """Non-owner receives 403 Forbidden when attempting to delete another user's listing."""
        ts = int(datetime.utcnow().timestamp()) + 999
        other_user = User(
            name=f"Other User {ts}",
            username=f"otheruser_{ts}",
            email=f"otheruser_{ts}@test.com",
            password_hash=hash_password("password123"),
            trust_score=3.8
        )
        self.db.add(other_user)
        self.db.commit()
        self.db.refresh(other_user)
        other_token = create_access_token(other_user.id)
        other_headers = {"Authorization": f"Bearer {other_token}"}

        try:
            del_res = self.client.delete(f"/api/listings/{self.listing.id}", headers=other_headers)
            self.assertEqual(del_res.status_code, 403)
        finally:
            self.db.delete(other_user)
            self.db.commit()

    def test_delete_listing_unauthenticated_returns_401(self):
        """Unauthenticated DELETE returns 401."""
        res = self.client.delete(f"/api/listings/{self.listing.id}")
        self.assertEqual(res.status_code, 401)

    def test_delete_nonexistent_listing_returns_404(self):
        """DELETE for non-existent listing returns 404."""
        res = self.client.delete("/api/listings/non-existent-id-12345", headers=self.headers)
        self.assertEqual(res.status_code, 404)

if __name__ == "__main__":
    unittest.main()
