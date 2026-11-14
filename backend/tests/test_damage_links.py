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
    BorrowRequest, BorrowRequestStatus, Conversation, HandoverStatus, Listing,
    ListingStatus, Message, NegotiationOffer, Notification, OfferStatus, User,
)
from app.services.auth import create_access_token

VIEWS = ("front", "back", "left", "right", "top", "bottom")


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (30, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


class TestDamageLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        cls.users = {}
        for role in ("lender", "borrower", "intruder"):
            cls.users[role] = User(
                name=f"Link {role}", username=f"link_{role}_{suffix}",
                email=f"link_{role}_{suffix}@test.com", password_hash="test",
            )
        db.add_all(cls.users.values())
        db.flush()
        cls.listing = Listing(
            owner_id=cls.users["lender"].id, name="Link Test Item", category="Drill",
            description="x", price_per_day=20, status=ListingStatus.published,
        )
        db.add(cls.listing)
        db.commit()
        cls.ids = {role: u.id for role, u in cls.users.items()}
        cls.listing_id = cls.listing.id
        db.close()
        cls.headers = {
            role: {"Authorization": f"Bearer {create_access_token(uid)}"}
            for role, uid in cls.ids.items()
        }

    # ---------- helpers ----------
    def _make_lend(self):
        db = SessionLocal()
        try:
            start = datetime.utcnow() + timedelta(days=30)
            end = start + timedelta(days=3)
            conv = Conversation(borrower_id=self.ids["borrower"], lender_id=self.ids["lender"])
            db.add(conv)
            db.flush()
            req = BorrowRequest(
                borrower_id=self.ids["borrower"], listing_id=self.listing_id,
                title="Rental: link test", category="Drill", description="x",
                max_price_per_day=20, needed_from=start, needed_until=end, total_cost=60,
                status=BorrowRequestStatus.open, handover_status=HandoverStatus.pending.value,
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
            return req.id, conv.id
        finally:
            db.close()

    def _start(self, lend_id, role="lender"):
        return self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/start",
                                headers=self.headers[role])

    def _share(self, lend_id, role="lender"):
        return self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/share",
                                headers=self.headers[role])

    def _upload_before(self, check_id, views=VIEWS):
        for view in views:
            res = self.client.put(
                f"/api/damage-checks/{check_id}/photos/before/{view}",
                files={"file": (f"{view}.png", PNG, "image/png")},
                headers=self.headers["lender"],
            )
            self.assertEqual(res.status_code, 200, res.text)

    def _shared_lend(self):
        lend_id, conv_id = self._make_lend()
        check_id = self._start(lend_id).json()["check_id"]
        self._upload_before(check_id)
        res = self._share(lend_id)
        self.assertEqual(res.status_code, 200, res.text)
        return lend_id, conv_id, check_id, res.json()

    def _set(self, lend_id, **fields):
        db = SessionLocal()
        try:
            req = db.get(BorrowRequest, lend_id)
            for k, v in fields.items():
                setattr(req, k, v)
            db.commit()
        finally:
            db.close()

    # ---------- tests ----------
    def test_start_is_lender_only_and_idempotent(self):
        lend_id, _ = self._make_lend()
        self.assertEqual(self._start(lend_id, "borrower").status_code, 403)
        self.assertEqual(self._start(lend_id, "intruder").status_code, 403)
        first = self._start(lend_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self._start(lend_id).json()["check_id"], first.json()["check_id"])

    def test_share_requires_all_six_photos(self):
        lend_id, _ = self._make_lend()
        self.assertEqual(self._share(lend_id).status_code, 409)  # no check yet
        check_id = self._start(lend_id).json()["check_id"]
        self._upload_before(check_id, VIEWS[:5])
        res = self._share(lend_id)
        self.assertEqual(res.status_code, 409)
        self.assertIn("bottom", res.json()["detail"])
        self.assertEqual(self._share(lend_id, "borrower").status_code, 403)

    def test_share_mints_link_notifies_and_is_idempotent(self):
        lend_id, conv_id, _, body = self._shared_lend()
        token = body["token"]
        self.assertEqual(body["link"], f"/damage-check/{token}")
        self.assertGreaterEqual(len(token), 40)

        db = SessionLocal()
        try:
            req = db.get(BorrowRequest, lend_id)
            self.assertEqual(req.handover_status, "photos_uploaded")
            notes = db.query(Notification).filter(
                Notification.user_id == self.ids["borrower"],
                Notification.borrow_request_id == lend_id,
                Notification.notification_type == "damage_check_link",
            ).all()
            self.assertEqual([n.link_url for n in notes], [f"/damage-check/{token}"])
            msgs = db.query(Message).filter(Message.conversation_id == conv_id).all()
            self.assertTrue(any("/damage-check/" in m.content for m in msgs))
        finally:
            db.close()

        again = self._share(lend_id)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["token"], token)
        db = SessionLocal()
        try:
            count = db.query(Notification).filter(
                Notification.borrow_request_id == lend_id,
                Notification.notification_type == "damage_check_link",
            ).count()
            self.assertEqual(count, 1)  # re-sharing does not spam the borrower
        finally:
            db.close()

    def test_resolve_link_authorization(self):
        _, _, check_id, body = self._shared_lend()
        url = f"/api/damage-links/{body['token']}"
        res = self.client.get(url, headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["role"], "borrower")
        self.assertEqual(res.json()["check_id"], check_id)
        self.assertEqual(self.client.get(url, headers=self.headers["lender"]).json()["role"], "lender")
        self.assertEqual(self.client.get(url, headers=self.headers["intruder"]).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(
            self.client.get("/api/damage-links/not-a-real-token", headers=self.headers["borrower"]).status_code,
            404,
        )

    def test_expired_and_closed_links_return_410(self):
        lend_id, _, _, body = self._shared_lend()
        url = f"/api/damage-links/{body['token']}"
        self._set(lend_id, damage_link_expires_at=datetime.utcnow() - timedelta(days=1))
        res = self.client.get(url, headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 410)
        self.assertIn("expired", res.json()["detail"])

        self._set(lend_id, damage_link_expires_at=datetime.utcnow() + timedelta(days=5),
                  handover_status="return_confirmed")
        res = self.client.get(url, headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 410)
        self.assertIn("closed", res.json()["detail"])

    def test_link_lifetime_extended_when_rental_starts(self):
        lend_id, _, _, body = self._shared_lend()
        res = self.client.post(f"/api/borrow-requests/{lend_id}/handover/borrower-confirm",
                               json={}, headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 200, res.text)
        db = SessionLocal()
        try:
            req = db.get(BorrowRequest, lend_id)
            self.assertGreaterEqual(req.damage_link_expires_at, req.return_due_at + timedelta(days=29))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
