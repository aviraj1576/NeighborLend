import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ep_engine.config import EP_ROOT


def validate_manifest(path: Path):
    path = path.resolve()
    if not path.is_relative_to(EP_ROOT):
        raise ValueError("Benchmark manifests must remain inside EP")
    text = path.read_text("utf-8")
    cases = (
        [json.loads(line) for line in text.splitlines() if line.strip()]
        if path.suffix == ".jsonl"
        else json.loads(text)["cases"]
    )
    groups, hashes, ids = {}, {}, set()
    for case in cases:
        if case["case_id"] in ids or not case["object_instance_group"]:
            raise ValueError("Duplicate case or missing object group")
        ids.add(case["case_id"])
        split = case["split"]
        if split not in {"development", "calibration", "test", "smoke"}:
            raise ValueError("Unknown evaluation split")
        group = case["object_instance_group"]
        if group in groups and groups[group] != split:
            raise ValueError("Object-level split leakage")
        groups[group] = split
        if (
            case.get("labels") is not None
            and case.get("annotation_status") != "independently_reviewed"
        ):
            raise ValueError("Unreviewed labels cannot be ground truth")
        for view in case["views"]:
            image = (path.parent / view["path"]).resolve()
            if not image.is_relative_to(path.parent) or image.is_symlink():
                raise ValueError("Unsafe benchmark image path")
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            if digest != view["sha256"]:
                raise ValueError("Benchmark image hash mismatch")
            if digest in hashes and hashes[digest] != split:
                raise ValueError("Duplicate-image split leakage")
            hashes[digest] = split
    return cases


def read_mask(base, specification):
    path = (base / specification["path"]).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_relative_to(EP_ROOT):
        raise ValueError("Unsafe evaluation mask path")
    data = path.read_bytes()
    if len(data) > 20_000_000 or hashlib.sha256(data).hexdigest() != specification["sha256"]:
        raise ValueError("Evaluation mask hash/size mismatch")
    with Image.open(path, formats=("PNG",)) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError("Evaluation mask pixel budget exceeded")
        values = np.asarray(image.convert("L"))
        if not np.isin(values, (0, 255)).all():
            raise ValueError("Evaluation masks must be binary 0/255")
        return values == 255


def evaluate_cases(cases, predictions, base):
    """Offline label-aware evaluator. Predictions cannot populate missing ground truth."""
    ids = {case["case_id"] for case in cases}
    if len({row["case_id"] for row in predictions}) != len(predictions):
        raise ValueError("Duplicate predictions")
    if any(row["case_id"] not in ids for row in predictions):
        raise ValueError("Prediction cites unknown case")
    by_id = {row["case_id"]: row for row in predictions}
    report = {"cases": len(cases), "missing_predictions": len(ids - set(by_id))}
    for task in ("identity_consistent", "viewpoint_comparable", "change_present"):
        truth, estimated = [], []
        for case in cases:
            labels = case.get("labels") or {}
            if labels and case.get("annotation_status") != "independently_reviewed":
                raise ValueError("Unreviewed evaluation labels")
            label, prediction = labels.get(task), by_id.get(case["case_id"], {}).get(task)
            if any(value is not None and type(value) is not bool for value in (label, prediction)):
                raise ValueError("Binary evaluation values must be bool or null")
            truth.append(label)
            estimated.append(prediction)
        report[task] = binary_metrics(truth, estimated)
    localization, segmentation = [], []
    for case in cases:
        labels = case.get("labels") or {}
        prediction = by_id.get(case["case_id"], {})
        for view, boxes in labels.get("regions", {}).items():
            proposals = prediction.get("regions", {}).get(view)
            if proposals is not None:
                localization.append(
                    {
                        "case_id": case["case_id"],
                        "view": view,
                        **region_metrics(boxes, proposals),
                    }
                )
        for view, mask in labels.get("masks", {}).items():
            predicted = prediction.get("masks", {}).get(view)
            if predicted is not None:
                segmentation.append(
                    {
                        "case_id": case["case_id"],
                        "view": view,
                        "iou": mask_iou(read_mask(base, mask), read_mask(base, predicted)),
                    }
                )
    report["localization"] = {
        "status": "measured" if localization else "blocked_no_assessable_regions",
        "views": localization,
    }
    report["segmentation"] = {
        "status": "measured" if segmentation else "blocked_no_assessable_masks",
        "views": segmentation,
    }
    return report


def binary_metrics(truth, predictions):
    labelled = [
        (label, prediction)
        for label, prediction in zip(truth, predictions, strict=True)
        if label is not None
    ]
    assessed = [(label, prediction) for label, prediction in labelled if prediction is not None]
    if not labelled:
        return {"status": "blocked_no_labels", "labelled": 0}
    tp = sum(label is True and prediction is True for label, prediction in assessed)
    fp = sum(label is False and prediction is True for label, prediction in assessed)
    tn = sum(label is False and prediction is False for label, prediction in assessed)
    fn = sum(label is True and prediction is False for label, prediction in assessed)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "status": "measured",
        "labelled": len(labelled),
        "assessed": len(assessed),
        "abstention_rate": 1 - len(assessed) / len(labelled),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
    }


def box_iou(first, second):
    a, b = np.asarray(first, float), np.asarray(second, float)
    if (
        a.shape != (4,)
        or b.shape != (4,)
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
        or np.any(a[2:] <= a[:2])
        or np.any(b[2:] <= b[:2])
    ):
        raise ValueError("Invalid localization boxes")
    intersection = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
    return float(intersection / ((a[2:] - a[:2]).prod() + (b[2:] - b[:2]).prod() - intersection))


def mask_iou(first, second):
    if first.shape != second.shape or first.dtype != np.bool_ or second.dtype != np.bool_:
        raise ValueError("Invalid evaluation masks")
    union = (first | second).sum()
    return float((first & second).sum() / union) if union else None


def region_metrics(truth, proposals, threshold=0.3):
    used, matched = set(), []
    for proposal in proposals:
        choices = [
            (box_iou(proposal, box), index) for index, box in enumerate(truth) if index not in used
        ]
        best = max(choices, default=(0, -1))
        if best[0] >= threshold:
            used.add(best[1])
            matched.append(best[0])
    tp, fp, fn = len(used), len(proposals) - len(used), len(truth) - len(used)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "matched_ious": matched,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }
