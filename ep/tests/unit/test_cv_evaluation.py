import hashlib
import json

import numpy as np
import pytest
from PIL import Image

from ep_engine.cv.evaluation import (
    binary_metrics,
    box_iou,
    evaluate_cases,
    mask_iou,
    read_mask,
    region_metrics,
    validate_manifest,
)


def test_metrics_handle_abstention_no_labels_and_localization():
    assert binary_metrics([None], [True])["status"] == "blocked_no_labels"
    result = binary_metrics([True, False, False, True], [True, True, False, None])
    assert result["precision"] == 0.5 and result["abstention_rate"] == 0.25
    assert box_iou([0, 0, 1, 1], [0.5, 0, 1, 1]) == 0.5
    assert region_metrics([[0, 0, 1, 1]], [[0, 0, 1, 1], [0, 0, 1, 1]])["fp"] == 1
    assert mask_iou(np.zeros((2, 2), bool), np.zeros((2, 2), bool)) is None
    assert mask_iou(np.ones((2, 2), bool), np.ones((2, 2), bool)) == 1
    with pytest.raises(ValueError):
        box_iou([1, 0, 0, 1], [0, 0, 1, 1])
    with pytest.raises(ValueError):
        mask_iou(np.ones((2, 3), bool), np.ones((2, 2), bool))


def test_manifest_hash_review_and_split_guards(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"deterministic manifest unit test, not physical evidence")
    case = {
        "case_id": "one",
        "object_instance_group": "object-1",
        "split": "development",
        "labels": None,
        "views": [{"path": "sample.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
    }
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(case))
    assert len(validate_manifest(path)) == 1
    second = {**case, "case_id": "two", "split": "test"}
    path.write_text(json.dumps(case) + "\n" + json.dumps(second))
    with pytest.raises(ValueError, match="split leakage"):
        validate_manifest(path)
    path.write_text(json.dumps({**case, "labels": {"comparable": True}}))
    with pytest.raises(ValueError, match="Unreviewed"):
        validate_manifest(path)
    image.write_bytes(b"modified")
    path.write_text(json.dumps(case))
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_manifest(path)


def test_label_aware_evaluator_and_binary_masks(tmp_path):
    image = tmp_path / "mask.png"
    Image.fromarray(np.full((8, 8), 255, np.uint8)).save(image)
    mask = {"path": "mask.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    # Mathematical fixtures only, not benchmark ground truth or accuracy claims.
    case = {
        "case_id": "metric-fixture",
        "annotation_status": "independently_reviewed",
        "labels": {
            "identity_consistent": True,
            "viewpoint_comparable": True,
            "change_present": False,
            "regions": {"after": []},
            "masks": {"before": mask},
        },
    }
    prediction = {
        "case_id": "metric-fixture",
        "identity_consistent": True,
        "viewpoint_comparable": True,
        "change_present": True,
        "regions": {"after": [[0, 0, 1, 1]]},
        "masks": {"before": mask},
    }
    report = evaluate_cases([case], [prediction], tmp_path)
    assert report["change_present"]["fp"] == 1
    assert report["localization"]["views"][0]["fp"] == 1
    assert report["segmentation"]["views"][0]["iou"] == 1
    assert (
        evaluate_cases([{**case, "labels": None}], [], tmp_path)["identity_consistent"]["status"]
        == "blocked_no_labels"
    )
    for predictions in (
        [prediction, prediction],
        [{**prediction, "case_id": "unknown"}],
        [{**prediction, "change_present": 1}],
    ):
        with pytest.raises(ValueError):
            evaluate_cases([case], predictions, tmp_path)
    with pytest.raises(ValueError):
        read_mask(tmp_path, {**mask, "sha256": "0" * 64})
    Image.fromarray(np.full((8, 8), 128, np.uint8)).save(image)
    with pytest.raises(ValueError, match="binary"):
        read_mask(tmp_path, {**mask, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()})
