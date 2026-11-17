import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import Listing, ListingPhoto, User
from app.routers import uploads as upload_router
from app.services import storage_service
from app.services.auth import create_access_token
from scripts.migrate_listing_photos_to_supabase import _legacy_relative_path


class _FakeBucket:
    def __init__(self):
        self.objects = {}

    def upload(self, path, data, file_options):
        self.objects[path] = {"bytes": data, "options": file_options}

    def get_public_url(self, path):
        return f"{TEST_SUPABASE_URL}/storage/v1/object/public/{storage_service.LISTING_PHOTOS_BUCKET}/{path}"


class _FakeStorage:
    def __init__(self):
        self.bucket = _FakeBucket()

    def from_(self, bucket_name):
        if bucket_name != storage_service.LISTING_PHOTOS_BUCKET:
            raise AssertionError(f"Unexpected bucket: {bucket_name}")
        return self.bucket

    def get_bucket(self, bucket_name):
        if bucket_name != storage_service.LISTING_PHOTOS_BUCKET:
            raise AssertionError(f"Unexpected bucket: {bucket_name}")
        return {"public": True}

    def create_bucket(self, *_args, **_kwargs):
        raise AssertionError("The uploader must not create a bucket")

    def update_bucket(self, *_args, **_kwargs):
        raise AssertionError("The uploader must not change bucket configuration")


class _FakeSupabase:
    def __init__(self):
        self.storage = _FakeStorage()


TEST_SUPABASE_URL = "https://neighborlend-test.supabase.co"


class TestSupabasePhotoUploads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        cls.old_supabase = storage_service.supabase
        cls.old_ready = storage_service._public_bucket_ready
        cls.old_supabase_url = storage_service.settings.supabase_url
        cls.old_detector = upload_router.detect_objects
        storage_service.supabase = _FakeSupabase()
        storage_service._public_bucket_ready = True
        storage_service.settings.supabase_url = TEST_SUPABASE_URL
        upload_router.detect_objects = lambda _image_bytes: []

        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        cls.user = User(
            name="Photo Upload Test", username=f"photo_user_{suffix}",
            email=f"photo_user_{suffix}@test.com", password_hash="test",
        )
        cls.db.add(cls.user)
        cls.db.commit()
        cls.db.refresh(cls.user)
        cls.headers = {"Authorization": f"Bearer {create_access_token(cls.user.id)}"}

    @classmethod
    def tearDownClass(cls):
        listing_ids = [row.id for row in cls.db.query(Listing.id).filter_by(owner_id=cls.user.id).all()]
        if listing_ids:
            cls.db.query(ListingPhoto).filter(ListingPhoto.listing_id.in_(listing_ids)).delete(synchronize_session=False)
            cls.db.query(Listing).filter(Listing.id.in_(listing_ids)).delete(synchronize_session=False)
        cls.db.query(User).filter_by(id=cls.user.id).delete()
        cls.db.commit()
        cls.db.close()
        storage_service.supabase = cls.old_supabase
        storage_service._public_bucket_ready = cls.old_ready
        storage_service.settings.supabase_url = cls.old_supabase_url
        upload_router.detect_objects = cls.old_detector

    def test_upload_returns_supabase_url_and_listing_preserves_cover_relation(self):
        upload = self.client.post(
            "/api/upload",
            headers=self.headers,
            files={"file": ("tool.jpg", b"test-image-bytes", "image/jpeg")},
        )
        self.assertEqual(upload.status_code, 200)
        image_url = upload.json()["url"]
        self.assertTrue(image_url.startswith(
            f"{TEST_SUPABASE_URL}/storage/v1/object/public/{storage_service.LISTING_PHOTOS_BUCKET}/images/"
        ))
        self.assertEqual(len(storage_service.supabase.storage.bucket.objects), 1)
        listing_response = self.client.post(
            "/api/listings",
            headers=self.headers,
            json={"name": "Photo-backed listing", "category": "Tools", "price_per_day": 12, "photo_urls": [image_url]},
        )
        self.assertEqual(listing_response.status_code, 200)
        listing_id = listing_response.json()["id"]
        photo = self.db.query(ListingPhoto).filter_by(listing_id=listing_id).one()
        self.assertEqual(photo.url, image_url)
        self.assertTrue(photo.is_cover)
        self.assertEqual(listing_response.json()["photos"], [image_url])

    def test_existing_bucket_is_checked_without_creating_or_changing_it(self):
        storage_service._public_bucket_ready = False
        storage_service._ensure_public_bucket()
        self.assertTrue(storage_service._public_bucket_ready)

    def test_upload_requires_auth_and_supabase_configuration(self):
        unauthorized = self.client.post(
            "/api/upload", files={"file": ("tool.jpg", b"image", "image/jpeg")}
        )
        self.assertEqual(unauthorized.status_code, 401)

        real_client = storage_service.supabase
        storage_service.supabase = None
        try:
            unavailable = self.client.post(
                "/api/upload",
                headers=self.headers,
                files={"file": ("tool.jpg", b"image", "image/jpeg")},
            )
        finally:
            storage_service.supabase = real_client
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", unavailable.json()["detail"])

    def test_listing_allows_localhost_photo_urls_in_dev(self):
        response = self.client.post(
            "/api/listings",
            headers=self.headers,
            json={
                "name": "Local photo listing",
                "category": "Tools",
                "price_per_day": 12,
                "photo_urls": ["http://localhost:8000/uploads/images/old.jpg"],
            },
        )
        # In development (test env), local URLs are allowed
        self.assertEqual(response.status_code, 200)

    def test_migration_accepts_only_local_upload_paths_and_blocks_traversal(self):
        legacy = _legacy_relative_path(
            "http://localhost:8000/uploads/images/old.jpg",
            "http://localhost:8000",
        )
        self.assertEqual(legacy.as_posix(), "images/old.jpg")
        self.assertIsNone(_legacy_relative_path(
            "https://outside.example/uploads/images/old.jpg",
            "http://localhost:8000",
        ))
        self.assertIsNone(_legacy_relative_path(
            "http://localhost:8000/uploads/../../.env",
            "http://localhost:8000",
        ))


if __name__ == "__main__":
    unittest.main()
