import io
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ep_engine.assessment.providers import MockProvider, UnavailableProvider
from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.pipeline import CVPipeline
from ep_engine.cv.worker import load_inputs
from ep_engine.main import create_app


class ControlledModels:
    def segment(self, image, box):
        mask = np.zeros(image.shape[:2], bool)
        mask[20:-20, 20:-20] = True
        return mask

    def embedding(self, *args):
        return np.ones(384, np.float32)

    def close(self):
        pass

    def metrics(self):
        return {"device": "controlled_synthetic_adapter"}


def controlled_cv(payload, output, cancelled):
    return CVPipeline(CVConfig.model_validate(payload["config"]), ControlledModels()).run(
        UUID(payload["inspection_id"]), load_inputs(payload), output
    )


def fixture_reply(request):
    return {
        "observations": [
            {
                "candidate_id": row["id"],
                "status": "possible_visible_damage",
                "damage_type": "uncertain",
                "affected_region": "Synthetic patch",
                "evidence_ids": [row["before_id"], row["after_id"]],
                "artifact_ids": row["artifact_ids"],
                "explanation": "Mock interpretation of controlled pixels",
                "uncertainty": "No real physical-damage or identity claim",
            }
            for row in request.manifest["candidates"]
        ]
    }


@pytest.fixture
def cv_source(client, headers, upload, application, auth):
    before, after = [], []
    target = {"x1": 0.05, "y1": 0.05, "x2": 0.95, "y2": 0.95}
    for seed in (23, 41):
        image = np.random.default_rng(seed).integers(30, 210, (256, 256, 3), np.uint8)
        changed = image.copy()
        changed[90:120, 100:130] = 0
        for stage, array, ids in (("before", image, before), ("after", changed, after)):
            buffer = io.BytesIO()
            Image.fromarray(array).save(buffer, format="PNG")
            response = upload(
                stage=stage,
                data=buffer.getvalue(),
                token="test-borrower-token" if stage == "after" else None,
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])
    inspection = client.post(
        "/v1/inspections",
        json={"rental_id": "rental-1", "reference_ids": before, "return_ids": after},
        headers=headers,
    ).json()
    run = client.post(
        f"/v1/inspections/{inspection['id']}/cv-runs",
        headers=headers,
        json={"targets": {key: target for key in before + after}},
    ).json()
    package = application.state.cv.execute(
        run["id"], auth.authenticate("Bearer test-lender-token"), controlled_cv
    )
    assert package.outcome == "comparable" and len(package.candidates) == 2
    return run


def queue(client, headers, cv_source, **options):
    response = client.post(
        f"/v1/cv-runs/{cv_source['id']}/assessments", json=options, headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_four_phase_controlled_integration_cache_and_parent_state(
    client, application, cv_source, headers, auth
):
    provider = MockProvider(fixture_reply)
    service = application.state.assessments
    service.provider = provider
    job = queue(client, headers, cv_source)
    assert client.get(f"/v1/assessments/{job['id']}/result", headers=headers).status_code == 409
    report = service.execute(job["id"], auth.authenticate("Bearer test-lender-token"))
    assert report.status == "human_review_required" and report.mocked and len(report.findings) == 2
    assert report.stage_statuses == ["damage_verification", "evidence_fusion", "report_generation"]
    assert queue(client, headers, cv_source)["id"] == job["id"] and provider.calls == 1
    result = client.get(f"/v1/assessments/{job['id']}/result", headers=headers)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert str(service.store.db.path) not in result.text and "base64" not in result.text
    assert (
        client.get(f"/v1/inspections/{cv_source['inspection_id']}", headers=headers).json()[
            "status"
        ]
        == "created"
    )
    (
        Path(__file__).resolve().parents[2] / ".test-artifacts/phase34-mock-integration.json"
    ).write_text(
        json.dumps(
            {
                "controlled_source_images": 4,
                "provider_calls": provider.calls,
                "report": report.model_dump(mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("allow_external", [False, True])
def test_gemini_mock_http_queue_execution_persistence_and_opt_in(
    client, application, cv_source, headers, auth, monkeypatch, allow_external
):
    import httpx

    from ep_engine.assessment.providers import GeminiProvider, PreparedRequest, ProviderSettings
    from ep_engine.assessment.service import provider_key

    monkeypatch.setenv("EP_VLM_PROVIDER", "gemini")
    monkeypatch.setenv("EP_VLM_MODEL", "gemini-test-model")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-google-key")
    monkeypatch.setenv("EP_VLM_ALLOW_EXTERNAL", "1")
    calls = []

    def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        manifest = json.loads(body["contents"][0]["parts"][0]["text"])
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": json.dumps(fixture_reply(PreparedRequest(manifest, [])))}
                            ]
                        },
                    }
                ]
            },
        )

    settings = ProviderSettings.from_environment()
    provider = GeminiProvider(settings, httpx.MockTransport(handle))
    rotated = GeminiProvider(
        ProviderSettings(**(settings.model_dump() | {"api_key": "rotated-key"}))
    )
    assert provider_key(provider) == provider_key(rotated)
    service = application.state.assessments
    service.provider = provider
    job = queue(client, headers, cv_source, allow_external=allow_external)
    report = service.execute(job["id"], auth.authenticate("Bearer test-lender-token"))
    result = client.get(f"/v1/assessments/{job['id']}/result", headers=headers)
    assert result.status_code == 200 and result.json() == report.model_dump(mode="json")
    assert len(calls) == int(allow_external)
    if allow_external:
        assert report.provider == "gemini" and len(report.findings) == 2
        assert report.status == "human_review_required" and not report.mocked
    else:
        assert report.error_code == "external_processing_not_permitted" and not report.findings
    assert "synthetic-google-key" not in result.text and "inlineData" not in result.text
    assert report.payment_action == "none" and not report.physical_identity_verified
    assert queue(client, headers, cv_source, allow_external=allow_external)["id"] == job["id"]
    assert len(calls) == int(allow_external)


def test_assessment_authorization_and_cancel(client, application, cv_source, headers, auth):
    application.state.assessments.provider = MockProvider()
    job = queue(client, headers, cv_source)
    for route in (f"/v1/assessments/{job['id']}", f"/v1/assessments/{job['id']}/result"):
        assert client.get(route).status_code == 401
        assert (
            client.get(route, headers={"Authorization": "Bearer test-other-token"}).status_code
            == 403
        )
    assert (
        client.post(
            f"/v1/assessments/{job['id']}/cancel",
            headers={"Authorization": "Bearer test-borrower-token"},
        ).status_code
        == 403
    )
    assert (
        client.post(f"/v1/assessments/{job['id']}/cancel", headers=headers).json()["status"]
        == "cancelled"
    )
    with pytest.raises(EPError):
        application.state.assessments.execute(
            job["id"], auth.authenticate("Bearer test-lender-token")
        )


def test_provider_unavailable_persists_honest_inconclusive_report(
    client, application, cv_source, headers, auth
):
    service = application.state.assessments
    service.provider = UnavailableProvider()
    job = queue(client, headers, cv_source)
    report = service.execute(job["id"], auth.authenticate("Bearer test-lender-token"))
    assert report.status == "inconclusive" and report.error_code == "provider_unavailable"
    assert not report.findings and report.metrics.attempts == 0


def test_restart_persistence_and_interrupted_job(
    client, application, cv_source, headers, auth, settings
):
    service = application.state.assessments
    service.provider = MockProvider(fixture_reply)
    first = queue(client, headers, cv_source)
    service.execute(first["id"], auth.authenticate("Bearer test-lender-token"))
    second = queue(client, headers, cv_source, max_candidates=1)
    service.store.claim(second["id"])
    with TestClient(create_app(settings, authorization=auth)) as restarted:
        assert (
            restarted.get(f"/v1/assessments/{first['id']}/result", headers=headers).status_code
            == 200
        )
        record = restarted.get(f"/v1/assessments/{second['id']}", headers=headers).json()
        assert record["status"] == "failed" and record["error_code"] == "worker_interrupted"


def test_source_integrity_rechecked_before_worker(client, application, cv_source, headers, auth):
    service = application.state.assessments
    service.provider = MockProvider(fixture_reply)
    job = queue(client, headers, cv_source)
    record = application.state.repository.get_inspection(cv_source["inspection_id"])
    application.state.storage.path(str(record.reference_ids[0]), "original").write_bytes(
        b"corrupt fixture"
    )
    with pytest.raises(EPError) as caught:
        service.execute(job["id"], auth.authenticate("Bearer test-lender-token"))
    assert caught.value.code == "integrity_failure" and service.provider.calls == 0


def test_queue_limit_configuration_change_and_request_validation(
    client, application, cv_source, headers, auth
):
    service = application.state.assessments
    service.provider = MockProvider(fixture_reply)
    first = queue(client, headers, cv_source)
    for count in (1, 2, 3):
        queue(client, headers, cv_source, max_candidates=count)
    route = f"/v1/cv-runs/{cv_source['id']}/assessments"
    assert client.post(route, json={"max_candidates": 8}, headers=headers).status_code == 429
    assert (
        client.post(
            route, json={"arbitrary_url": "https://example.invalid"}, headers=headers
        ).status_code
        == 422
    )
    service.provider = UnavailableProvider()
    with pytest.raises(EPError) as caught:
        service.execute(first["id"], auth.authenticate("Bearer test-lender-token"))
    assert caught.value.code == "provider_configuration_changed"
    assert (
        service.get(first["id"], auth.authenticate("Bearer test-lender-token"))[0].status
        == "failed"
    )


def test_cancellation_during_provider_execution_never_commits(
    client, application, cv_source, headers, auth
):
    service = application.state.assessments
    grant = auth.authenticate("Bearer test-lender-token")
    pending = {}

    def cancel(request):
        service.cancel(pending["id"], grant)
        return fixture_reply(request)

    service.provider = MockProvider(cancel)
    pending.update(queue(client, headers, cv_source))
    with pytest.raises(EPError):
        service.execute(pending["id"], grant)
    assert service.get(pending["id"], grant)[0].status == "cancelled"
    assert client.get(f"/v1/assessments/{pending['id']}/result", headers=headers).status_code == 409


def test_persisted_forged_citations_are_rejected(client, application, cv_source, headers, auth):
    from uuid import uuid4

    service = application.state.assessments
    service.provider = MockProvider(fixture_reply)
    grant = auth.authenticate("Bearer test-lender-token")
    job = queue(client, headers, cv_source)
    report = service.execute(job["id"], grant)
    report.findings[0].evidence_ids = [uuid4(), uuid4()]
    with service.store.db.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET report=? WHERE id=?", (report.model_dump_json(), job["id"])
        )
    assert client.get(f"/v1/assessments/{job['id']}/result", headers=headers).status_code == 409


def test_assessment_commit_failure_rolls_back_result(
    client, application, cv_source, headers, auth, monkeypatch
):
    import sqlite3
    from contextlib import contextmanager

    service = application.state.assessments
    service.provider = MockProvider(fixture_reply)
    job = queue(client, headers, cv_source)
    finish = service.store.finish

    def fail_commit(key, report):
        transaction = service.store.db.transaction

        @contextmanager
        def failure():
            with transaction() as connection:
                yield connection
                raise sqlite3.OperationalError("Controlled commit failure")

        with monkeypatch.context() as context:
            context.setattr(service.store.db, "transaction", failure)
            return finish(key, report)

    monkeypatch.setattr(service.store, "finish", fail_commit)
    with pytest.raises(sqlite3.Error):
        service.execute(job["id"], auth.authenticate("Bearer test-lender-token"))
    record, _, report = service.store.get(job["id"])
    assert record.status == "failed" and report is None
