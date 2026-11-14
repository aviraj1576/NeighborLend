import io
import os
import sys
import time
import unittest
from datetime import datetime

os.environ.setdefault("DAMAGE_PROVIDER", "mock")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image
from starlette.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.services.auth import create_access_token

VIEWS = ("front", "back", "left", "right", "top", "bottom")


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


class TestDamageModuleMount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        users = {}
        for role in ("lender", "borrower", "intruder"):
            users[role] = User(
                name=f"Damage {role}", username=f"damage_{role}_{suffix}",
                email=f"damage_{role}_{suffix}@test.com", password_hash="test",
            )
        cls.db.add_all(users.values())
        cls.db.commit()
        cls.users = users
        cls.headers = {
            role: {"Authorization": f"Bearer {create_access_token(u.id)}"}
            for role, u in users.items()
        }

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _create_check(self):
        res = self.client.post(
            "/api/damage-checks",
            json={
                "request_id": "req-1",
                "lender_id": self.users["lender"].id,
                "borrower_id": self.users["borrower"].id,
                "item_class": "Drill",
            },
            headers=self.headers["lender"],
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["id"]

    def _upload(self, check_id, phase, view, role):
        return self.client.put(
            f"/api/damage-checks/{check_id}/photos/{phase}/{view}",
            files={"file": (f"{view}.png", PNG, "image/png")},
            headers=self.headers[role],
        )

    def test_full_flow(self):
        # 1. create
        check_id = self._create_check()
        res = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["lender"])
        self.assertEqual(res.json()["status"], "collecting")

        # 2. lender uploads all 6 before photos
        for view in VIEWS:
            self.assertEqual(self._upload(check_id, "before", view, "lender").status_code, 200)
        res = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["lender"])
        self.assertEqual(res.json()["missing_before"], [])

        # 3. wrong role / outsider
        self.assertEqual(self._upload(check_id, "before", "front", "borrower").status_code, 403)
        res = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["intruder"])
        self.assertEqual(res.status_code, 403)
        res = self.client.get(f"/api/damage-checks/{check_id}/photos/before/front",
                              headers=self.headers["intruder"])
        self.assertEqual(res.status_code, 403)
        res = self.client.get(f"/api/damage-checks/{check_id}")
        self.assertEqual(res.status_code, 401)

        # 4. fewer than 6 after photos -> analyze refused
        res = self.client.post(f"/api/damage-checks/{check_id}/analyze", headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 409)

        # 5. borrower uploads 6 after photos, analysis completes
        for view in VIEWS:
            self.assertEqual(self._upload(check_id, "after", view, "borrower").status_code, 200)
        res = self.client.post(f"/api/damage-checks/{check_id}/analyze", headers=self.headers["borrower"])
        self.assertEqual(res.status_code, 202, res.text)
        body = None
        for _ in range(20):
            body = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["lender"]).json()
            if body["status"] in ("done", "failed"):
                break
            time.sleep(0.2)
        self.assertEqual(body["status"], "done", body)
        self.assertEqual(body["report"]["overall"], "clear")
        self.assertEqual(body["report"]["model"], "mock")

        # photos can still be fetched by a participant, bytes round-trip
        res = self.client.get(f"/api/damage-checks/{check_id}/photos/after/top",
                              headers=self.headers["lender"])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/png")

        # 6. analyze again is idempotent and keeps the report
        res = self.client.post(f"/api/damage-checks/{check_id}/analyze", headers=self.headers["lender"])
        self.assertEqual(res.status_code, 202)
        again = self.client.get(f"/api/damage-checks/{check_id}", headers=self.headers["lender"]).json()
        self.assertEqual(again["status"], "done")
        self.assertEqual(again["report"]["generated_at"], body["report"]["generated_at"])

        # uploads are refused once analysis has run (double-submission guard)
        self.assertEqual(self._upload(check_id, "after", "front", "borrower").status_code, 409)

    def test_non_participant_cannot_create_check(self):
        res = self.client.post(
            "/api/damage-checks",
            json={"lender_id": self.users["lender"].id, "borrower_id": self.users["borrower"].id},
            headers=self.headers["intruder"],
        )
        self.assertEqual(res.status_code, 403)

    def test_rejects_non_image_upload(self):
        check_id = self._create_check()
        res = self.client.put(
            f"/api/damage-checks/{check_id}/photos/before/front",
            files={"file": ("x.png", b"not an image", "image/png")},
            headers=self.headers["lender"],
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
