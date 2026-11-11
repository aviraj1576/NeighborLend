import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ep_engine.core.exceptions import EPError
from ep_engine.main import create_app


def test_restart_persists_evidence_and_inspections(
    client, application, settings, auth, upload, evidence_pair, headers
):
    inspection = client.post("/v1/inspections", headers=headers, json=evidence_pair).json()
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        assert (
            restarted.get(f"/v1/inspections/{inspection['id']}", headers=headers).json()
            == inspection
        )
        evidence_id = evidence_pair["reference_ids"][0]
        assert (
            restarted.get(f"/v1/evidence/{evidence_id}/content", headers=headers).status_code == 200
        )


@pytest.mark.parametrize("failure", ["write", "insert"])
def test_upload_failure_rolls_back(client, application, upload, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise OSError("sensitive database path")

    if failure == "write":
        monkeypatch.setattr(application.state.storage, "write", fail)
    else:
        monkeypatch.setattr(application.state.repository, "insert_evidence", fail)
    result = upload()
    assert result.status_code == 503
    assert "sensitive" not in result.text
    assert list(application.state.storage.root.iterdir()) == []
    with application.state.repository.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0


def test_restart_recovers_orphans_missing_and_inflight(
    client, settings, auth, application, upload, evidence_pair, headers
):
    record = client.post("/v1/inspections", headers=headers, json=evidence_pair).json()
    repository = application.state.repository
    repository.transition(record["id"], "queued")
    repository.transition(record["id"], "processing")
    root = application.state.storage.root
    orphan = root / f"{uuid4()}.original"
    orphan.write_bytes(b"crashed upload")
    pending = root / f"{uuid4()}.part"
    pending.write_bytes(b"partial")
    evidence_id = evidence_pair["reference_ids"][0]
    (root / f"{evidence_id}.original").unlink()
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        assert not orphan.exists()
        assert not pending.exists()
        failed = restarted.get(f"/v1/inspections/{record['id']}", headers=headers).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "restart_interrupted"
        assert (
            restarted.get(f"/v1/evidence/{evidence_id}", headers=headers).json()[
                "validation_status"
            ]
            == "invalid"
        )
        assert (
            restarted.get(f"/v1/evidence/{evidence_id}/content", headers=headers).status_code == 409
        )


def test_state_machine_no_false_completion(client, application, evidence_pair, headers):
    record = client.post("/v1/inspections", headers=headers, json=evidence_pair).json()
    repository = application.state.repository
    with pytest.raises(EPError):
        repository.transition(record["id"], "processing")
    repository.transition(record["id"], "queued")
    with pytest.raises(EPError):
        repository.transition(record["id"], "queued")
    repository.transition(record["id"], "processing")
    with pytest.raises(EPError):
        repository.transition(record["id"], "completed")
    repository.transition(record["id"], "failed", error_code="pipeline_unavailable")
    assert repository.get_inspection(record["id"]).error_code == "pipeline_unavailable"
    with pytest.raises(EPError):
        repository.transition(record["id"], "queued")


def test_inspection_rejects_wrong_stage_missing_ids(client, evidence_pair, headers):
    evidence_pair["reference_ids"], evidence_pair["return_ids"] = (
        evidence_pair["return_ids"],
        evidence_pair["reference_ids"],
    )
    assert client.post("/v1/inspections", headers=headers, json=evidence_pair).status_code == 422
    evidence_pair["reference_ids"] = [str(uuid4())]
    assert client.post("/v1/inspections", headers=headers, json=evidence_pair).status_code == 422


def test_foreign_keys_and_schema_version(client, application):
    with application.state.repository.transaction() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO inspection_evidence VALUES ('missing', 'missing')")


def test_cancelled_inspection_is_persisted_terminal_state(
    client, application, evidence_pair, headers
):
    record = client.post("/v1/inspections", headers=headers, json=evidence_pair).json()
    cancelled = application.state.repository.transition(record["id"], "cancelled")
    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None
    assert (
        client.get(f"/v1/inspections/{record['id']}", headers=headers).json()["status"]
        == "cancelled"
    )
    with pytest.raises(EPError):
        application.state.repository.transition(record["id"], "queued")
