import hashlib
import json
from uuid import uuid4

import numpy as np

from ep_engine.assessment.contracts import digest_package
from ep_engine.cv.contracts import CVConfig, CVPackage
from ep_engine.cv.pipeline import CVPipeline, InputImage


def test_archived_assessment_digest_survives_additive_cv_fields(tmp_path):
    inputs = [
        InputImage(uuid4(), stage, np.full((128, 128, 3), 128, np.uint8), "a" * 64, None)
        for stage in ("before", "after")
    ]
    package = CVPipeline(CVConfig()).run(uuid4(), inputs, tmp_path / "archive")
    legacy = package.model_dump(mode="json")
    legacy["models"].pop("algorithm_revision")
    legacy["models"].pop("embedding_preprocessing")
    legacy.pop("boundary_changes")
    for q in legacy["quality"]:
        q.pop("recommendations")
    for s in legacy["segmentation"]:
        s.pop("target_support")
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    loaded = CVPackage.model_validate(legacy)
    assert digest_package(loaded) == expected
    loaded.quality[0].recommendations.append("New evidence must affect the digest")
    assert digest_package(loaded) != expected
