import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, Listing, ListingStatus, BorrowRequest, OfferStatus
from app.services.auth import create_access_token, hash_password

class TestChatAndNegotiation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()

        # Create unique test users
        ts = int(datetime.utcnow().timestamp())
        cls.lender = User(
            name=f"Lender User {ts}",
            username=f"lender_{ts}",
            email=f"lender_{ts}@test.com",
            password_hash=hash_password("password123"),
            trust_score=85.0
        )
        cls.borrower = User(
            name=f"Borrower User {ts}",
            username=f"borrower_{ts}",
            email=f"borrower_{ts}@test.com",
            password_hash=hash_password("password123"),
            trust_score=75.0
        )
        cls.intruder = User(
            name=f"Intruder User {ts}",
            username=f"intruder_{ts}",
            email=f"intruder_{ts}@test.com",
            password_hash=hash_password("password123"),
            trust_score=50.0
        )
        cls.db.add_all([cls.lender, cls.borrower, cls.intruder])
        cls.db.commit()
        cls.db.refresh(cls.lender)
        cls.db.refresh(cls.borrower)
        cls.db.refresh(cls.intruder)

        cls.lender_token = create_access_token(cls.lender.id)
        cls.borrower_token = create_access_token(cls.borrower.id)
        cls.intruder_token = create_access_token(cls.intruder.id)

        cls.lender_headers = {"Authorization": f"Bearer {cls.lender_token}"}
        cls.borrower_headers = {"Authorization": f"Bearer {cls.borrower_token}"}
        cls.intruder_headers = {"Authorization": f"Bearer {cls.intruder_token}"}

        # Create a test listing
        cls.listing = Listing(
            owner_id=cls.lender.id,
            name="Professional DSLR Camera Test",
            category="Electronics",
            description="High-end DSLR for weekend shoots",
            price_per_day=500.0,
            min_price_per_day=350.0,
            security_deposit=1000.0,
            status=ListingStatus.published
        )
        cls.db.add(cls.listing)
        cls.db.commit()
        cls.db.refresh(cls.listing)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.close()
        except Exception:
            pass

    def test_01_cannot_chat_with_self(self):
        # Lender tries to start conversation on their own listing
        res = self.client.post(
            "/api/conversations",
            json={"listing_id": self.listing.id, "initial_message": "Hello self"},
            headers=self.lender_headers
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("own listing", res.json()["detail"].lower())

    def test_02_create_conversation_and_send_message(self):
        # Borrower starts conversation
        res = self.client.post(
            "/api/conversations",
            json={"listing_id": self.listing.id, "initial_message": "Hi, is this DSLR available this weekend?"},
            headers=self.borrower_headers
        )
        self.assertEqual(res.status_code, 200)
        conv = res.json()
        self.__class__.conversation_id = conv["id"]
        self.assertEqual(conv["listing_id"], self.listing.id)
        self.assertTrue(conv["is_borrower"])
        self.assertGreaterEqual(len(conv["messages"]), 1)

        # Borrower sends another message
        msg_res = self.client.post(
            f"/api/conversations/{self.conversation_id}/messages",
            json={"content": "I am planning to use it for an outdoor nature shoot."},
            headers=self.borrower_headers
        )
        self.assertEqual(msg_res.status_code, 200)
        self.assertEqual(msg_res.json()["content"], "I am planning to use it for an outdoor nature shoot.")

        # Lender views conversation messages
        lender_res = self.client.get(
            f"/api/conversations/{self.conversation_id}/messages",
            headers=self.lender_headers
        )
        self.assertEqual(lender_res.status_code, 200)
        messages = lender_res.json()
        self.assertGreaterEqual(len(messages), 2)

    def test_03_intruder_forbidden(self):
        # Third party tries to access conversation
        res = self.client.get(
            f"/api/conversations/{self.conversation_id}",
            headers=self.intruder_headers
        )
        self.assertEqual(res.status_code, 403)

        # Third party tries to read messages
        res_msg = self.client.get(
            f"/api/conversations/{self.conversation_id}/messages",
            headers=self.intruder_headers
        )
        self.assertEqual(res_msg.status_code, 403)

    def test_04_offer_validation(self):
        start = (datetime.utcnow() + timedelta(days=2)).isoformat()
        end = (datetime.utcnow() + timedelta(days=5)).isoformat()
        invalid_end = (datetime.utcnow() + timedelta(days=1)).isoformat()

        # 1. Invalid date order (end < start)
        res = self.client.post(
            f"/api/conversations/{self.conversation_id}/offers",
            json={"daily_price": 400.0, "start_date": start, "end_date": invalid_end},
            headers=self.borrower_headers
        )
        self.assertEqual(res.status_code, 400)

        # 2. Daily price below minimum listing price (min is 350, offering 300)
        res = self.client.post(
            f"/api/conversations/{self.conversation_id}/offers",
            json={"daily_price": 300.0, "start_date": start, "end_date": end},
            headers=self.borrower_headers
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("minimum price", res.json()["detail"].lower())

        # 3. Valid offer (400/day for 3 days = 1200)
        res = self.client.post(
            f"/api/conversations/{self.conversation_id}/offers",
            json={
                "daily_price": 400.0,
                "start_date": start,
                "end_date": end,
                "message": "Can you do ₹400/day for 3 days?"
            },
            headers=self.borrower_headers
        )
        self.assertEqual(res.status_code, 200)
        offer = res.json()
        self.__class__.initial_offer_id = offer["id"]
        self.assertEqual(offer["status"], "pending")
        self.assertEqual(offer["daily_price"], 400.0)
        self.assertEqual(offer["total_cost"], 1200.0)

    def test_05_counter_offer_and_history(self):
        # Borrower cannot counter their own offer
        counter_start = (datetime.utcnow() + timedelta(days=2)).isoformat()
        counter_end = (datetime.utcnow() + timedelta(days=5)).isoformat()

        res_self = self.client.post(
            f"/api/offers/{self.initial_offer_id}/counter",
            json={"daily_price": 420.0, "start_date": counter_start, "end_date": counter_end},
            headers=self.borrower_headers
        )
        self.assertEqual(res_self.status_code, 400)

        # Lender counters offer to 450/day
        res = self.client.post(
            f"/api/offers/{self.initial_offer_id}/counter",
            json={
                "daily_price": 450.0,
                "start_date": counter_start,
                "end_date": counter_end,
                "message": "I can do ₹450/day since it includes 2 extra lenses."
            },
            headers=self.lender_headers
        )
        self.assertEqual(res.status_code, 200)
        counter_offer = res.json()
        self.__class__.counter_offer_id = counter_offer["id"]
        self.assertEqual(counter_offer["status"], "pending")
        self.assertEqual(counter_offer["daily_price"], 450.0)
        self.assertEqual(counter_offer["total_cost"], 1350.0)
        self.assertEqual(counter_offer["parent_offer_id"], self.initial_offer_id)

        # Verify initial offer is now marked as countered in conversation offers list
        offers_res = self.client.get(
            f"/api/conversations/{self.conversation_id}/offers",
            headers=self.borrower_headers
        )
        offers = offers_res.json()
        parent = next(o for o in offers if o["id"] == self.initial_offer_id)
        self.assertEqual(parent["status"], "countered")

    def test_06_accept_offer_and_borrow_request_integration(self):
        # Lender cannot accept their own counter offer
        res_self = self.client.post(
            f"/api/offers/{self.counter_offer_id}/accept",
            headers=self.lender_headers
        )
        self.assertEqual(res_self.status_code, 400)

        # Borrower accepts the counter offer
        res = self.client.post(
            f"/api/offers/{self.counter_offer_id}/accept",
            headers=self.borrower_headers
        )
        self.assertEqual(res.status_code, 200)
        accepted = res.json()
        self.assertEqual(accepted["status"], "accepted")
        self.assertIsNotNone(accepted["borrow_request_id"])

        # Verify BorrowRequest was created with agreed terms
        borrow_req_id = accepted["borrow_request_id"]
        db_req = self.db.query(BorrowRequest).filter(BorrowRequest.id == borrow_req_id).first()
        self.assertIsNotNone(db_req)
        self.assertEqual(db_req.borrower_id, self.borrower.id)
        self.assertEqual(db_req.listing_id, self.listing.id)
        self.assertEqual(db_req.max_price_per_day, 450.0)
        self.assertEqual(db_req.total_cost, 1350.0)
        self.assertEqual(db_req.status.value, "open")

    def test_07_prevent_duplicate_acceptance_and_conflicting_dates(self):
        # 1. Duplicate acceptance fails
        res_dup = self.client.post(
            f"/api/offers/{self.counter_offer_id}/accept",
            headers=self.borrower_headers
        )
        self.assertEqual(res_dup.status_code, 400)

        # 2. Another borrower tries to rent the same item on overlapping dates
        # Create second borrower
        ts = int(datetime.utcnow().timestamp()) + 99
        other_borrower = User(
            name=f"Other Borrower {ts}",
            username=f"other_{ts}",
            email=f"other_{ts}@test.com",
            password_hash=hash_password("password123")
        )
        self.db.add(other_borrower)
        self.db.commit()
        other_token = create_access_token(other_borrower.id)
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Other borrower starts conversation
        c_res = self.client.post(
            "/api/conversations",
            json={"listing_id": self.listing.id},
            headers=other_headers
        )
        other_conv_id = c_res.json()["id"]

        # Other borrower tries to make offer overlapping with the accepted offer dates (days 2 to 5)
        conflict_start = (datetime.utcnow() + timedelta(days=3)).isoformat()
        conflict_end = (datetime.utcnow() + timedelta(days=4)).isoformat()

        res_conflict = self.client.post(
            f"/api/conversations/{other_conv_id}/offers",
            json={"daily_price": 480.0, "start_date": conflict_start, "end_date": conflict_end},
            headers=other_headers
        )
        self.assertEqual(res_conflict.status_code, 400)
        self.assertIn("already booked", res_conflict.json()["detail"].lower())

    def test_08_reject_offer(self):
        # Create fresh conversation and offer for rejection test
        ts = int(datetime.utcnow().timestamp()) + 199
        new_borrower = User(
            name=f"Reject Tester {ts}",
            username=f"reject_{ts}",
            email=f"reject_{ts}@test.com",
            password_hash=hash_password("password123")
        )
        self.db.add(new_borrower)
        self.db.commit()
        new_token = create_access_token(new_borrower.id)
        new_headers = {"Authorization": f"Bearer {new_token}"}

        c_res = self.client.post(
            "/api/conversations",
            json={"listing_id": self.listing.id},
            headers=new_headers
        )
        conv_id = c_res.json()["id"]

        # Offer on non-overlapping dates (days 10 to 12)
        start = (datetime.utcnow() + timedelta(days=10)).isoformat()
        end = (datetime.utcnow() + timedelta(days=12)).isoformat()
        off_res = self.client.post(
            f"/api/conversations/{conv_id}/offers",
            json={"daily_price": 400.0, "start_date": start, "end_date": end},
            headers=new_headers
        )
        self.assertEqual(off_res.status_code, 200)
        offer_id = off_res.json()["id"]

        # Lender rejects offer
        rej_res = self.client.post(
            f"/api/offers/{offer_id}/reject",
            headers=self.lender_headers
        )
        self.assertEqual(rej_res.status_code, 200)
        self.assertEqual(rej_res.json()["status"], "rejected")

if __name__ == "__main__":
    unittest.main()
