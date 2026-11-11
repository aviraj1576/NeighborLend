"""Conservative prompt/mask checks; these are plausibility checks, not object identity."""

import cv2
import numpy as np
from PIL import Image

from ep_engine.core.exceptions import EPError


def mask_support(mask, box):
    height, width = mask.shape
    x1, y1, x2, y2 = box
    target = np.zeros_like(mask)
    target[
        int(y1 * height) : max(int(y1 * height) + 1, int(y2 * height)),
        int(x1 * width) : max(int(x1 * width) + 1, int(x2 * width)),
    ] = True
    area = int(mask.sum())
    intersection = int((mask & target).sum())
    border = np.concatenate((mask[0], mask[-1], mask[1:-1, 0], mask[1:-1, -1]))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    dominance = float(stats[1:, cv2.CC_STAT_AREA].max() / max(1, area)) if count > 1 else 0
    return {
        "box_iou": intersection / max(1, int((mask | target).sum())),
        "outside_target_fraction": (area - intersection) / max(1, area),
        "target_fill": intersection / max(1, int(target.sum())),
        "frame_border_fraction": float(border.mean()),
        "largest_component_fraction": dominance,
    }


def validate_target_mask(mask, box):
    support = mask_support(mask, box)
    if (
        support["outside_target_fraction"] > 0.20
        or support["target_fill"] < 0.08
        or support["box_iou"] < 0.15
        or support["frame_border_fraction"] > 0.55
        or support["largest_component_fraction"] < 0.75
    ):
        raise EPError(
            503,
            "invalid_mask",
            "Object mask is inconsistent with the target or selects frame background",
        )
    return support


def select_target_mask(masks, scores, box):
    """Rank all SAM hypotheses after validating each, rather than trusting IoU head alone."""
    valid = []
    for mask, score in zip(masks, scores, strict=True):
        if mask.dtype != np.bool_ or not 0.001 < mask.mean() < 0.98:
            continue
        try:
            support = validate_target_mask(mask, box)
        except EPError:
            continue
        rank = 0.6 * support["box_iou"] + 0.4 * float(np.clip(score, 0, 1))
        valid.append((rank, mask, support))
    if not valid:
        raise EPError(
            503, "invalid_mask", "No plausible object mask; supply a tighter target or recapture"
        )
    valid.sort(key=lambda r: r[0], reverse=True)
    if len(valid) > 1 and valid[0][0] - valid[1][0] < 0.03:
        first, second = valid[0][1], valid[1][1]
        if (first & second).sum() / max(1, (first | second).sum()) < 0.5:
            raise EPError(503, "invalid_mask", "Competing foreground masks require target review")
    return valid[0][1]


def embedding_canvas(rgb, mask):
    """Keep the entire masked object in a square; center-cropping loses long-object parts."""
    ys, xs = np.where(mask)
    cropped = rgb[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].copy()
    local_mask = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    if max(cropped.shape[:2]) / min(cropped.shape[:2]) > 16:
        raise EPError(503, "invalid_embedding", "Object crop has unsafe extreme aspect ratio")
    cropped[~local_mask] = (124, 116, 104)
    image = Image.fromarray(cropped)
    image.thumbnail((224, 224), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (224, 224), (124, 116, 104))
    canvas.paste(image, ((224 - image.width) // 2, (224 - image.height) // 2))
    return np.asarray(canvas, dtype=np.float32) / 255
