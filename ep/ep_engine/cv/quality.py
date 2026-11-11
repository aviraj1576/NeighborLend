import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import Quality


def assess_quality(evidence_id, rgb, config, mask=None):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise EPError(422, "invalid_image", "Invalid quality-assessment image")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    values = gray[mask] if mask is not None and mask.any() else gray.ravel()
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    focus = float(laplacian[mask].var() if mask is not None and mask.any() else laplacian.var())
    dark, bright = float((values < 10).mean()), float((values > 245).mean())
    reasons = []
    if min(gray.shape) < config.min_side:
        reasons.append("low_resolution")
    if focus < config.min_focus:
        reasons.append("blur_or_no_texture")
    if values.std() < config.min_contrast:
        reasons.append("low_contrast")
    if dark > config.max_clipped_fraction:
        reasons.append("underexposed")
    if bright > config.max_clipped_fraction:
        reasons.append("overexposed")
    unusable = bool(reasons)
    touches = bool(
        mask is not None
        and (mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
    )
    if touches:
        reasons.append("possible_cropping")
    guidance = {
        "blur_or_no_texture": (
            "Recapture in focus with steady support, diffuse light and visible surface detail; "
            "do not upscale or sharpen to pass the gate"
        ),
        "low_resolution": "Provide the original-resolution file and a closer view of the object",
        "low_contrast": "Use diffuse even lighting and a contrasting plain background",
        "underexposed": "Increase diffuse illumination; retain detail on dark surfaces",
        "overexposed": "Reduce glare and exposure; avoid direct flash on reflective surfaces",
        "possible_cropping": (
            "Capture the complete object and accessories, plus separate matched closeups"
        ),
    }
    return Quality(
        evidence_id=evidence_id,
        status="needs_recapture" if unusable else "usable",
        width=gray.shape[1],
        height=gray.shape[0],
        focus_variance=focus,
        contrast_std=float(values.std()),
        mean_exposure=float(values.mean() / 255),
        dark_fraction=dark,
        bright_fraction=bright,
        object_fraction=float(mask.mean()) if mask is not None else None,
        touches_frame=touches,
        reasons=reasons,
        recommendations=[guidance[r] for r in reasons],
    )
