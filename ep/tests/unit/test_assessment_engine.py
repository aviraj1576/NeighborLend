from uuid import uuid4

import numpy as np
import pytest

from ep_engine.assessment.contracts import AssessmentOptions
from ep_engine.assessment.engine import assess
from ep_engine.assessment.providers import MockProvider
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


class Models:
    def segment(self, rgb, box):
        mask = np.zeros(rgb.shape[:2], bool)
        mask[20:-20, 20:-20] = True
        return mask

    def embedding(self, *args):
        return np.ones(384, np.float32)

    def close(self):
        pass

    def metrics(self):
        return {"device": "deterministic_fixture"}


@pytest.fixture
def controlled_package(tmp_path):
    rgb = np.random.default_rng(23).integers(30, 210, (256, 256, 3), np.uint8)
    after = rgb.copy()
    after[90:120, 100:130] = 0
    target = Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95)
    inputs = [
        InputImage(uuid4(), stage, image, char * 64, target)
        for stage, image, char in (("before", rgb, "a"), ("after", after, "b"))
    ]
    directory = tmp_path / "artifacts"
    package = CVPipeline(CVConfig(), Models()).run(uuid4(), inputs, directory)
    return package, directory


def mock_reply(request):
    candidate = request.manifest["candidates"][0]
    return {
        "observations": [
            {
                "candidate_id": candidate["id"],
                "status": "possible_visible_damage",
                "damage_type": "uncertain",
                "affected_region": "Controlled changed patch",
                "evidence_ids": [candidate["before_id"], candidate["after_id"]],
                "artifact_ids": candidate["artifact_ids"],
                "explanation": "Mock fixture observation only",
                "uncertainty": "Synthetic test; no physical damage established",
            }
        ]
    }


def test_gated_assessment_is_cited_private_and_explicitly_mocked(controlled_package):
    package, directory = controlled_package
    provider = MockProvider(mock_reply)
    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        provider,
    )
    assert report.status == "human_review_required" and report.mocked is True
    assert provider.calls == 1 and report.metrics.attempts == 1
    assert report.payment_action == "none" and report.physical_identity_verified is False
    assert str(directory) not in report.model_dump_json()


def test_inconclusive_cv_never_calls_vlm(controlled_package):
    package, directory = controlled_package
    for pair in package.pairs:
        pair.status = "inconclusive"
    package.candidates = []
    package.outcome = "inconclusive"
    package.unmatched_ids = package.source_ids
    provider = MockProvider(lambda request: pytest.fail("Unsupported provider call"))
    report = assess(
        uuid4(),
        package,
        lambda key: pytest.fail("Unnecessary image read"),
        AssessmentOptions(),
        provider,
    )
    assert report.status == "inconclusive" and report.provider == "not_called"


@pytest.mark.parametrize(
    "change",
    [
        "unknown_evidence",
        "unknown_artifact",
        "invented_candidate",
        "bad_json",
        "missing_field",
        "cost_claim",
    ],
)
def test_unsupported_provider_output_is_rejected(controlled_package, change):
    package, directory = controlled_package

    def response(request):
        data = mock_reply(request)
        observation = data["observations"][0]
        if change == "unknown_evidence":
            observation["evidence_ids"] = [str(uuid4())]
        elif change == "unknown_artifact":
            observation["artifact_ids"] = [str(uuid4())]
        elif change == "invented_candidate":
            observation["candidate_id"] = str(uuid4())
        elif change == "bad_json":
            return "not JSON"
        elif change == "missing_field":
            del observation["uncertainty"]
        else:
            observation["deposit_deduction"] = 500
        return data

    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        MockProvider(response),
    )
    assert report.status == "inconclusive" and not report.findings
    assert report.error_code in {"provider_schema", "unsupported_claim"}


@pytest.mark.parametrize("error", [TimeoutError, RuntimeError])
def test_provider_exceptions_cannot_create_findings(controlled_package, error):
    package, directory = controlled_package

    def fail(request):
        raise error("Sensitive exception content is never a public explanation")

    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        MockProvider(fail),
    )
    assert not report.findings and report.status == "inconclusive"
    assert report.error_code == (
        "provider_timeout" if error is TimeoutError else "provider_failure"
    )
    assert report.metrics.attempts == 1 and "Sensitive" not in report.model_dump_json()


@pytest.mark.parametrize(
    "reason", ["weak_inliers", "invalid_transform", "missing_overlap", "poor_quality"]
)
def test_failed_upstream_support_never_reads_images_or_calls_provider(controlled_package, reason):
    package, _ = controlled_package
    if reason == "weak_inliers":
        package.pairs[0].inliers = 1
    elif reason == "invalid_transform":
        package.pairs[0].homography = [[0.0, 0, 0]] * 3
    elif reason == "missing_overlap":
        package.pairs[0].overlap_id = uuid4()
    else:
        package.quality[0].status = "needs_recapture"
    provider = MockProvider(lambda request: pytest.fail("Unsupported provider call"))
    report = assess(
        uuid4(),
        package,
        lambda key: pytest.fail("Unsupported image read"),
        AssessmentOptions(),
        provider,
    )
    assert report.status == "inconclusive" and provider.calls == 0


def test_incomplete_context_and_corrupt_artifact_fail_safely(controlled_package):
    package, directory = controlled_package
    provider = MockProvider(mock_reply)
    report = assess(uuid4(), package, lambda key: b"corrupt", AssessmentOptions(), provider)
    assert report.error_code == "artifact_integrity" and provider.calls == 0
    package.artifacts = [row for row in package.artifacts if row.kind != "object_crop"]
    report = assess(
        uuid4(),
        package,
        lambda key: pytest.fail("Missing context must block reads"),
        AssessmentOptions(),
        provider,
    )
    assert report.error_code == "insufficient_evidence" and provider.calls == 0


@pytest.mark.parametrize("kind", ["json_http", "gemini"])
def test_mock_uncertainty_and_external_opt_in_are_explicit(controlled_package, kind):
    package, directory = controlled_package
    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        MockProvider(),
    )
    assert report.status == "inconclusive" and report.mocked
    assert all(row.status == "insufficient_evidence" for row in report.findings)
    external = MockProvider(lambda request: pytest.fail("External request not permitted"))
    external.kind = kind
    report = assess(
        uuid4(),
        package,
        lambda key: pytest.fail("No image preparation without consent"),
        AssessmentOptions(),
        external,
    )
    assert report.error_code == "external_processing_not_permitted" and external.calls == 0


def test_crop_roles_and_resource_budgets_are_enforced(controlled_package):
    from pydantic import ValidationError

    package, directory = controlled_package
    before_crop = next(row for row in package.artifacts if row.kind == "before_crop")
    before_crop.source_ids = [package.pairs[0].after_id]
    provider = MockProvider(lambda request: pytest.fail("Reversed crop citation"))
    report = assess(
        uuid4(),
        package,
        lambda key: pytest.fail("Reversed crop read"),
        AssessmentOptions(),
        provider,
    )
    assert report.error_code == "insufficient_evidence" and provider.calls == 0
    for options in ({"max_candidates": 9}, {"max_pairs": 5}, {"image_side": 769}):
        with pytest.raises(ValidationError):
            AssessmentOptions(**options)


@pytest.mark.parametrize("response_mode", ["valid", "unknown_artifact", "bad_json", "refused"])
def test_gemini_wire_reply_passes_existing_schema_and_citation_gate(
    controlled_package, response_mode
):
    import json

    import httpx

    from ep_engine.assessment.providers import GeminiProvider, PreparedRequest, ProviderSettings

    package, directory = controlled_package
    calls = []

    def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        manifest = json.loads(body["contents"][0]["parts"][0]["text"])
        response = mock_reply(PreparedRequest(manifest, []))
        if response_mode == "unknown_artifact":
            response["observations"][0]["artifact_ids"][0] = str(uuid4())
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "SAFETY" if response_mode == "refused" else "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "not-json"
                                        if response_mode == "bad_json"
                                        else json.dumps(response)
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    provider = GeminiProvider(
        ProviderSettings(
            provider="gemini", model="gemini-test-model", api_key="fixture", permit_external=True
        ),
        httpx.MockTransport(handle),
    )
    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(allow_external=True),
        provider,
    )
    assert len(calls) == 1 and report.provider == "gemini"
    assert report.metrics.images_sent > 0 and report.metrics.attempts == 1
    assert report.payment_action == "none" and report.human_review_required
    assert not report.physical_identity_verified
    if response_mode == "valid":
        assert report.status == "human_review_required" and report.error_code is None
        assert report.findings[0].candidate_id == package.candidates[0].id
        assert set(report.findings[0].evidence_ids) == set(package.source_ids)
    else:
        assert report.status == "inconclusive" and not report.findings
        assert (
            report.error_code
            == {
                "unknown_artifact": "unsupported_claim",
                "bad_json": "provider_schema",
                "refused": "provider_rejected",
            }[response_mode]
        )


def test_request_preserves_crop_mapping_and_selected_source_scope(controlled_package):
    package, directory = controlled_package

    def inspect(request):
        manifest = request.manifest
        assert set(manifest["source_hashes"]) == {str(key) for key in package.source_ids}
        assert all(row["box"] for row in manifest["segmentation"])
        assert {row["artifact_id"] for row in request.images} == set(
            manifest["allowed_artifact_ids"]
        )
        assert len(request.images) == len({row["artifact_id"] for row in request.images})
        assert all(row["source_box"] and row["frame_evidence_id"] for row in request.images)
        return mock_reply(request)

    result = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        MockProvider(inspect),
    )
    assert result.status == "human_review_required"


@pytest.mark.parametrize("conflicting", [False, True])
def test_repeated_region_observations_are_not_independent_confirmations(
    controlled_package, conflicting
):
    package, directory = controlled_package
    repeated = package.candidates[0].model_copy(deep=True, update={"id": uuid4()})
    package.candidates.append(repeated)

    def reply(request):
        data = mock_reply(request)
        observation = dict(data["observations"][0])
        observation["candidate_id"] = str(repeated.id)
        if conflicting:
            observation["status"] = "no_visible_change"
        data["observations"].append(observation)
        return data

    report = assess(
        uuid4(),
        package,
        lambda key: (directory / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        MockProvider(reply),
    )
    assert len(report.findings) == 2  # Retain contradictory observations for human review.
    assert any("not independent confirmations" in row.lower() for row in report.limitations)
    assert report.status == ("inconclusive" if conflicting else "human_review_required")
    if conflicting:
        assert any("conflict" in row.lower() for row in report.limitations)
    assert report.payment_action == "none"


@pytest.mark.parametrize("field", ["pairs", "candidates"])
def test_duplicate_cv_records_cannot_inflate_observation_counts(controlled_package, field):
    from pydantic import ValidationError

    from ep_engine.cv.contracts import CVPackage

    package, _ = controlled_package
    rows = getattr(package, field)
    rows.append(rows[0].model_copy(deep=True))
    with pytest.raises(ValidationError, match="Duplicate"):
        CVPackage.model_validate(package.model_dump())
