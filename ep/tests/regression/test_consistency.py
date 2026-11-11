import os
from concurrent.futures import ThreadPoolExecutor

import pytest


def test_second_file_failure_never_leaves_original(client, upload, application, monkeypatch):
    """Failure between original and derivative promotion must roll back both."""
    replace = os.replace

    def fail_derivative(source, target):
        if target.suffix == ".png":
            raise OSError("simulated full disk")
        return replace(source, target)

    monkeypatch.setattr("ep_engine.storage.local.os.replace", fail_derivative)
    assert upload().status_code == 503
    assert list(application.state.storage.root.iterdir()) == []
    with application.state.repository.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0


def test_concurrent_duplicates_share_one_record(client, upload, application):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: upload(), range(6)))
    assert sorted(response.status_code for response in results) == [200, 200, 200, 200, 200, 201]
    assert len({response.json()["id"] for response in results}) == 1
    assert len(list(application.state.storage.root.iterdir())) == 2


def test_real_database_insert_failure_cleans_files(client, upload, application):
    with application.state.repository.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_upload BEFORE INSERT ON evidence "
            "BEGIN SELECT RAISE(ABORT, 'test rejection'); END"
        )
    result = upload()
    assert result.status_code == 503
    assert list(application.state.storage.root.iterdir()) == []


def test_invalid_duplicate_cannot_report_success(
    client, application, upload, evidence_pair, headers
):
    record = application.state.repository.get_evidence(evidence_pair["reference_ids"][0])
    record.validation_status = "invalid"
    with application.state.repository.transaction() as connection:
        connection.execute(
            "UPDATE evidence SET record=? WHERE id=?", (record.model_dump_json(), str(record.id))
        )
    assert upload().status_code == 409
    assert client.post("/v1/inspections", json=evidence_pair, headers=headers).status_code == 409


def test_storage_rejects_path_escape_and_schema_downgrade(client, application):
    from ep_engine.storage.repository import Repository

    with pytest.raises(ValueError):
        application.state.storage.path("../../secret", "original")
    with pytest.raises(ValueError):
        application.state.storage.path("00000000-0000-0000-0000-000000000000", "exe")
    with application.state.repository.transaction() as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError):
        Repository(application.state.repository.path).initialize()


def test_unexpected_service_error_has_correlation_and_no_secret(
    client, application, upload, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("secret runtime exception")

    monkeypatch.setattr(application.state.evidence, "ingest", fail)
    result = upload()
    assert result.status_code == 500
    assert result.json()["request_id"] == result.headers["x-request-id"]
    assert "secret" not in result.text
