import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ep_engine.config import Settings
from ep_engine.core.security import Grant, LocalAuthorization
from ep_engine.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart(session):
    if os.environ.get("EP_SYNTHETIC_ONLY") != "1":
        return
    excluded = [
        os.path.normcase(str(ROOT / name)) + os.sep
        for name in (
            "test_images",
            ".test-artifacts/real-image-evaluation",
        )
    ]

    def guard(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        if any(path == prefix[:-1] or path.startswith(prefix) for prefix in excluded):
            raise PermissionError("Exploratory image data is excluded from this milestone")

    sys.addaudithook(guard)


def pytest_collection_modifyitems(items):
    if os.environ.get("EP_SYNTHETIC_ONLY") == "1":
        for item in items:
            if item.get_closest_marker("real_inference") and not item.get_closest_marker(
                "controlled_inference"
            ):
                item.add_marker(
                    pytest.mark.skip(
                        reason="Synthetic-only milestone: existing test uses a bundled photograph"
                    )
                )


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    # Test lock/cache writes never touch the application's runtime directories.
    monkeypatch.setattr("ep_engine.cv.concurrency.LOCK_PATH", tmp_path / "worker.lock")
    monkeypatch.setattr("ep_engine.cv.models.EP_ROOT", tmp_path)
    for name in tuple(os.environ):
        if name.startswith("EP_VLM_"):
            monkeypatch.delenv(name)
    for name in (
        "GEMINI_API_KEY",
        "EP_DATA_DIR",
        "EP_LOCAL_GRANTS_FILE",
        "EP_MAX_UPLOAD_BYTES",
        "EP_MAX_PIXELS",
        "EP_MAX_DIMENSION",
        "EP_CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path):
    assert tmp_path.resolve().is_relative_to(ROOT / ".test-artifacts")
    return Settings(data_dir=tmp_path / "private")


@pytest.fixture
def auth():
    return LocalAuthorization(
        {
            "test-lender-token": Grant(subject="lender", rentals={"rental-1": "lender"}),
            "test-borrower-token": Grant(subject="borrower", rentals={"rental-1": "borrower"}),
            "test-other-token": Grant(subject="other", rentals={"rental-2": "lender"}),
        }
    )


@pytest.fixture
def application(settings, auth):
    return create_app(settings, authorization=auth)


@pytest.fixture
def client(application):
    with TestClient(application, raise_server_exceptions=False) as result:
        yield result


@pytest.fixture
def headers():
    return {"Authorization": "Bearer test-lender-token"}


@pytest.fixture
def image_bytes():
    def make(fmt="PNG", size=(24, 16), color="navy", exif=None):
        output = io.BytesIO()
        options = {"exif": exif} if exif else {}
        Image.new("RGB", size, color).save(output, format=fmt, **options)
        return output.getvalue()

    return make


@pytest.fixture
def upload(client, headers, image_bytes):
    def send(stage="before", rental="rental-1", data=None, token=None, **metadata):
        return client.post(
            "/v1/evidence",
            headers={"Authorization": f"Bearer {token}"} if token else headers,
            params={"rental_id": rental, "stage": stage, "viewpoint": "front", **metadata},
            content=image_bytes() if data is None else data,
        )

    return send


@pytest.fixture
def evidence_pair(upload, image_bytes):
    before = upload().json()
    after = upload(stage="after", token="test-borrower-token", data=image_bytes(color="red")).json()
    return {"rental_id": "rental-1", "reference_ids": [before["id"]], "return_ids": [after["id"]]}
