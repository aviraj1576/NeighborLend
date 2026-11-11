"""Object crops and fixed spatial partitions; no mask-only registration."""

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.geometry import align_pair
from ep_engine.v3.matching import filter_correspondences


def object_crop(image, mask):
    ys, xs = np.where(mask)
    x, y = max(0, int(xs.min()) - 16), max(0, int(ys.min()) - 16)
    right = min(image.shape[1], int(xs.max()) + 17)
    bottom = min(image.shape[0], int(ys.max()) + 17)
    return image[y:bottom, x:right], mask[y:bottom, x:right], np.array([x, y], np.float32)


def restore_rotation(points, turns, shape):
    h, w = shape
    rotations = (
        np.eye(3),
        np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1.0]]),
        np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1.0]]),
        np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1.0]]),
    )
    if not len(points):
        return points.copy()
    return cv2.perspectiveTransform(points[None], np.linalg.inv(rotations[turns]))[0]


def cropped_matches(matcher, first, second, mask0, mask1, turns):
    a, ma, offset0 = object_crop(first, mask0)
    b, mb, offset1 = object_crop(second, mask1)
    src, dst = matcher(a, np.rot90(b, turns).copy(), ma, np.rot90(mb, turns).copy())
    # Validate adapter outputs before applying coordinate transformations.
    src, dst = filter_correspondences(src, dst, np.ones(len(src)), ma, np.rot90(mb, turns))
    src = src + offset0
    dst = restore_rotation(dst, turns, mb.shape) + offset1
    return filter_correspondences(src, dst, np.ones(len(src)), mask0, mask1)


def local_surfaces(src, dst, first, mask0, mask1, config, verify):
    """Four predeclared source quadrants, never iteratively peel fitted inliers.

    A local fit cannot make the whole view comparable. Both correspondence hulls
    restrict its overlap; no change or silhouette inference outside that support.
    """
    ys, xs = np.where(mask0)
    midx, midy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    regions = []
    for quadrant in range(4):
        selected = ((src[:, 0] >= midx) == bool(quadrant % 2)) & (
            (src[:, 1] >= midy) == bool(quadrant // 2)
        )
        a, b = src[selected], dst[selected]
        matrix, support, _ = verify(a, b, mask0, mask1, config)
        if matrix is None:
            continue
        forward = cv2.perspectiveTransform(a[None], matrix)[0]
        reverse = cv2.perspectiveTransform(b[None], np.linalg.inv(matrix))[0]
        inliers = (np.linalg.norm(forward - b, axis=1) <= 3) & (
            np.linalg.norm(reverse - a, axis=1) * np.sqrt(mask1.size / mask0.size) <= 3
        )
        hulls = []
        for points, mask in ((a, mask0), (b, mask1)):
            hull = np.zeros(mask.shape, np.uint8)
            cv2.fillConvexPoly(hull, cv2.convexHull(points[inliers]).astype(np.int32), 1)
            hulls.append(hull.astype(bool) & mask)
        try:
            # Global transform validity and existing overlap gates still apply.
            align_pair(first, mask0, mask1, matrix, config)
            _, overlap = align_pair(first, *hulls, matrix, config)
        except EPError as error:
            if error.code not in {"unstable_geometry", "insufficient_overlap"}:
                raise
            continue
        regions.append(
            dict(matrix=matrix, overlap=overlap, support=support, quadrant=quadrant, matches=len(a))
        )
    return regions
