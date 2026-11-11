import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import Pair
from ep_engine.cv.numerics import bounded_cosine


def local_features(rgb, mask):
    # Precise pyramid coordinates avoid the half-pixel localization bias that
    # otherwise turns a quarter-turn of unchanged texture into change proposals.
    detector = cv2.SIFT_create(nfeatures=1200, enable_precise_upscale=True)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    keypoints, descriptors = detector.detectAndCompute(gray, mask.astype(np.uint8) * 255)
    if descriptors is not None:
        descriptors = np.sqrt(
            descriptors / np.maximum(descriptors.sum(axis=1, keepdims=True), 1e-8)
        )
    return keypoints, descriptors


def geometric_support(src, dst, matrix, inliers, before_mask, after_mask, config):
    valid = inliers.ravel().astype(bool)
    count = int(valid.sum())
    if count < config.min_inliers or valid.mean() < config.min_inlier_ratio:
        return None
    forward = cv2.perspectiveTransform(src[None], matrix)[0]
    reverse = cv2.perspectiveTransform(dst[None], np.linalg.inv(matrix))[0]
    error = float(np.median(np.linalg.norm(forward[valid] - dst[valid], axis=1)))
    reverse_error = float(np.median(np.linalg.norm(reverse[valid] - src[valid], axis=1)))
    scale = np.sqrt(after_mask.size / before_mask.size)
    symmetric_error = max(error, reverse_error * scale)
    source_coverage = min(
        1.0, abs(cv2.contourArea(cv2.convexHull(src[valid]))) / max(1, before_mask.sum())
    )
    target_coverage = min(
        1.0, abs(cv2.contourArea(cv2.convexHull(dst[valid]))) / max(1, after_mask.sum())
    )
    if min(source_coverage, target_coverage) < 0.03 or symmetric_error > 3:
        return None
    return dict(
        inliers=count,
        inlier_ratio=float(valid.mean()),
        median_reprojection_error=error,
        symmetric_reprojection_error=symmetric_error,
        source_coverage=source_coverage,
        target_coverage=target_coverage,
    )


def validate_transform(matrix, before_shape, after_shape):
    if (
        matrix is None
        or matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or abs(matrix[2, 2]) < 1e-9
    ):
        raise EPError(422, "unstable_geometry", "Invalid geometric transform")
    matrix = matrix / matrix[2, 2]
    bh, bw = before_shape
    ah, aw = after_shape
    normalized = np.diag([1 / aw, 1 / ah, 1]) @ matrix @ np.diag([bw, bh, 1])
    if np.linalg.det(normalized) <= 1e-6 or np.linalg.cond(normalized) > 10000:
        raise EPError(422, "unstable_geometry", "Degenerate or reflected geometry")
    corners = np.float32([[[0, 0], [bw, 0], [bw, bh], [0, bh]]])
    denominators = np.c_[corners[0], np.ones(4)] @ matrix[2]
    if np.any(denominators <= 1e-8):
        raise EPError(422, "unstable_geometry", "Projective horizon intersects the image")
    projected = cv2.perspectiveTransform(corners, matrix)[0]
    area = abs(cv2.contourArea(projected)) / (aw * ah)
    if (
        not cv2.isContourConvex(projected)
        or not 0.05 < area < 4
        or np.max(np.abs(projected)) > 5 * max(aw, ah)
    ):
        raise EPError(422, "unstable_geometry", "Extreme geometric warp")
    return matrix


def match_pair(
    before_id, after_id, before, after, before_mask, after_mask, similarity, config, features=None
):
    pair = Pair(
        before_id=before_id,
        after_id=after_id,
        cosine_similarity=bounded_cosine(similarity),
        method="dinov2_full_object_rot4_rootsift_mutual_ransac_v2_1",
    )
    if similarity < config.min_similarity:
        pair.reasons.append("embedding_inconsistent")
        return pair, None
    pair.local_matching_evaluated = True
    (kp1, des1), (kp2, des2) = features or (
        local_features(before, before_mask),
        local_features(after, after_mask),
    )
    if des1 is None or des2 is None or min(len(des1), len(des2)) < 8:
        pair.reasons.append("insufficient_correspondence")
        return pair, None
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(des1, des2, k=2)
    reverse = matcher.knnMatch(des2, des1, k=2)
    reverse_good = {
        m.queryIdx: m.trainIdx
        for values in reverse
        if len(values) == 2
        for m, n in [values]
        if m.distance < 0.75 * n.distance
    }
    good = [
        m
        for values in forward
        if len(values) == 2
        for m, n in [values]
        if m.distance < 0.75 * n.distance and reverse_good.get(m.trainIdx) == m.queryIdx
    ]
    pair.matches = len(good)
    if len(good) < config.min_inliers:
        pair.reasons.append("insufficient_correspondence")
        return pair, None
    src = np.float32([kp1[m.queryIdx].pt for m in good])
    dst = np.float32([kp2[m.trainIdx].pt for m in good])
    matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if inliers is None or inliers.size != len(good) or not np.isin(inliers, (0, 1)).all():
        pair.reasons.append("unstable_geometry")
        return pair, None
    try:
        matrix = validate_transform(matrix, before.shape[:2], after.shape[:2])
        support = geometric_support(src, dst, matrix, inliers, before_mask, after_mask, config)
    except EPError:
        support = None
    if support is None:
        # A lower-degree model is allowed only with the SAME correspondence, support,
        # error and inlier requirements. No mask-only or embedding-only registration.
        affine, affine_inliers = cv2.estimateAffinePartial2D(
            src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0
        )
        if affine is not None and affine_inliers is not None:
            alternative = np.vstack((affine, [0.0, 0.0, 1.0]))
            try:
                alternative = validate_transform(alternative, before.shape[:2], after.shape[:2])
                support = geometric_support(
                    src, dst, alternative, affine_inliers, before_mask, after_mask, config
                )
                if support is not None:
                    matrix = alternative
                    pair.geometry_model = "similarity"
            except EPError:
                support = None
    if support is None:
        pair.reasons.append("weak_geometric_support_or_view_change")
        return pair, None
    for key, value in support.items():
        setattr(pair, key, value)
    pair.identity = "consistent_visual_evidence"
    pair.homography = matrix.tolist()
    return pair, matrix


def align_pair(before, before_mask, after_mask, matrix, config):
    matrix = validate_transform(matrix, before.shape[:2], after_mask.shape)
    height, width = after_mask.shape
    warped = cv2.warpPerspective(before, matrix, (width, height))
    warped_mask = cv2.warpPerspective(
        before_mask.astype(np.uint8), matrix, (width, height), flags=cv2.INTER_NEAREST
    ).astype(bool)
    overlap = warped_mask & after_mask
    overlap = cv2.erode(overlap.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    fraction = overlap.sum() / max(1, min(warped_mask.sum(), after_mask.sum()))
    if fraction < config.min_overlap or overlap.sum() < 64:
        raise EPError(422, "insufficient_overlap", "Insufficient valid object overlap")
    return warped, overlap
