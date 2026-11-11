import sqlite3
from contextlib import contextmanager
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ep_engine.core.exceptions import EPError
from ep_engine.cv.artifacts import ArtifactWriter
from ep_engine.cv.pipeline import CVPipeline
from ep_engine.cv.worker import load_inputs
from ep_engine.main import create_app


def software_executor(payload, output, cancelled):
    """No pretrained claim: real low-quality gating plus a synthetic storage-test artifact."""
    from ep_engine.cv.contracts import CVConfig

    package = CVPipeline(CVConfig.model_validate(payload["config"])).run(
        uuid4() if payload.get("forge") else __import__("uuid").UUID(payload["inspection_id"]),
        load_inputs(payload),
        output,
    )
    writer = ArtifactWriter(output, package.source_ids)
    writer.save("object_mask", np.full((20, 20), 128, np.uint8), [package.source_ids[0]])
    package.artifacts = writer.records
    return package


@pytest.fixture
def cv_run(client, evidence_pair, headers):
    inspection = client.post("/v1/inspections", json=evidence_pair, headers=headers).json()
    result = client.post(f"/v1/inspections/{inspection['id']}/cv-runs", json={}, headers=headers)
    assert result.status_code == 202, result.text
    return result.json()


def lender(auth):
    return auth.authenticate("Bearer test-lender-token")


@pytest.mark.parametrize("mutation", ["thresholds", "source_dimensions", "processing_dimensions"])
def test_worker_cannot_change_the_approved_coordinate_or_threshold_manifest(
    client, application, cv_run, auth, headers, mutation
):
    def forged(payload, output, cancelled):
        package = software_executor(payload, output, cancelled)
        if mutation == "thresholds":
            package.thresholds.min_similarity = 0.01
        elif mutation == "source_dimensions":
            package.source_dimensions[package.source_ids[0]] = (900, 900)
        else:
            package.processing_dimensions[package.source_ids[0]] = (900, 900)
        return package

    service = application.state.cv
    with pytest.raises((EPError, ValueError)):
        service.execute(cv_run["id"], lender(auth), forged)
    assert service.get(cv_run["id"], lender(auth))[0].status == "failed"
    assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 409
    assert (
        client.post(f"/v1/cv-runs/{cv_run['id']}/assessments", json={}, headers=headers).status_code
        == 409
    )


@pytest.mark.parametrize("tamper", ["source", "thresholds"])
def test_stale_or_forged_persisted_cv_cannot_reach_assessment(
    client, application, cv_run, auth, headers, tamper
):
    service = application.state.cv
    package = service.execute(cv_run["id"], lender(auth), software_executor)
    if tamper == "source":
        application.state.storage.path(str(package.source_ids[0]), "original").write_bytes(
            b"tampered"
        )
    else:
        package.thresholds.min_similarity = 0.01
        with service.store.db.transaction() as connection:
            connection.execute(
                "UPDATE runs SET result=? WHERE id=?", (package.model_dump_json(), cv_run["id"])
            )
    assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 409
    artifact_id = package.artifacts[0].id
    assert (
        client.get(
            f"/v1/cv-runs/{cv_run['id']}/artifacts/{artifact_id}", headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(f"/v1/cv-runs/{cv_run['id']}/assessments", json={}, headers=headers).status_code
        == 409
    )


def test_cv_result_private_artifacts_and_parent_semantics(
    client, application, cv_run, auth, headers
):
    service = application.state.cv
    assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 409
    package = service.execute(cv_run["id"], lender(auth), software_executor)
    assert package.outcome == "inconclusive"
    result = client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers)
    assert result.status_code == 200
    key = result.json()["artifacts"][0]["id"]
    route = f"/v1/cv-runs/{cv_run['id']}/artifacts/{key}"
    response = client.get(route, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"\x89PNG")
    assert "storage_ref" not in result.text and str(service.store.root) not in result.text
    assert (
        client.get(f"/v1/inspections/{cv_run['inspection_id']}", headers=headers).json()["status"]
        == "created"
    )
    with pytest.raises(EPError):
        service.execute(cv_run["id"], lender(auth), software_executor)
    assert (
        client.get(f"/v1/cv-runs/{cv_run['id']}/artifacts/{uuid4()}", headers=headers).status_code
        == 404
    )


def test_cv_authorization_forgery_and_cancellation(client, application, cv_run, auth, headers):
    foreign = {"Authorization": "Bearer test-other-token"}
    for suffix in ("", "/result", f"/artifacts/{uuid4()}"):
        assert client.get(f"/v1/cv-runs/{cv_run['id']}{suffix}", headers=foreign).status_code == 403
        assert client.get(f"/v1/cv-runs/{cv_run['id']}{suffix}").status_code == 401
    assert (
        client.post(
            f"/v1/cv-runs/{cv_run['id']}/cancel",
            headers={"Authorization": "Bearer test-borrower-token"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/v1/inspections/{cv_run['inspection_id']}/cv-runs",
            json={"targets": {str(uuid4()): {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9}}},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/v1/inspections/{cv_run['inspection_id']}/cv-runs", json={}, headers=foreign
        ).status_code
        == 403
    )
    assert (
        client.post(f"/v1/cv-runs/{cv_run['id']}/cancel", headers=headers).json()["status"]
        == "cancelled"
    )
    with pytest.raises(EPError):
        application.state.cv.execute(cv_run["id"], lender(auth), software_executor)


@pytest.mark.parametrize("error", ["model_oom", "inference_timeout", "model_load_failed"])
def test_worker_failure_never_commits_artifacts(client, application, cv_run, auth, error):
    def failing(payload, output, cancelled):
        output.mkdir(parents=True)
        (output / "partial.png").write_bytes(b"partial")
        raise EPError(503, error, "Injected failure")

    with pytest.raises(EPError):
        application.state.cv.execute(cv_run["id"], lender(auth), failing)
    run = application.state.cv.get(cv_run["id"], lender(auth))[0]
    assert run.status == "failed" and run.error_code == error
    assert list(application.state.cv.store.artifacts.iterdir()) == []
    assert list(application.state.cv.store.work.iterdir()) == []


def test_restart_and_integrity_checks(client, application, settings, auth, cv_run, headers):
    package = application.state.cv.execute(cv_run["id"], lender(auth), software_executor)
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        assert (
            restarted.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 200
        )
    artifact = (
        application.state.cv.store.artifacts / cv_run["id"] / f"{package.artifacts[0].id}.png"
    )
    artifact.write_bytes(b"tampered")
    assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 409
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        record = restarted.get(f"/v1/cv-runs/{cv_run['id']}", headers=headers).json()
        assert record["status"] == "failed" and record["error_code"] == "artifact_integrity"


def test_queue_bound_and_restart_of_processing(
    client, application, cv_run, settings, auth, headers
):
    for _ in range(3):
        assert (
            client.post(
                f"/v1/inspections/{cv_run['inspection_id']}/cv-runs", json={}, headers=headers
            ).status_code
            == 202
        )
    assert (
        client.post(
            f"/v1/inspections/{cv_run['inspection_id']}/cv-runs", json={}, headers=headers
        ).status_code
        == 429
    )
    application.state.cv.store.claim(cv_run["id"])
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        record = restarted.get(f"/v1/cv-runs/{cv_run['id']}", headers=headers).json()
        assert record["status"] == "failed" and record["error_code"] == "worker_interrupted"


def test_commit_failure_removes_promoted_artifacts(client, application, cv_run, auth, monkeypatch):
    store = application.state.cv.store
    real_finish = store.finish

    def fail_commit(run_id, package, output):
        transaction = store.db.transaction

        @contextmanager
        def failing():
            with transaction() as connection:
                yield connection
                raise sqlite3.OperationalError("commit failure")

        with monkeypatch.context() as context:
            context.setattr(store.db, "transaction", failing)
            return real_finish(run_id, package, output)

    monkeypatch.setattr(store, "finish", fail_commit)
    with pytest.raises(sqlite3.Error):
        application.state.cv.execute(cv_run["id"], lender(auth), software_executor)
    assert list(store.artifacts.iterdir()) == []


def test_work_directory_failure_is_terminal(client, application, cv_run, auth, monkeypatch):
    from pathlib import Path

    mkdir = Path.mkdir
    directory = application.state.cv.store.work / cv_run["id"]

    def fail(self, *args, **kwargs):
        if self == directory:
            raise OSError("injected directory failure")
        return mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(OSError):
        application.state.cv.execute(cv_run["id"], lender(auth), software_executor)
    assert application.state.cv.get(cv_run["id"], lender(auth))[0].status == "failed"


@pytest.mark.parametrize("corrupt", [False, True])
def test_windows_directory_rename_fallback_is_verified_and_transactional(
    client, application, cv_run, auth, headers, monkeypatch, corrupt
):
    from pathlib import Path

    store = application.state.cv.store
    original_rename = Path.rename
    original_verify = store.verify_package_files

    def denied(self, target):
        if self.name == "output":
            error = PermissionError("Injected Windows directory handle contention")
            error.winerror = 5
            raise error
        return original_rename(self, target)

    def verify(run_id, package, directory=None):
        if corrupt and directory is not None and directory.parent == store.artifacts:
            next(directory.glob("*.png")).write_bytes(b"corrupt copy")
        return original_verify(run_id, package, directory)

    monkeypatch.setattr(Path, "rename", denied)
    monkeypatch.setattr(store, "verify_package_files", verify)
    if corrupt:
        with pytest.raises(EPError):
            application.state.cv.execute(cv_run["id"], lender(auth), software_executor)
        assert list(store.artifacts.iterdir()) == []
        assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 409
    else:
        package = application.state.cv.execute(cv_run["id"], lender(auth), software_executor)
        original_verify(cv_run["id"], package)
        assert client.get(f"/v1/cv-runs/{cv_run['id']}/result", headers=headers).status_code == 200


def test_worker_busy_and_forged_source_rejected(client, application, cv_run, auth, headers):
    service = application.state.cv
    second = client.post(
        f"/v1/inspections/{cv_run['inspection_id']}/cv-runs", json={}, headers=headers
    ).json()
    service.store.claim(second["id"])
    with pytest.raises(EPError) as caught:
        service.store.claim(cv_run["id"])
    assert caught.value.code == "worker_busy"
    service.store.terminate(second["id"], "cancelled")

    def forge(payload, output, cancelled):
        package = software_executor(payload, output, cancelled)
        package.source_hashes[package.source_ids[0]] = "f" * 64
        return package

    with pytest.raises(EPError) as caught:
        service.execute(cv_run["id"], lender(auth), forge)
    assert caught.value.code == "stage_contract"
    assert not list(service.store.artifacts.iterdir())


def test_active_worker_lock_prevents_destructive_startup_recovery(
    client, application, cv_run, auth, monkeypatch, tmp_path
):
    from ep_engine.cv import concurrency

    monkeypatch.setattr(concurrency, "LOCK_PATH", tmp_path / "worker.lock")
    service = application.state.cv
    with concurrency.worker_guard():
        for operation in (
            service.store.initialize,
            lambda: service.execute(cv_run["id"], lender(auth), software_executor),
        ):
            with pytest.raises(EPError) as caught:
                operation()
            assert caught.value.code == "worker_busy"
    # Stale file remains, but the OS lock is released, so normal work can resume.
    assert service.get(cv_run["id"], lender(auth))[0].status == "queued"
    assert service.execute(cv_run["id"], lender(auth), software_executor).outcome == "inconclusive"
