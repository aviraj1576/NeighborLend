import io
import os
import sys
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DAMAGE_PROVIDER", "mock")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image
from starlette.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import (
    BorrowRequest, BorrowRequestStatus, Conversation, Dispute, DisputeStatus,
    HandoverStatus, Listing, ListingStatus, NegotiationOffer, Notification, OfferStatus, User,
)
from app.services.auth import create_access_token

VIEWS = ("front", "back", "left", "right", "top", "bottom")


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (90, 160, 60)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


class TestReturnAndDispute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        users = {}
        for role in ("lender", "borrower", "intruder", "admin"):
            users[role] = User(
                name=f"Ret {role}", username=f"ret_{role}_{suffix}",
                email=f"ret_{role}_{suffix}@test.com", password_hash="test",
                is_admin=(role == "admin"),
            )
        db.add_all(users.values())
        db.flush()
        listing = Listing(
            owner_id=users["lender"].id, name="Return Test Item", category="Drill",
            description="x", price_per_day=20, status=ListingStatus.published,
        )
        db.add(listing)
        db.commit()
        cls.ids = {role: u.id for role, u in users.items()}
        cls.listing_id = listing.id
        db.close()
        cls.headers = {
            role: {"Authorization": f"Bearer {create_access_token(uid)}"}
            for role, uid in cls.ids.items()
        }

    # ---------- helpers ----------
    def _put_photos(self, check_id, phase, role, views=VIEWS):
        for view in views:
            res = self.client.put(
                f"/api/damage-checks/{check_id}/photos/{phase}/{view}",
                files={"file": (f"{view}.png", PNG, "image/png")},
                headers=self.headers[role],
            )
            self.assertEqual(res.status_code, 200, res.text)

    def _set(self, lend_id, **fields):
        db = SessionLocal()
        try:
            req = db.get(BorrowRequest, lend_id)
            for k, v in fields.items():
                setattr(req, k, v)
            db.commit()
        finally:
            db.close()

    def _get(self, lend_id):
        db = SessionLocal()
        try:
            req = db.get(BorrowRequest, lend_id)
            db.expunge(req)
            return req
        finally:
            db.close()

    def _active_lend(self, due_in_days=5, after_photos=True):
        """A lend in 'lender_confirmed' state with a complete before set (and optionally after set)."""
        db = SessionLocal()
        try:
            start = datetime.utcnow() + timedelta(days=30)
            end = start + timedelta(days=3)
            conv = Conversation(borrower_id=self.ids["borrower"], lender_id=self.ids["lender"])
            db.add(conv)
            db.flush()
            req = BorrowRequest(
                borrower_id=self.ids["borrower"], listing_id=self.listing_id,
                title="Rental: return test", category="Drill", description="x",
                max_price_per_day=20, needed_from=start, needed_until=end, total_cost=60,
                status=BorrowRequestStatus.fulfilled,
                handover_status=HandoverStatus.pending.value,
            )
            db.add(req)
            db.flush()
            db.add(NegotiationOffer(
                conversation_id=conv.id, listing_id=self.listing_id,
                sender_id=self.ids["borrower"], daily_price=20, start_date=start,
                end_date=end, total_cost=60, status=OfferStatus.accepted,
                borrow_request_id=req.id,
            ))
            db.commit()
            lend_id = req.id
        finally:
            db.close()
        res = self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/start",
                               headers=self.headers["lender"])
        check_id = res.json()["check_id"]
        self._put_photos(check_id, "before", "lender")
        self.assertEqual(
            self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/share",
                             headers=self.headers["lender"]).status_code, 200)
        self._set(
            lend_id, handover_status=HandoverStatus.lender_confirmed.value,
            borrowing_started_at=datetime.utcnow() - timedelta(days=1),
            return_due_at=datetime.utcnow() + timedelta(days=due_in_days),
        )
        if after_photos:
            self._put_photos(check_id, "after", "borrower")
        return lend_id, check_id

    def _submit(self, lend_id, role="borrower"):
        return self.client.post(f"/api/borrow-requests/{lend_id}/return/submit",
                                headers=self.headers[role])

    def _approve(self, lend_id, role="lender"):
        return self.client.post(f"/api/borrow-requests/{lend_id}/return/approve",
                                headers=self.headers[role])

    def _dispute(self, lend_id, role="lender", reason="Scratch on the left side"):
        return self.client.post(f"/api/borrow-requests/{lend_id}/return/dispute",
                                json={"reason": reason}, headers=self.headers[role])

    def _count_notes(self, user_key, lend_id, ntype):
        db = SessionLocal()
        try:
            return db.query(Notification).filter(
                Notification.user_id == self.ids[user_key],
                Notification.borrow_request_id == lend_id,
                Notification.notification_type == ntype,
            ).count()
        finally:
            db.close()

    # ---------- submit ----------
    def test_submit_needs_all_six_after_photos(self):
        lend_id, check_id = self._active_lend(after_photos=False)
        self._put_photos(check_id, "after", "borrower", VIEWS[:4])
        res = self._submit(lend_id)
        self.assertEqual(res.status_code, 409)
        self.assertIn("bottom", res.json()["detail"])
        self.assertEqual(self._get(lend_id).handover_status, "lender_confirmed")

    def test_submit_happy_path_and_double_submit(self):
        lend_id, check_id = self._active_lend()
        self.assertEqual(self._submit(lend_id, "lender").status_code, 403)
        self.assertEqual(self._submit(lend_id, "intruder").status_code, 403)
        res = self._submit(lend_id)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["handover_status"], "return_photos_uploaded")
        self.assertIsNotNone(self._get(lend_id).returned_at)
        self.assertEqual(self._count_notes("lender", lend_id, "return_submitted"), 1)
        check = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["lender"]).json()
        self.assertIn(check["status"], ("processing", "done"))
        self.assertEqual(self._submit(lend_id).status_code, 409)  # double submission
        self.assertEqual(self._count_notes("lender", lend_id, "return_submitted"), 1)

    def test_early_return_before_due_date(self):
        lend_id, _ = self._active_lend(due_in_days=10)
        self.assertGreater(self._get(lend_id).return_due_at, datetime.utcnow() + timedelta(days=9))
        self.assertEqual(self._submit(lend_id).status_code, 200)

    def test_submit_before_handover_is_complete_is_rejected(self):
        lend_id, _ = self._active_lend()
        self._set(lend_id, handover_status=HandoverStatus.photos_uploaded.value)
        self.assertEqual(self._submit(lend_id).status_code, 409)

    # ---------- approve ----------
    def test_approve_by_lender_only_and_closes_lend(self):
        lend_id, _ = self._active_lend()
        self.assertEqual(self._approve(lend_id).status_code, 409)  # nothing submitted yet
        self._submit(lend_id)
        self.assertEqual(self._approve(lend_id, "borrower").status_code, 403)
        self.assertEqual(self._approve(lend_id, "intruder").status_code, 403)
        res = self._approve(lend_id)
        self.assertEqual(res.status_code, 200, res.text)
        lend = self._get(lend_id)
        self.assertEqual(lend.handover_status, "return_confirmed")
        self.assertEqual(lend.status, BorrowRequestStatus.closed)
        self.assertEqual(lend.return_confirmed_by, self.ids["lender"])
        self.assertEqual(self._count_notes("borrower", lend_id, "return_confirmed"), 1)
        self.assertEqual(self._approve(lend_id).status_code, 409)  # double approve

    def test_review_timeout_auto_approves(self):
        lend_id, _ = self._active_lend()
        self._submit(lend_id)
        self._set(lend_id, returned_at=datetime.utcnow() - timedelta(hours=73))
        res = self.client.get(f"/api/borrow-requests/{lend_id}/handover", headers=self.headers["lender"])
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["handover_status"], "return_confirmed")
        lend = self._get(lend_id)
        self.assertEqual(lend.status, BorrowRequestStatus.closed)
        self.assertIsNone(lend.return_confirmed_by)
        self.assertEqual(self._count_notes("borrower", lend_id, "return_confirmed"), 1)
        self.assertEqual(self._count_notes("lender", lend_id, "return_confirmed"), 1)
        # a late dispute is refused once the window elapsed
        self.assertEqual(self._dispute(lend_id).status_code, 409)

    def test_timeout_does_not_fire_inside_window(self):
        lend_id, _ = self._active_lend()
        self._submit(lend_id)
        self._set(lend_id, returned_at=datetime.utcnow() - timedelta(hours=71))
        res = self.client.get(f"/api/borrow-requests/{lend_id}/handover", headers=self.headers["lender"])
        self.assertEqual(res.json()["handover_status"], "return_photos_uploaded")

    # ---------- dispute ----------
    def test_dispute_flow_and_double_dispute(self):
        lend_id, check_id = self._active_lend()
        self._submit(lend_id)
        self.assertEqual(self._dispute(lend_id, "borrower").status_code, 403)
        self.assertEqual(self._dispute(lend_id, "lender", "   ").status_code, 422)
        res = self._dispute(lend_id)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["handover_status"], "disputed")

        db = SessionLocal()
        try:
            rows = db.query(Dispute).filter(Dispute.borrow_request_id == lend_id).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, DisputeStatus.open)
            self.assertEqual(rows[0].check_id, check_id)
            self.assertEqual(rows[0].raised_by, self.ids["lender"])
        finally:
            db.close()
        self.assertEqual(self._count_notes("admin", lend_id, "admin_dispute"), 1)
        self.assertEqual(self._count_notes("borrower", lend_id, "dispute"), 1)

        again = self._dispute(lend_id)
        self.assertEqual(again.status_code, 409)
        self.assertIn("already open", again.json()["detail"])
        self.assertEqual(self._approve(lend_id).status_code, 409)  # cannot approve a disputed lend

    def test_non_return_dispute_only_a_week_after_due_date(self):
        lend_id, _ = self._active_lend(after_photos=False)
        self._set(lend_id, return_due_at=datetime.utcnow() - timedelta(days=2))
        self.assertEqual(self._dispute(lend_id).status_code, 409)
        self._set(lend_id, return_due_at=datetime.utcnow() - timedelta(days=8))
        res = self._dispute(lend_id, reason="Never returned")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["handover_status"], "disputed")

    def test_dispute_before_any_return_is_rejected(self):
        lend_id, _ = self._active_lend(after_photos=False)
        self.assertEqual(self._dispute(lend_id).status_code, 409)


if __name__ == "__main__":
    unittest.main()
