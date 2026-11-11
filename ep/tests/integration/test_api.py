import hashlib


def test_health_readiness_openapi(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["pipeline"] == "unavailable"
    schema = client.get("/openapi.json").json()
    assert "/v1/evidence/{evidence_id}/content" in schema["paths"]


def test_evidence_roundtrip(client, upload, image_bytes, headers):
    original = image_bytes()
    response = upload(data=original)
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["sha256"] == hashlib.sha256(original).hexdigest()
    assert evidence["uploader_role"] == "lender"
    assert "storage_ref" not in evidence
    assert client.get(f"/v1/evidence/{evidence['id']}", headers=headers).json() == evidence
    result = client.get(f"/v1/evidence/{evidence['id']}/content", headers=headers)
    assert result.content == original
    assert result.headers["cache-control"] == "no-store"


def test_scoped_duplicate(upload, application):
    first = upload().json()
    second = upload()
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert len(list(application.state.storage.root.glob("*.original"))) == 1


def test_inspection_creation_truthful(client, evidence_pair, headers):
    response = client.post("/v1/inspections", json=evidence_pair, headers=headers)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["status"] == "created"
    assert record["result_status"] == "unavailable"
    assert record["completed_at"] is None
    assert client.get(f"/v1/inspections/{record['id']}", headers=headers).json() == record


def test_api_validation_and_errors(client, headers):
    for payload in ({}, {"rental_id": "rental-1", "reference_ids": [], "return_ids": []}):
        result = client.post("/v1/inspections", json=payload, headers=headers)
        assert result.status_code == 422
        assert result.json()["error"]["code"] == "invalid_request"
        assert result.json()["request_id"] == result.headers["x-request-id"]
    assert client.get("/v1/evidence/not-a-uuid", headers=headers).status_code == 422


def test_database_outage_is_sanitized(client, application, monkeypatch, headers):
    def fail():
        raise OSError("private/path SECRET")

    monkeypatch.setattr(application.state.repository, "check", fail)
    result = client.get("/ready")
    assert result.status_code == 503
    assert "SECRET" not in result.text


def test_unknown_route_is_consistent(client):
    result = client.get("/uploads/secret")
    assert result.status_code == 404
    assert result.json()["error"]["code"] == "http_error"
