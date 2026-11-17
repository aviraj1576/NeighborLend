import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from storage3.exceptions import StorageApiError

from app.services import storage_service


PROJECT_REF = "neighborlendprojectref"


class FakeStorage:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def get_bucket(self, name):
        self.calls.append(name)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def storage_setup(monkeypatch):
    fake_storage = FakeStorage(result={"public": True})
    monkeypatch.setattr(storage_service, "supabase", SimpleNamespace(storage=fake_storage))
    monkeypatch.setattr(storage_service, "_public_bucket_ready", False)
    monkeypatch.setattr(storage_service.settings, "supabase_url", f"https://{PROJECT_REF}.supabase.co")
    monkeypatch.setattr(storage_service.settings, "supabase_service_role_key", "test-service-role-key")
    return fake_storage


def _legacy_service_key(project_ref):
    payload = base64.urlsafe_b64encode(
        json.dumps({"ref": project_ref, "role": "service_role"}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_bucket_lookup_success_marks_existing_public_bucket_ready(storage_setup):
    storage_service._ensure_public_bucket()

    assert storage_setup.calls == ["listing_photos"]
    assert storage_service._public_bucket_ready is True


def test_private_bucket_is_rejected(storage_setup):
    storage_setup.result = {"public": False}

    with pytest.raises(HTTPException) as exc_info:
        storage_service._ensure_public_bucket()

    assert exc_info.value.status_code == 503
    assert "public" in exc_info.value.detail


@pytest.mark.parametrize(
    "error,expected_status,expected_code",
    [
        (StorageApiError("Bucket not found", "BucketNotFound", 404), "404", "BucketNotFound"),
        (StorageApiError("Invalid API key", "InvalidJWT", 401), "401", "InvalidJWT"),
        (httpx.ConnectError("Storage API connection failed"), "unavailable", "unavailable"),
    ],
    ids=["missing-bucket", "invalid-credentials", "connectivity-failure"],
)
def test_bucket_lookup_failures_log_safe_diagnostics(
    storage_setup, caplog, error, expected_status, expected_code,
):
    storage_setup.error = error

    with pytest.raises(HTTPException) as exc_info:
        storage_service._ensure_public_bucket()

    assert exc_info.value.status_code == 503
    assert "Supabase Storage bucket lookup failed" in caplog.text
    assert f"exception_class={type(error).__name__}" in caplog.text
    assert f"http_status={expected_status}" in caplog.text
    assert f"error_code={expected_code}" in caplog.text
    assert "project_binding=unverifiable" in caplog.text
    assert "test-service-role-key" not in caplog.text


def test_mismatched_legacy_service_key_project_is_rejected_without_logging_key(
    storage_setup, monkeypatch, caplog,
):
    secret_key = _legacy_service_key("anotherprojectref")
    monkeypatch.setattr(storage_service.settings, "supabase_service_role_key", secret_key)

    with pytest.raises(HTTPException) as exc_info:
        storage_service._ensure_public_bucket()

    assert exc_info.value.status_code == 503
    assert "same Supabase project" in exc_info.value.detail
    assert storage_setup.calls == []
    assert "project_binding=mismatch" in caplog.text
    assert secret_key not in caplog.text


def test_matching_legacy_service_key_project_is_detected(storage_setup, monkeypatch):
    monkeypatch.setattr(
        storage_service.settings,
        "supabase_service_role_key",
        _legacy_service_key(PROJECT_REF),
    )

    assert storage_service._project_binding_status() == "match"


def test_safe_diagnostic_redacts_credentials_and_url_query(storage_setup):
    message = (
        "Authorization: test-service-role-key; "
        "Bearer eyJhbGci.signature.payload; "
        "https://project.supabase.co/storage/v1?apikey=do-not-log"
    )

    safe = storage_service._safe_diagnostic_value(message)

    assert "test-service-role-key" not in safe
    assert "eyJhbGci.signature.payload" not in safe
    assert "do-not-log" not in safe
    assert "https://project.supabase.co/storage/v1" in safe
