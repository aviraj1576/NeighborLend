import cv2
import numpy as np


def ssim_map(before, after):
    """Gaussian-window SSIM, data range 1, sigma 1.5, K1=.01, K2=.03; not damage confidence."""

    def blur(value):
        return cv2.GaussianBlur(value, (7, 7), 1.5)

    mu1, mu2 = blur(before), blur(after)
    var1 = np.maximum(blur(before * before) - mu1 * mu1, 0)
    var2 = np.maximum(blur(after * after) - mu2 * mu2, 0)
    cov = blur(before * after) - mu1 * mu2
    return np.clip(
        ((2 * mu1 * mu2 + 0.0001) * (2 * cov + 0.0009))
        / ((mu1 * mu1 + mu2 * mu2 + 0.0001) * (var1 + var2 + 0.0009)),
        -1,
        1,
    )


def photometric_pair(before, after, overlap):
    gray1 = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gray2 = cv2.cvtColor(after, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    # Robust global gain/offset correction; never normalize quality-gate inputs.
    low1, high1 = np.quantile(gray1[overlap], [0.1, 0.9])
    low2, high2 = np.quantile(gray2[overlap], [0.1, 0.9])
    gain = float(np.clip((high2 - low2) / (high1 - low1), 0.67, 1.5)) if high1 - low1 > 0.1 else 1.0
    offset = np.median(gray2[overlap] - gain * gray1[overlap])
    adjusted = np.clip(gain * gray1 + offset, 0, 1)
    return adjusted, gray2


def find_changes(before, after, overlap, config):
    if overlap.sum() < 64:
        return np.zeros(overlap.shape, np.float32), []
    adjusted, gray2 = photometric_pair(before, after, overlap)
    difference = np.clip((1 - ssim_map(adjusted, gray2)) / 2, 0, 1)
    difference[~overlap] = 0
    proposals = (
        (difference > config.difference_threshold) & (np.abs(adjusted - gray2) > 0.06) & overlap
    ).astype(np.uint8)
    # Opening with 3x3 erased one/two-pixel crack/scratch evidence. Area filtering
    # removes small isolated noise while retaining thin connected structures.
    proposals = cv2.morphologyEx(proposals, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    proposals[~overlap] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(proposals)
    regions = []
    for label in range(1, count):
        x, y, width, height, area = map(int, stats[label])
        if config.min_candidate_area <= area <= 0.4 * overlap.sum():
            regions.append((x, y, width, height, area, float(difference[labels == label].mean())))
    return difference, sorted(regions, key=lambda value: value[4], reverse=True)[:20]


def boundary_regions(before_mask, after_mask, matrix, config, *, aligned_before=None, after=None):
    """Directional silhouette changes, separate from shared-surface appearance evidence.

    A mask cannot distinguish physical removal from occlusion. Never call these
    confirmed missing parts, and abstain on clipped objects or gross disagreement.
    """
    height, width = after_mask.shape
    warped = cv2.warpPerspective(
        before_mask.astype(np.uint8), matrix, (width, height), flags=cv2.INTER_NEAREST
    ).astype(bool)
    if any(
        m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any()
        for m in (before_mask, after_mask, warped)
    ):
        return [], ["boundary_unassessable_cropped_object"]
    union = warped | after_mask
    if (warped ^ after_mask).sum() / max(1, union.sum()) > 0.35:
        return [], ["mask_disagreement_or_view_change"]
    footprint = cv2.warpPerspective(
        np.ones(before_mask.shape, np.uint8), matrix, (width, height), flags=cv2.INTER_NEAREST
    )
    footprint = cv2.erode(footprint, np.ones((9, 9), np.uint8)).astype(bool)
    appearance_residual = None
    unsupported = False
    if aligned_before is not None and after is not None:
        shared = cv2.erode(
            (warped & after_mask & footprint).astype(np.uint8), np.ones((9, 9), np.uint8)
        ).astype(bool)
        if shared.sum() < 64:
            return [], ["boundary_appearance_unassessable"]
        adjusted, gray2 = photometric_pair(aligned_before, after, shared)
        appearance_residual = np.abs(adjusted - gray2)
    regions = []
    for direction, source, other in (
        ("potentially_missing", warped, after_mask),
        ("additional_or_displaced", after_mask, warped),
    ):
        core = cv2.erode(source.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        tolerance = cv2.dilate(other.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        change = core & ~tolerance & footprint
        count, labels, stats, _ = cv2.connectedComponentsWithStats(change.astype(np.uint8))
        for i in range(1, count):
            x, y, w, h, area = map(int, stats[i])
            if max(config.min_candidate_area, 0.002 * union.sum()) <= area <= 0.35 * union.sum():
                if (
                    appearance_residual is not None
                    and np.median(appearance_residual[labels == i]) <= 0.06
                ):
                    unsupported = True
                    continue
                regions.append(dict(direction=direction, box_xywh=[x, y, w, h], area_pixels=area))
    return sorted(regions, key=lambda r: r["area_pixels"], reverse=True)[:20], [
        "Boundary changes can be occlusion, pose or segmentation error; "
        "semantic part identity is unverified",
        *(["boundary_without_appearance_support"] if unsupported else []),
    ]
