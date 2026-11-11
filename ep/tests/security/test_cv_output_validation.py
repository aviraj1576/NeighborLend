import hashlib
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from ep_engine.core.exceptions import EPError
from ep_engine.cv.artifacts import ArtifactWriter
from ep_engine.cv.contracts import CVConfig, CVPackage
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.cv.store import CVStore, cleanup


def package_at(directory):
    inputs = [
        InputImage(uuid4(), stage, np.full((32, 32, 3), 128, np.uint8), "a" * 64, None)
        for stage in ("before", "after")
    ]
    package = CVPipeline(CVConfig()).run(uuid4(), inputs, directory)
    writer = ArtifactWriter(directory, package.source_ids)
    writer.save("object_mask", np.full((12, 16), 255, np.uint8), package.source_ids)
    package.artifacts = writer.records
    return package


def test_private_artifact_limits_and_citations(tmp_path):
    key = uuid4()
    writer = ArtifactWriter(tmp_path / "images", [key])
    image = np.zeros((16, 16), np.uint8)
    for sources in ([], [uuid4()]):
        with pytest.raises(EPError, match="citation"):
            writer.save("object_mask", image, sources)
    for invalid in (image.astype(float), np.zeros((2049, 2), np.uint8)):
        with pytest.raises(EPError):
            writer.save("object_mask", invalid, [key])
    writer.total = 32_000_000
    with pytest.raises(EPError):
        writer.save("object_mask", image, [key])
    assert list(writer.root.iterdir()) == []
    with pytest.raises(EPError):
        cleanup(tmp_path, tmp_path)
    with pytest.raises(EPError):
        cleanup(tmp_path, tmp_path.parent)


def test_reject_forged_package_citations_and_outcome(tmp_path):
    package = package_at(tmp_path / "output")
    valid = package.model_dump(mode="json")
    assert CVPackage.model_validate(valid).outcome == "inconclusive"
    mutations = [
        {"outcome": "comparable"},
        {"unmatched_ids": []},
        {"quality": []},
        {"segmentation": []},
        {"source_ids": [valid["source_ids"][0]] * 2},
        {"artifacts": [valid["artifacts"][0]] * 2},
        {"artifacts": [{**valid["artifacts"][0], "source_ids": [str(uuid4())]}]},
        {"source_hashes": {key: "not-a-digest" for key in valid["source_hashes"]}},
        {"source_dimensions": {}},
        {
            "segmentation": [
                {**valid["segmentation"][0], "status": "segmented"},
                valid["segmentation"][1],
            ]
        },
        {
            "candidates": [
                {
                    "id": str(uuid4()),
                    "before_id": valid["source_ids"][0],
                    "after_id": valid["source_ids"][1],
                    "before_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                    "after_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                    "area_pixels": 10,
                    "mean_difference": 0.5,
                    "inlier_ratio": 1,
                }
            ]
        },
    ]
    for mutation in mutations:
        with pytest.raises(ValidationError):
            CVPackage.model_validate({**valid, **mutation})


def test_artifact_must_be_real_png_with_matching_dimensions(tmp_path):
    store = CVStore(tmp_path / "cv")
    directory = store.work / "output"
    package = package_at(directory)
    store.verify_package_files(uuid4(), package, directory)
    row = package.artifacts[0]
    row.width += 1
    with pytest.raises(EPError):
        store.verify_package_files(uuid4(), package, directory)
    row.width -= 1
    data = b"not an image despite a matching receipt"
    (directory / f"{row.id}.png").write_bytes(data)
    row.byte_size, row.sha256 = len(data), hashlib.sha256(data).hexdigest()
    with pytest.raises(EPError):
        store.verify_package_files(uuid4(), package, directory)
