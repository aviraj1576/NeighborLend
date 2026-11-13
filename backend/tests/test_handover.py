import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.database import SessionLocal, migrate_schema
from app.main import app
from app.models import (
    BorrowRequest, BorrowRequestStatus, Conversation, HandoverStatus, Listing,
    ListingStatus, Message, NegotiationOffer, Notification, OfferStatus, User,
)
from app.services.auth import create_access_token


class TestHandover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        cls.lender = User(
            name="Handover Lender", username=f"handover_lender_{suffix}",
            email=f"handover_lender_{suffix}@test.com", password_hash="test",
        )
        cls.borrower = User(
            name="Handover Borrower", username=f"handover_borrower_{suffix}",
            email=f"handover_borrower_{suffix}@test.com", password_hash="test",
        )
        cls.intruder = User(
            name="Handover Intruder", username=f"handover_intruder_{suffix}",
            email=f"handover_intruder_{suffix}@test.com", password_hash="test",
        )
        cls.db.add_all([cls.lender, cls.borrower, cls.intruder])
        cls.db.flush()
        cls.listing = Listing(
            owner_id=cls.lender.id, name="Handover Test Item", category="Tools",
            description="Test item", price_per_day=20, status=ListingStatus.published,
        )
        cls.db.add(cls.listing)
        cls.db.flush()
        cls.headers = {
            role: {"Authorization": f"Bearer {create_access_token(user.id)}"}
            for role, user in (
                ("lender", cls.lender), ("borrower", cls.borrower), ("intruder", cls.intruder)
            )
        }
        cls.request_id = cls._make_rental("main")
        cls.issue_request_id = cls._make_rental("issue")
        cls.db.commit()

    @classmethod
    def _make_rental(cls, label):
        now = datetime.utcnow()
        start = now + timedelta(days=30)
        end = start + timedelta(days=3)
        conversation = Conversation(borrower_id=cls.borrower.id, lender_id=cls.lender.id)
        cls.db.add(conversation)
        cls.db.flush()
        request = BorrowRequest(
            borrower_id=cls.borrower.id,
            listing_id=cls.listing.id,
            title=f"Rental: {label}",
            category=cls.listing.category,
            description="Agreed rental for handover test",
            max_price_per_day=20,
            needed_from=start,
            needed_until=end,
            total_cost=60,
            status=BorrowRequestStatus.open,
            handover_status=HandoverStatus.pending.value,
        )
        cls.db.add(request)
        cls.db.flush()
        offer = NegotiationOffer(
            conversation_id=conversation.id,
            listing_id=cls.listing.id,
            sender_id=cls.borrower.id,
            daily_price=20,
            start_date=start,
            end_date=end,
            total_cost=60,
            status=OfferStatus.accepted,
            borrow_request_id=request.id,
        )
        cls.db.add(offer)
        from app.services.negotiation import snapshot_offer_terms
        snapshot_offer_terms(offer, cls.listing, conversation)
        cls.db.flush()
        # Handover regression fixtures now represent explicitly funded demo rentals.
        from app.services.payments import PaymentService, snapshot_booking
        from app.services.razorpay_service import MockPaymentProvider
        booking = snapshot_booking(cls.db, request, offer, "mock")
        request_id, booking_id, actor = request.id, booking.id, cls.borrower.id
        cls.db.commit()
        payments = PaymentService(cls.db, MockPaymentProvider())
        payments.order(booking_id, actor)
        payments.demo_pay(booking_id, actor, "success")
        return request_id

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_get_handover_is_private_to_participants(self):
        response = self.client.get(
            f"/api/borrow-requests/{self.request_id}/handover",
            headers=self.headers["borrower"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["handover_status"], "pending")
        self.assertTrue(response.json()["conversation_id"])
        forbidden = self.client.get(
            f"/api/borrow-requests/{self.request_id}/handover",
            headers=self.headers["intruder"],
        )
        self.assertEqual(forbidden.status_code, 403)

    def _evidence(self, request_id):
        import io
        from PIL import Image
        from app.payment_models import RentalBooking
        booking = self.db.query(RentalBooking).filter_by(borrow_request_id=request_id).one()
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(stream, format="PNG")
        result = self.client.post(f"/api/payments/bookings/{booking.id}/evidence?stage=handover",
                                  headers=self.headers["lender"],
                                  files={"file": ("before.png", stream.getvalue(), "image/png")})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()["url"]

    def test_new_handover_flow(self):
        """Test the new handover flow: lender uploads photos -> borrower confirms -> lender confirms"""
        request_url = f"/api/borrow-requests/{self.request_id}/handover"
        upload_url = f"{request_url}/upload-photos"
        borrower_confirm_url = f"{request_url}/borrower-confirm"
        lender_confirm_url = f"{request_url}/lender-confirm"

        # 1. Lender uploads photos - unauthorized users get 403 (but need valid body)
        self.assertEqual(self.client.post(upload_url, headers=self.headers["intruder"], json={"photo_urls": ["x"]}).status_code, 403)
        self.assertEqual(self.client.post(upload_url, headers=self.headers["borrower"], json={"photo_urls": ["x"]}).status_code, 403)
        
        upload_resp = self.client.post(upload_url, headers=self.headers["lender"], json={"photo_urls": [self._evidence(self.request_id)]})
        self.assertEqual(upload_resp.status_code, 200)
        self.assertEqual(upload_resp.json()["handover_status"], "photos_uploaded")
        self.assertEqual(len(upload_resp.json()["handover_photos"]), 1)

        # 2. Borrower acknowledges receipt; lender acknowledgement starts rental.
        self.assertEqual(self.client.post(borrower_confirm_url, headers=self.headers["intruder"], json={"photo_urls": []}).status_code, 403)
        self.assertEqual(self.client.post(borrower_confirm_url, headers=self.headers["lender"], json={"photo_urls": []}).status_code, 403)
        
        confirm_resp = self.client.post(borrower_confirm_url, headers=self.headers["borrower"], json={"photo_urls": []})
        self.assertEqual(confirm_resp.status_code, 200)
        body = confirm_resp.json()
        self.assertEqual(body["handover_status"], "borrower_confirmed")
        self.assertEqual(body["status"], "open")
        self.assertEqual(body["handover_confirmed_by"], self.borrower.id)
        self.assertIsNone(body["borrowing_started_at"])
        self.assertIsNone(body["return_due_at"])

        # 3. Lender confirms handover complete
        self.assertEqual(self.client.post(lender_confirm_url, headers=self.headers["intruder"]).status_code, 403)
        self.assertEqual(self.client.post(lender_confirm_url, headers=self.headers["borrower"]).status_code, 403)
        
        lender_confirm_resp = self.client.post(lender_confirm_url, headers=self.headers["lender"])
        self.assertEqual(lender_confirm_resp.status_code, 200)
        self.assertEqual(lender_confirm_resp.json()["handover_status"], "lender_confirmed")

        # Cannot confirm again
        self.assertEqual(self.client.post(lender_confirm_url, headers=self.headers["lender"]).status_code, 409)

        self.db.expire_all()
        request = self.db.query(BorrowRequest).filter_by(id=self.request_id).one()
        self.assertEqual(request.handover_status, "lender_confirmed")
        self.assertEqual(request.status, BorrowRequestStatus.fulfilled)
        self.assertIsNotNone(request.borrowing_started_at)

    def test_issue_report_works_from_photos_uploaded(self):
        """Test that issue can be reported after photos uploaded"""
        request_url = f"/api/borrow-requests/{self.issue_request_id}/handover"
        upload_url = f"{request_url}/upload-photos"
        issue_url = f"{request_url}/report-issue"

        # Lender uploads photos first
        self.assertEqual(self.client.post(upload_url, headers=self.headers["lender"], json={"photo_urls": [self._evidence(self.issue_request_id)]}).status_code, 200)

        # Borrower reports issue
        self.assertEqual(
            self.client.post(issue_url, json={"description": "  "}, headers=self.headers["borrower"]).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(issue_url, json={"description": "Issue"}, headers=self.headers["lender"]).status_code,
            403,
        )
        reported = self.client.post(
            issue_url,
            json={"description": "The casing is cracked."},
            headers=self.headers["borrower"],
        )
        self.assertEqual(reported.status_code, 200)
        self.assertEqual(reported.json()["handover_status"], "issue_reported")
        self.assertEqual(reported.json()["status"], "open")
        self.assertIsNone(reported.json()["borrowing_started_at"])
        self.assertEqual(reported.json()["handover_issue_description"], "The casing is cracked.")
        self.assertEqual(self.client.post(issue_url, json={"description": "Again"}, headers=self.headers["borrower"]).status_code, 409)

        self.db.expire_all()
        request = self.db.query(BorrowRequest).filter_by(id=self.issue_request_id).one()
        self.assertEqual(request.status, BorrowRequestStatus.open)
        self.assertIsNone(request.borrowing_started_at)
        self.assertEqual(
            self.db.query(Notification).filter_by(
                borrow_request_id=self.issue_request_id,
                notification_type="handover_issue_reported",
            ).count(),
            1,
        )


class TestHandoverSchemaMigration(unittest.TestCase):
    def test_existing_borrow_requests_receive_additive_handover_columns(self):
        database_path = Path(tempfile.gettempdir()) / f"neighborlend-legacy-{os.getpid()}.db"
        database_path.unlink(missing_ok=True)
        engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE borrow_requests (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL)"
                ))
                connection.execute(text(
                    "INSERT INTO borrow_requests (id, title) VALUES ('legacy-id', 'Old request')"
                ))
            migrate_schema(engine)
            columns = {column["name"] for column in inspect(engine).get_columns("borrow_requests")}
            self.assertTrue({
                "handover_status", "handover_marked_at", "handover_confirmed_at",
                "handover_confirmed_by", "handover_issue_description",
                "handover_issue_reported_at", "borrowing_started_at", "return_due_at",
            }.issubset(columns))
            with engine.connect() as connection:
                row = connection.execute(text(
                    "SELECT title, handover_status FROM borrow_requests WHERE id = 'legacy-id'"
                )).one()
            self.assertEqual(row.title, "Old request")
            self.assertEqual(row.handover_status, "not_applicable")
        finally:
            engine.dispose()
            database_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
