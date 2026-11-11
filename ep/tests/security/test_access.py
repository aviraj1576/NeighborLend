from fastapi.testclient import TestClient

from ep_engine.main import create_app


def test_fail_closed_without_configuration(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 503
        assert (
            client.post("/v1/evidence?rental_id=rental-1&stage=before", content=b"x").status_code
            == 503
        )


def test_no_identity_from_client(client, upload, headers):
    for token in (None, "Bearer forged", "Basic test-lender-token"):
        response = client.get(
            "/v1/evidence/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": token}
            if token
            else {"X-User-ID": "lender", "X-Role": "lender"},
        )
        assert response.status_code == 401
    assert upload(stage="after").status_code == 403
    assert upload(rental="rental-2").status_code == 403
    assert upload(stage="before", token="test-borrower-token").status_code == 403


def test_cross_rental_reads_and_inspections(client, upload, evidence_pair, headers):
    evidence_id = evidence_pair["reference_ids"][0]
    foreign = {"Authorization": "Bearer test-other-token"}
    for suffix in ("", "/content"):
        assert client.get(f"/v1/evidence/{evidence_id}{suffix}", headers=foreign).status_code == 403
    inspection = client.post("/v1/inspections", headers=headers, json=evidence_pair).json()
    assert client.get(f"/v1/inspections/{inspection['id']}", headers=foreign).status_code == 403
    other = upload(rental="rental-2", token="test-other-token").json()
    evidence_pair["reference_ids"] = [other["id"]]
    assert client.post("/v1/inspections", headers=headers, json=evidence_pair).status_code == 422


def test_filename_and_metadata_cannot_escape(client, upload, application):
    result = upload(viewpoint="../../private", filename="../../secret.png")
    assert result.status_code == 201
    files = list(application.state.storage.root.iterdir())
    assert all(item.parent == application.state.storage.root for item in files)
    assert not (application.state.storage.root.parent / "secret.png").exists()


def test_tamper_detection(client, upload, application, headers):
    record = upload().json()
    original = application.state.storage.root / f"{record['id']}.original"
    original.write_bytes(b"tampered")
    response = client.get(f"/v1/evidence/{record['id']}/content", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "integrity_failure"


def test_cors_default_denies_origin(client):
    result = client.options(
        "/v1/evidence",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in result.headers


def test_derivative_tampering_blocks_inspection_and_duplicates(
    client, upload, application, evidence_pair, headers
):
    evidence_id = evidence_pair["reference_ids"][0]
    (application.state.storage.root / f"{evidence_id}.png").write_bytes(b"tampered derivative")
    assert upload().status_code == 409
    result = client.post("/v1/inspections", json=evidence_pair, headers=headers)
    assert result.status_code == 409
    with application.state.repository.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM inspections").fetchone()[0] == 0
