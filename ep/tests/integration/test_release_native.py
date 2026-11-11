"""Release acceptance: real native workers and CV, mock only the Gemini HTTP boundary."""

import base64
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ep_engine.assessment.contracts import AssessmentReport, digest_package
from ep_engine.cv.contracts import CVPackage
from ep_engine.main import create_app
from ep_engine.pipeline.interfaces import STAGE_ORDER

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.real_inference
@pytest.mark.controlled_inference
@pytest.mark.parametrize("device,changed,views", [("cuda", True, 2), ("cpu", False, 1)])
def test_native_api_to_private_review_report(monkeypatch, device, changed, views):
    if os.environ.get("EP_RUN_CONTROLLED_CV") != "1":
        pytest.skip("Explicit synthetic native release acceptance required")
    from scripts import run_assessment_worker, run_cv_worker

    started = time.perf_counter()
    directory = ROOT / ".test-artifacts" / "phase5-release" / f"{device}-{uuid4()}"
    directory.mkdir(parents=True)
    tokens = {
        role: f"phase5-{role}-synthetic-credential-only" for role in ("lender", "borrower", "other")
    }
    grants = directory / "local-grants.json"
    grants.write_text(
        json.dumps(
            [
                {
                    "token": tokens[role],
                    "grant": {
                        "subject": role,
                        "rentals": {
                            "rental-2" if role == "other" else "rental-1": (
                                "lender" if role == "other" else role
                            )
                        },
                    },
                }
                for role in tokens
            ]
        ),
        encoding="utf-8",
    )
    for name, value in {
        "EP_DATA_DIR": str(directory / "private"),
        "EP_LOCAL_GRANTS_FILE": str(grants),
        "EP_WORKER_TOKEN": tokens["lender"],
        "EP_VLM_PROVIDER": "gemini",
        "EP_VLM_MODEL": "gemini-synthetic-release-test",
        "GEMINI_API_KEY": "synthetic-key",
        "EP_VLM_ALLOW_EXTERNAL": "1",
    }.items():
        monkeypatch.setenv(name, value)
    headers = {"Authorization": "Bearer " + tokens["lender"]}
    foreign = {"Authorization": "Bearer " + tokens["other"]}
    source_hashes, source_bytes, stages, wire_manifests = {}, {}, {"before": [], "after": []}, []
    target = {"x1": 0.16, "y1": 0.16, "x2": 0.84, "y2": 0.84}
    timings = {}
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        for view in range(views):
            before = np.full((256, 256, 3), 230, np.uint8)
            before[48:208, 48:208] = np.random.default_rng(42 + view).integers(
                30, 170, (160, 160, 3), np.uint8
            )
            after = before.copy()
            if changed:
                after[105:135, 110:140] = 0
            for stage, pixels in (("before", before), ("after", after)):
                buffer = io.BytesIO()
                Image.fromarray(pixels).save(buffer, format="PNG")
                content = buffer.getvalue()
                response = client.post(
                    "/v1/evidence",
                    content=content,
                    params={
                        "rental_id": "rental-1",
                        "stage": stage,
                        "viewpoint": f"generated-{view}",
                    },
                    headers={
                        "Authorization": "Bearer "
                        + tokens["lender" if stage == "before" else "borrower"],
                        "Content-Type": "image/png",
                    },
                )
                assert response.status_code == 201, response.text
                evidence = response.json()
                key = evidence["id"]
                assert evidence["sha256"] == hashlib.sha256(content).hexdigest()
                assert evidence["width"] == evidence["height"] == 256
                assert evidence["stage"] == stage and evidence["metadata_verified"] is False
                stages[stage].append(key)
                source_hashes[key], source_bytes[key] = evidence["sha256"], content
        response = client.post(
            "/v1/inspections",
            json={
                "rental_id": "rental-1",
                "reference_ids": stages["before"],
                "return_ids": stages["after"],
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        inspection_id = response.json()["id"]
        response = client.post(
            f"/v1/inspections/{inspection_id}/cv-runs",
            json={
                "targets": {key: target for key in source_hashes},
                "config": {"device": device, "max_side": 256},
            },
            headers=headers,
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        assert client.get(f"/v1/cv-runs/{run_id}/result", headers=headers).status_code == 409
        mark = time.perf_counter()
        with monkeypatch.context() as context:
            context.setattr(sys, "argv", ["run_cv_worker.py", run_id])
            run_cv_worker.main()  # Default ProcessRunner: actual hidden native child, no CV mocks.
        timings["cv_worker_seconds"] = time.perf_counter() - mark
        assert client.get(f"/v1/cv-runs/{run_id}", headers=headers).json()["status"] == "completed"
        response = client.get(f"/v1/cv-runs/{run_id}/result", headers=headers)
        assert response.status_code == 200, response.text
        package = CVPackage.model_validate(response.json())
        assert package.schema_version == "2.0" and package.models["adapter"] == "NativeModels"
        assert package.metrics["device"] == device and package.outcome == "comparable"
        assert set(package.metrics["stage_seconds"]) == set(STAGE_ORDER[:6])
        assert {str(k): v for k, v in package.source_hashes.items()} == source_hashes
        assert all(size == (256, 256) for size in package.source_dimensions.values())
        assert package.processing_dimensions == package.source_dimensions
        assert all(row.status == "segmented" and row.box for row in package.segmentation)
        assert len([p for p in package.pairs if p.status == "comparable"]) == views
        artifacts = {str(row.id): row for row in package.artifacts}
        for artifact in package.artifacts:
            route = f"/v1/cv-runs/{run_id}/artifacts/{artifact.id}"
            response = client.get(route, headers=headers)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert hashlib.sha256(response.content).hexdigest() == artifact.sha256
            with Image.open(io.BytesIO(response.content)) as image:
                assert image.size == (artifact.width, artifact.height) and image.format == "PNG"
            assert client.get(route, headers=foreign).status_code == 403
        for candidate in package.candidates:
            assert str(candidate.before_id) in stages["before"]
            assert str(candidate.after_id) in stages["after"]
            pair = next(
                p
                for p in package.pairs
                if (p.before_id == candidate.before_id and p.after_id == candidate.after_id)
            )
            assert pair.alignment_status == "aligned" and pair.local_matching_evaluated
            assert pair.inliers >= package.thresholds.min_inliers and pair.homography
            for key in candidate.artifact_ids:
                artifact = artifacts[str(key)]
                box = (
                    candidate.before_box if artifact.kind == "before_crop" else candidate.after_box
                )
                source = (
                    candidate.before_id if artifact.kind == "before_crop" else candidate.after_id
                )
                assert artifact.source_ids == [source]
                assert abs(artifact.width - (box.x2 - box.x1) * 256) <= 2
                assert abs(artifact.height - (box.y2 - box.y1) * 256) <= 2

        def mock_google(request):
            assert request.url.host == "generativelanguage.googleapis.com"
            assert request.headers["x-goog-api-key"] == "synthetic-key"
            body = json.loads(request.content)
            parts = body["contents"][0]["parts"]
            manifest = json.loads(parts[0]["text"])
            assert manifest["cv_digest"] == digest_package(package)
            assert manifest["source_hashes"] == source_hashes
            assert set(manifest["allowed_artifact_ids"]) == {
                json.loads(parts[i]["text"])["artifact_id"] for i in range(1, len(parts), 2)
            }
            for i in range(1, len(parts), 2):
                metadata = json.loads(parts[i]["text"])
                pixels = base64.b64decode(parts[i + 1]["inlineData"]["data"], validate=True)
                artifact = artifacts[metadata["artifact_id"]]
                assert hashlib.sha256(pixels).hexdigest() == metadata["sha256"]
                assert metadata["source_artifact_sha256"] == artifact.sha256
                assert metadata["source_ids"] == list(map(str, artifact.source_ids))
                assert metadata["frame_evidence_id"] in metadata["source_ids"]
                with Image.open(io.BytesIO(pixels)) as image:
                    assert image.size == (metadata["width"], metadata["height"])
                if metadata["kind"] in ("before_crop", "after_crop"):
                    candidate = next(
                        c
                        for c in manifest["candidates"]
                        if metadata["artifact_id"] in c["artifact_ids"]
                    )
                    assert (
                        metadata["source_box"]
                        == candidate[
                            "before_box" if metadata["kind"] == "before_crop" else "after_box"
                        ]
                    )
            wire_manifests.append(manifest)  # No keys or image bytes are recorded here.
            observations = [
                {
                    "candidate_id": c["id"],
                    "status": "possible_visible_damage",
                    "damage_type": "uncertain",
                    "affected_region": "Synthetic edited patch",
                    "evidence_ids": [c["before_id"], c["after_id"]],
                    "artifact_ids": c["artifact_ids"],
                    "explanation": "Mock Gemini interpretation only",
                    "uncertainty": "Synthetic pixels; no physical-damage or identity proof",
                }
                for c in manifest["candidates"]
            ]
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [{"text": json.dumps({"observations": observations})}]
                            },
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 123, "candidatesTokenCount": 45},
                },
            )

        real_client = httpx.Client

        def mocked_client(*args, **kwargs):
            return real_client(*args, **(kwargs | {"transport": httpx.MockTransport(mock_google)}))

        monkeypatch.setattr(httpx, "Client", mocked_client)
        route = f"/v1/cv-runs/{run_id}/assessments"
        options = {"allow_external": True}
        response = client.post(route, json=options, headers=headers)
        assert response.status_code == 202, response.text
        job = response.json()
        mark = time.perf_counter()
        with monkeypatch.context() as context:
            context.setattr(sys, "argv", ["run_assessment_worker.py", job["id"]])
            run_assessment_worker.main()  # Same operator entrypoint; only HTTP is replaced.
        timings["assessment_worker_seconds"] = time.perf_counter() - mark
        review_route = f"/v1/assessments/{job['id']}/result"
        response = client.get(review_route, headers=headers)
        assert response.status_code == 200, response.text
        report = AssessmentReport.model_validate(response.json())
        assert report.schema_version == "4.0" and report.cv_digest == digest_package(package)
        assert (
            report.source_hashes == package.source_hashes
            and str(report.inspection_id) == inspection_id
        )
        assert report.physical_identity_verified is False and report.payment_action == "none"
        assert report.human_review_required and report.error_code is None
        assert len(wire_manifests) == int(changed)
        if changed:
            assert len(package.candidates) == views and len(report.findings) == views
            assert report.status == "human_review_required" and report.provider == "gemini"
            assert report.stage_statuses == list(STAGE_ORDER[6:])
            assert {f.candidate_id for f in report.findings} == {c.id for c in package.candidates}
        else:
            assert not package.candidates and not report.findings
            assert report.status == "no_visible_change" and report.metrics.attempts == 0
        assert client.post(route, json=options, headers=headers).json()["id"] == job["id"]
        assert len(wire_manifests) == int(
            changed
        )  # Equivalent completed request never sends again.
        for path in (
            review_route,
            f"/v1/cv-runs/{run_id}/result",
            f"/v1/evidence/{stages['before'][0]}/content",
            f"/v1/inspections/{inspection_id}",
        ):
            assert client.get(path, headers=foreign).status_code == 403
            assert client.get(path).status_code == 401
        assert (
            client.get(f"/v1/inspections/{inspection_id}", headers=headers).json()["status"]
            == "created"
        )
        for key, content in source_bytes.items():
            assert client.get(f"/v1/evidence/{key}/content", headers=headers).content == content
    # Re-open the actual databases/app; no in-memory report is supplied to retrieval.
    with TestClient(create_app(), raise_server_exceptions=False) as restarted:
        persisted = restarted.get(review_route, headers=headers)
        assert persisted.status_code == 200 and persisted.json() == report.model_dump(mode="json")
        assert (
            restarted.get(f"/v1/assessments/{job['id']}", headers=headers).json()["status"]
            == "completed"
        )
    timings["total_seconds"] = time.perf_counter() - started
    summary = {
        "test": "test_native_api_to_private_review_report",
        "device": device,
        "changed": changed,
        "views": views,
        "mocked_http_only": True,
        "provider_calls": len(wire_manifests),
        "case_directory": str(directory.relative_to(ROOT)),
        "timings": timings,
        "inspection_id": inspection_id,
        "cv_run_id": run_id,
        "assessment_id": job["id"],
        "cv_metrics": package.metrics,
        "cv_outcome": package.outcome,
        "candidates": len(package.candidates),
        "artifact_count": len(package.artifacts),
        "assessment": report.model_dump(mode="json"),
    }
    for name, data in (
        ("cv-package.json", package.model_dump(mode="json")),
        ("gemini-manifests.json", wire_manifests),
        ("results.json", summary),
    ):
        (directory / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    (directory.parent / f"latest-{device}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
