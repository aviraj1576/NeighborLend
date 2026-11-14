import io
import os
import sys
import time
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DAMAGE_PROVIDER", "mock")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image
from starlette.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import (
    AdminAuditLog, BorrowRequest, BorrowRequestStatus, Conversation, Dispute, DisputeStatus,
    HandoverStatus, Listing, ListingStatus, Message, NegotiationOffer, Notification,
    OfferStatus, User,
)
from app.services.auth import create_access_token

VIEWS = ("front", "back", "left", "right", "top", "bottom")


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 10, 200)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


class TestAdminDisputes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        users = {}
        for role in ("lender", "borrower", "admin"):
            users[role] = User(
                name=f"Adm {role}", username=f"adm_{role}_{suffix}",
                email=f"adm_{role}_{suffix}@test.com", password_hash="test",
                is_admin=(role == "admin"),
            )
        db.add_all(users.values())
        db.flush()
        listing = Listing(
            owner_id=users["lender"].id, name="Admin Test Item", category="Drill",
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
    def _put_photos(self, check_id, phase, role):
        for view in VIEWS:
            res = self.client.put(
                f"/api/damage-checks/{check_id}/photos/{phase}/{view}",
                files={"file": (f"{view}.png", PNG, "image/png")},
                headers=self.headers[role],
            )
            self.assertEqual(res.status_code, 200, res.text)

    def _disputed_lend(self):
        """Drive a real lend through the API into the 'disputed' state."""
        db = SessionLocal()
        try:
            start = datetime.utcnow() + timedelta(days=30)
            end = start + timedelta(days=3)
            conv = Conversation(borrower_id=self.ids["borrower"], lender_id=self.ids["lender"])
            db.add(conv)
            db.flush()
            req = BorrowRequest(
                borrower_id=self.ids["borrower"], listing_id=self.listing_id,
                title="Rental: admin test", category="Drill", description="x",
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
            lend_id, conv_id = req.id, conv.id
        finally:
            db.close()
        lender, borrower = self.headers["lender"], self.headers["borrower"]
        check_id = self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/start",
                                    headers=lender).json()["check_id"]
        self._put_photos(check_id, "before", "lender")
        self.client.post(f"/api/borrow-requests/{lend_id}/damage-check/share", headers=lender)
        db = SessionLocal()
        try:
            r = db.get(BorrowRequest, lend_id)
            r.handover_status = HandoverStatus.lender_confirmed.value
            r.return_due_at = datetime.utcnow() + timedelta(days=2)
            db.commit()
        finally:
            db.close()
        self._put_photos(check_id, "after", "borrower")
        self.assertEqual(
            self.client.post(f"/api/borrow-requests/{lend_id}/return/submit", headers=borrower).status_code, 200)
        res = self.client.post(f"/api/borrow-requests/{lend_id}/return/dispute",
                               json={"reason": "Dent on the casing"}, headers=lender)
        self.assertEqual(res.status_code, 200, res.text)
        db = SessionLocal()
        try:
            dispute = db.query(Dispute).filter(Dispute.borrow_request_id == lend_id).one()
            return lend_id, conv_id, check_id, dispute.id
        finally:
            db.close()

    def _admin_get(self, path, role="admin"):
        return self.client.get(f"/api/admin{path}", headers=self.headers[role])

    def _resolve(self, dispute_id, body, role="admin"):
        return self.client.post(f"/api/admin/disputes/{dispute_id}/resolve", json=body,
                                headers=self.headers[role])

    # ---------- tests ----------
    def test_admin_endpoints_reject_non_admins(self):
        _, _, _, dispute_id = self._disputed_lend()
        for role in ("lender", "borrower"):
            self.assertEqual(self._admin_get("/disputes", role).status_code, 403)
            self.assertEqual(self._admin_get(f"/disputes/{dispute_id}", role).status_code, 403)
            self.assertEqual(self._admin_get(f"/disputes/{dispute_id}/photos/before/front", role).status_code, 403)
            self.assertEqual(self._admin_get("/audit-logs", role).status_code, 403)
            self.assertEqual(self._resolve(dispute_id, {"outcome": "lender"}, role).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/disputes").status_code, 401)
        self.assertEqual(self.client.post(f"/api/admin/disputes/{dispute_id}/resolve",
                                          json={"outcome": "lender"}).status_code, 401)
        db = SessionLocal()  # nothing changed by the rejected calls
        try:
            self.assertEqual(db.get(Dispute, dispute_id).status, DisputeStatus.open)
        finally:
            db.close()

    def test_list_and_filter(self):
        lend_id, _, check_id, dispute_id = self._disputed_lend()
        rows = self._admin_get("/disputes").json()
        row = next(r for r in rows if r["id"] == dispute_id)
        self.assertEqual(row["borrow_request_id"], lend_id)
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["check_id"], check_id)
        self.assertEqual(row["lender"]["id"], self.ids["lender"])
        self.assertEqual(row["borrower"]["id"], self.ids["borrower"])
        self.assertIn("reason", row)
        resolved = self._admin_get("/disputes?status=resolved").json()
        self.assertNotIn(dispute_id, [r["id"] for r in resolved])
        self.assertIn(dispute_id, [r["id"] for r in self._admin_get("/disputes?status=all").json()])
        self.assertEqual(self._admin_get("/disputes?status=bogus").status_code, 422)

    def test_detail_has_report_and_photo_lists(self):
        _, _, _, dispute_id = self._disputed_lend()
        detail = None
        for _ in range(20):
            detail = self._admin_get(f"/disputes/{dispute_id}").json()
            if detail["check_status"] == "done":
                break
            time.sleep(0.2)
        self.assertEqual(detail["check_status"], "done")
        self.assertEqual(detail["report"]["overall"], "clear")
        self.assertEqual(len(detail["report"]["views"]), 6)
        self.assertEqual(detail["before_views"], list(VIEWS))
        self.assertEqual(detail["after_views"], list(VIEWS))
        self.assertIn("{phase}", detail["photo_url_template"])
        self.assertEqual(detail["lend"]["handover_status"], "disputed")
        self.assertEqual(self._admin_get("/disputes/does-not-exist").status_code, 404)

    def test_photo_endpoint(self):
        _, _, _, dispute_id = self._disputed_lend()
        res = self._admin_get(f"/disputes/{dispute_id}/photos/after/top")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/png")
        self.assertEqual(res.content, PNG)
        self.assertEqual(self._admin_get(f"/disputes/{dispute_id}/photos/after/side").status_code, 400)
        self.assertEqual(self._admin_get(f"/disputes/{dispute_id}/photos/during/top").status_code, 400)

    def test_resolve_validation(self):
        _, _, _, dispute_id = self._disputed_lend()
        self.assertEqual(self._resolve(dispute_id, {"outcome": "partial"}).status_code, 422)
        self.assertEqual(self._resolve(dispute_id, {"outcome": "partial", "note": "  "}).status_code, 422)
        self.assertEqual(self._resolve(dispute_id, {"outcome": "nobody"}).status_code, 422)
        self.assertEqual(self._resolve("does-not-exist", {"outcome": "lender"}).status_code, 404)
        db = SessionLocal()
        try:
            self.assertEqual(db.get(Dispute, dispute_id).status, DisputeStatus.open)
        finally:
            db.close()

    def test_resolve_closes_lend_notifies_both_and_audits(self):
        lend_id, conv_id, _, dispute_id = self._disputed_lend()
        res = self._resolve(dispute_id, {"outcome": "lender", "note": "Damage is clear in the photos"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "resolved")
        self.assertEqual(res.json()["outcome"], "lender")

        db = SessionLocal()
        try:
            lend = db.get(BorrowRequest, lend_id)
            self.assertEqual(lend.handover_status, "dispute_resolved")
            self.assertEqual(lend.status, BorrowRequestStatus.closed)
            dispute = db.get(Dispute, dispute_id)
            self.assertEqual(dispute.resolved_by, self.ids["admin"])
            self.assertIsNotNone(dispute.resolved_at)
            notes = db.query(Notification).filter(
                Notification.borrow_request_id == lend_id,
                Notification.notification_type == "dispute_resolved",
            ).all()
            by_user = {n.user_id: n.message for n in notes}
            self.assertEqual(set(by_user), {self.ids["lender"], self.ids["borrower"]})
            self.assertIn("in your favor", by_user[self.ids["lender"]])
            self.assertIn("lender's favor", by_user[self.ids["borrower"]])
            self.assertIn("Damage is clear", by_user[self.ids["borrower"]])
            logs = db.query(AdminAuditLog).filter(AdminAuditLog.target_id == dispute_id).all()
            self.assertEqual([(l.action, l.admin_id) for l in logs], [("dispute_resolved", self.ids["admin"])])
            msgs = db.query(Message).filter(Message.conversation_id == conv_id).all()
            self.assertTrue(any("resolved the dispute" in m.content for m in msgs))
        finally:
            db.close()

        self.assertEqual(self._resolve(dispute_id, {"outcome": "borrower"}).status_code, 409)  # double resolve
        log_rows = self._admin_get("/audit-logs?limit=50").json()
        mine = [r for r in log_rows if r["target_id"] == dispute_id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["detail"]["outcome"], "lender")

    def test_partial_and_borrower_outcomes(self):
        _, _, _, d1 = self._disputed_lend()
        res = self._resolve(d1, {"outcome": "partial", "note": "Split the repair cost"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["outcome"], "partial")
        _, _, _, d2 = self._disputed_lend()
        self.assertEqual(self._resolve(d2, {"outcome": "borrower"}).status_code, 200)  # note optional
        self.assertIn(d1, [r["id"] for r in self._admin_get("/disputes?status=resolved").json()])


if __name__ == "__main__":
    unittest.main()
