import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, get_db, migrate_schema
from app.main import app
from app.models import BorrowRequest, EmailVerification, Listing, ListingStatus, Notification, User
from app.routers.auth import settings as auth_settings
from app.services.auth import create_access_token, issue_captcha


class TestAuthenticationAndInbox(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'test.db')}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.db = self.session_factory()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _captcha(self):
        challenge = issue_captcha(self.db)
        first, second = challenge["question"].split(" = ?")[0].split(" + ")
        return challenge["captcha_id"], int(first) + int(second)

    def _user(self, name, username, email):
        user = User(
            name=name,
            username=username,
            email=email,
            password_hash="unused",
            is_verified=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _headers(self, user):
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    def test_existing_database_migration_is_additive_and_idempotent(self):
        legacy_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text("CREATE TABLE users (id VARCHAR PRIMARY KEY)"))
                connection.execute(text("CREATE TABLE borrow_requests (id VARCHAR PRIMARY KEY)"))
                connection.execute(text("INSERT INTO users (id) VALUES ('legacy-user')"))

            with patch("app.database.engine", legacy_engine):
                migrate_schema()
                migrate_schema()

            with legacy_engine.connect() as connection:
                user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
                request_columns = {
                    column["name"] for column in inspect(connection).get_columns("borrow_requests")
                }
                verified = connection.execute(
                    text("SELECT is_verified FROM users WHERE id = 'legacy-user'")
                ).scalar_one()

            self.assertTrue({"is_verified", "google_sub"}.issubset(user_columns))
            self.assertTrue(
                {"returned_at", "disputed_at", "dispute_description"}.issubset(request_columns)
            )
            self.assertTrue(verified)
        finally:
            legacy_engine.dispose()

    def test_registration_requires_otp_and_enforces_attempts_and_resend_cooldown(self):
        captcha_id, captcha_answer = self._captcha()
        with patch("app.routers.auth.send_verification_code") as send_email:
            response = self.client.post("/api/auth/register", json={
                "name": "New Neighbor",
                "username": "newneighbor",
                "email": "new@example.com",
                "password": "password123",
                "captcha_id": captcha_id,
                "captcha_answer": captcha_answer,
            })
            self.assertEqual(response.status_code, 202)
            self.assertNotIn("access_token", response.json())
            code = send_email.call_args.args[1]
            user = self.db.query(User).filter_by(email="new@example.com").one()
            verification = self.db.get(EmailVerification, user.id)
            self.assertNotEqual(verification.code_hash, code)

            login = self.client.post("/api/auth/login", json={
                "username_or_email": "new@example.com",
                "password": "password123",
            })
            self.assertEqual(login.status_code, 403)

            wrong_code = self.client.post("/api/auth/verify-email", json={
                "email": "new@example.com",
                "code": "000000" if code != "000000" else "000001",
            })
            self.assertEqual(wrong_code.status_code, 400)
            self.db.expire_all()
            verification = self.db.get(EmailVerification, user.id)
            self.assertEqual(verification.attempts, 1)

            immediate_resend = self.client.post("/api/auth/resend-verification", json={
                "email": "new@example.com",
            })
            self.assertEqual(immediate_resend.status_code, 429)

            verification.last_sent_at = datetime.utcnow() - timedelta(seconds=61)
            self.db.commit()
            resent = self.client.post("/api/auth/resend-verification", json={
                "email": "new@example.com",
            })
            self.assertEqual(resent.status_code, 200)
            new_code = send_email.call_args.args[1]

            verified = self.client.post("/api/auth/verify-email", json={
                "email": "new@example.com",
                "code": new_code,
            })
            self.assertEqual(verified.status_code, 200)
            login = self.client.post("/api/auth/login", json={
                "username_or_email": "new@example.com",
                "password": "password123",
            })
            self.assertEqual(login.status_code, 200)

    def test_google_sign_in_verifies_claims_before_issuing_token(self):
        payload = {
            "sub": "google-user-001",
            "email": "google@example.com",
            "email_verified": True,
            "name": "Google Neighbor",
        }
        with patch.object(auth_settings, "google_client_id", "client-id"), \
             patch("app.routers.auth.id_token.verify_oauth2_token", return_value=payload) as verify_token:
            response = self.client.post("/api/auth/google", json={"credential": "signed-id-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], "google@example.com")
        verify_token.assert_called_once()
        self.assertEqual(verify_token.call_args.args[2], "client-id")
        user = self.db.query(User).filter_by(google_sub="google-user-001").one()
        self.assertTrue(user.is_verified)

    def test_otp_attempt_limit_and_expiry_are_enforced(self):
        captcha_id, captcha_answer = self._captcha()
        with patch("app.routers.auth.send_verification_code") as send_email:
            response = self.client.post("/api/auth/register", json={
                "name": "Limited Neighbor",
                "username": "limitedneighbor",
                "email": "limited@example.com",
                "password": "password123",
                "captcha_id": captcha_id,
                "captcha_answer": captcha_answer,
            })
            self.assertEqual(response.status_code, 202)
            valid_code = send_email.call_args.args[1]
            invalid_code = "000000" if valid_code != "000000" else "000001"

            for attempt in range(5):
                result = self.client.post("/api/auth/verify-email", json={
                    "email": "limited@example.com",
                    "code": invalid_code,
                })
                self.assertEqual(result.status_code, 429 if attempt == 4 else 400)

            blocked_correct_code = self.client.post("/api/auth/verify-email", json={
                "email": "limited@example.com",
                "code": valid_code,
            })
            self.assertEqual(blocked_correct_code.status_code, 429)

        captcha_id, captcha_answer = self._captcha()
        with patch("app.routers.auth.send_verification_code") as send_email:
            self.client.post("/api/auth/register", json={
                "name": "Expired Neighbor",
                "username": "expiredneighbor",
                "email": "expired@example.com",
                "password": "password123",
                "captcha_id": captcha_id,
                "captcha_answer": captcha_answer,
            })
            expired_code = send_email.call_args.args[1]

        expired_user = self.db.query(User).filter_by(email="expired@example.com").one()
        verification = self.db.get(EmailVerification, expired_user.id)
        verification.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        expired = self.client.post("/api/auth/verify-email", json={
            "email": "expired@example.com",
            "code": expired_code,
        })
        self.assertEqual(expired.status_code, 400)

    def test_notifications_are_private_and_can_be_marked_read(self):
        owner = self._user("Owner", "owner1", "owner1@example.com")
        other = self._user("Other", "other1", "other1@example.com")
        notification = Notification(
            user_id=owner.id,
            notification_type="approval",
            title="Approved",
            message="Your offer was approved.",
            link_url="/messages/conversation-1",
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        response = self.client.get("/api/notifications", headers=self._headers(owner))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [notification.id])
        self.assertEqual(
            self.client.get("/api/notifications/unread-count", headers=self._headers(owner)).json()["unread_count"],
            1,
        )
        forbidden = self.client.patch(
            f"/api/notifications/{notification.id}/read",
            headers=self._headers(other),
        )
        self.assertEqual(forbidden.status_code, 404)

        marked = self.client.patch(
            f"/api/notifications/{notification.id}/read",
            headers=self._headers(owner),
        )
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.json()["is_read"])

    def test_new_borrow_request_notifies_matching_lenders(self):
        lender = self._user("Tool Lender", "toollender", "toollender@example.com")
        borrower = self._user("Tool Borrower", "toolborrower", "toolborrower@example.com")
        self.db.add(Listing(
            owner_id=lender.id,
            name="Power drill",
            category="Tools",
            price_per_day=15,
            status=ListingStatus.published,
        ))
        self.db.commit()

        response = self.client.post(
            "/api/borrow-requests",
            json={"title": "Need a drill", "category": "Tools", "max_price_per_day": 20},
            headers=self._headers(borrower),
        )
        self.assertEqual(response.status_code, 200)
        borrow_request_id = response.json()["id"]
        notification = self.db.query(Notification).filter_by(user_id=lender.id).one()
        self.assertEqual(notification.notification_type, "borrowing_request")
        self.assertEqual(notification.borrow_request_id, borrow_request_id)
        self.assertEqual(notification.link_url, f"/borrow-requests/{borrow_request_id}")

    def test_rental_return_and_dispute_notify_only_the_other_participant(self):
        lender = self._user("Lender", "lender1", "lender1@example.com")
        borrower = self._user("Borrower", "borrower1", "borrower1@example.com")
        listing = Listing(
            owner_id=lender.id,
            name="Drill",
            category="Tools",
            price_per_day=10,
            status=ListingStatus.published,
        )
        self.db.add(listing)
        self.db.flush()
        request = BorrowRequest(
            borrower_id=borrower.id,
            listing_id=listing.id,
            title="Rental: Drill",
            category="Tools",
        )
        self.db.add(request)
        self.db.commit()
        request_id = request.id

        returned = self.client.post(
            f"/api/borrow-requests/{request_id}/return",
            headers=self._headers(borrower),
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(
            self.client.post(
                f"/api/borrow-requests/{request_id}/dispute",
                json={"description": "The tool was damaged."},
                headers=self._headers(borrower),
            ).status_code,
            200,
        )
        notification_types = {
            notification.notification_type
            for notification in self.db.query(Notification).filter_by(user_id=lender.id).all()
        }
        self.assertEqual(notification_types, {"return", "dispute"})
        self.assertEqual(self.db.query(Notification).filter_by(user_id=borrower.id).count(), 0)


if __name__ == "__main__":
    unittest.main()
