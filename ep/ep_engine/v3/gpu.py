"""Measured opt-in CUDA kernels; CPU masks/components retain explainable coordinates."""

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.geometry import validate_transform


def cuda_modules():
    import torch
    import torch.nn.functional as functional

    if not torch.cuda.is_available():
        raise EPError(503, "cuda_unavailable", "Explicit CUDA processing requires a GPU")
    return torch, functional


def align_cuda(before, before_mask, after_mask, matrix, config):
    import torch
    from kornia.geometry.transform import warp_perspective

    cuda_modules()
    matrix = validate_transform(matrix, before.shape[:2], after_mask.shape)
    if max(*before.shape[:2], *after_mask.shape) > config.max_side:
        raise EPError(413, "processing_limit", "Warp exceeds configured processing dimensions")
    height, width = after_mask.shape
    with torch.inference_mode():
        image = torch.from_numpy(before.copy()).permute(2, 0, 1)[None].float().to("cuda")
        mask = torch.from_numpy(before_mask.copy())[None, None].float().to("cuda")
        transform = torch.from_numpy(matrix.copy()).float()[None].to("cuda")
        warped = warp_perspective(image, transform, (height, width), align_corners=True)
        warped_mask = (
            warp_perspective(mask, transform, (height, width), mode="nearest", align_corners=True)[
                0, 0
            ]
            .gt(0.5)
            .cpu()
            .numpy()
        )
        footprint = (
            warp_perspective(torch.ones_like(mask), transform, (height, width), align_corners=True)[
                0, 0
            ]
            .gt(0.999)
            .cpu()
            .numpy()
        )
        result = warped[0].permute(1, 2, 0).round().clamp(0, 255).byte().cpu().numpy()
    overlap = warped_mask & after_mask & footprint
    overlap = cv2.erode(overlap.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    fraction = overlap.sum() / max(1, min(warped_mask.sum(), after_mask.sum()))
    if fraction < config.min_overlap or overlap.sum() < 64:
        raise EPError(422, "insufficient_overlap", "Insufficient valid object overlap")
    return result, overlap


def appearance_cuda(before, after, overlap, config):
    torch, functional = cuda_modules()
    if max(overlap.shape) > config.max_side:
        raise EPError(413, "processing_limit", "Appearance exceeds processing dimensions")
    if overlap.sum() < 64:
        return np.zeros(overlap.shape, np.float32), []
    # Exact OpenCV luminance preserves parity; heavy SSIM/quantile work runs on CUDA.
    with torch.inference_mode():
        first, second = [
            torch.from_numpy(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
            .to(device="cuda", dtype=torch.float32)
            .div(255)
            for rgb in (before, after)
        ]
        valid = torch.from_numpy(overlap.copy()).to("cuda")
        levels = torch.tensor([0.1, 0.9], device="cuda")
        lo1, hi1 = torch.quantile(first[valid], levels)
        lo2, hi2 = torch.quantile(second[valid], levels)
        gain = torch.where(
            hi1 - lo1 > 0.1,
            ((hi2 - lo2) / (hi1 - lo1).clamp_min(1e-8)).clamp(0.67, 1.5),
            torch.ones_like(lo1),
        )
        # torch.median chooses the lower middle; quantile(.5) matches numpy median.
        offset = torch.quantile(second[valid] - gain * first[valid], 0.5)
        adjusted = (gain * first + offset).clamp(0, 1)
        kernel = torch.from_numpy(cv2.getGaussianKernel(7, 1.5).astype(np.float32)).to("cuda")
        kernel = (kernel @ kernel.T)[None, None]

        def blur(value):
            return functional.conv2d(
                functional.pad(value[None, None], (3,) * 4, mode="reflect"), kernel
            )[0, 0]

        mu1, mu2 = blur(adjusted), blur(second)
        var1 = (blur(adjusted * adjusted) - mu1 * mu1).clamp_min(0)
        var2 = (blur(second * second) - mu2 * mu2).clamp_min(0)
        cov = blur(adjusted * second) - mu1 * mu2
        similarity = (
            ((2 * mu1 * mu2 + 0.0001) * (2 * cov + 0.0009))
            / ((mu1 * mu1 + mu2 * mu2 + 0.0001) * (var1 + var2 + 0.0009))
        ).clamp(-1, 1)
        difference = ((1 - similarity) / 2).clamp(0, 1)
        difference[~valid] = 0
        proposals = (
            (
                (difference > config.difference_threshold)
                & ((adjusted - second).abs() > 0.06)
                & valid
            )
            .byte()
            .cpu()
            .numpy()
        )
        difference = difference.cpu().numpy()
    proposals = cv2.morphologyEx(proposals, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    proposals[~overlap] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(proposals)
    regions = []
    for label in range(1, count):
        x, y, width, height, area = map(int, stats[label])
        if config.min_candidate_area <= area <= 0.4 * overlap.sum():
            regions.append((x, y, width, height, area, float(difference[labels == label].mean())))
    return difference, sorted(regions, key=lambda value: value[4], reverse=True)[:20]
