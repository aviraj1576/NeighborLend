"""Bounded engineering experiments; these captures are not a damage holdout."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / ".runtime/v3-packages"))

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ep_engine.core.exceptions import EPError
from ep_engine.cv.geometry import align_pair, geometric_support, validate_transform
from ep_engine.cv.worker import load_inputs
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import LoFTRMatcher, verify_correspondences

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".test-artifacts/ep-v31-20261111"
OUT = ROOT / ".test-artifacts/ep-v31-improvement-20261111"


def read(path):
    return json.loads(path.read_text("utf-8"))


def crop(image, mask):
    ys, xs = np.where(mask)
    x, y = max(0, xs.min() - 16), max(0, ys.min() - 16)
    right, bottom = min(image.shape[1], xs.max() + 17), min(image.shape[0], ys.max() + 17)
    return image[y:bottom, x:right], mask[y:bottom, x:right], np.array([x, y])


def main():
    cv2.setNumThreads(1)
    jobs = [j for j in read(RELEASE / "evaluation-manifest.json") if j["kind"] == "real_pair"]
    sheet = Image.new("RGB", (1100, 300 * len(jobs)), "white")
    draw = ImageDraw.Draw(sheet)
    records = []
    for index, job in enumerate(jobs):
        payload = read(Path(job["manifest"]))
        folder = RELEASE / "current-release" / job["case_id"]
        package = read(folder / "result.json")["cv_package"]
        inputs = load_inputs(payload)
        images = [r.rgb for r in inputs]
        masks = []
        for col, (rgb, segment) in enumerate(zip(images, package["segmentation"], strict=True)):
            thumb = Image.fromarray(rgb)
            thumb.thumbnail((260, 270))
            sheet.paste(thumb, (col * 540, index * 300 + 25))
            if segment["mask_id"]:
                mask = (
                    np.asarray(Image.open(folder / "artifacts" / f"{segment['mask_id']}.png")) > 0
                )
                masks.append(mask)
                overlay = rgb.copy()
                overlay[~mask] //= 4
                thumb = Image.fromarray(overlay)
                thumb.thumbnail((260, 270))
                sheet.paste(thumb, (col * 540 + 265, index * 300 + 25))
        draw.text((5, index * 300 + 5), f"{job['case_id']} : {package['outcome']}", fill="black")
        if "--images" in sys.argv or len(masks) != 2 or package["outcome"] == "comparable":
            continue
        config = V3Config.model_validate(payload["config"])
        matcher = LoFTRMatcher(config)
        for cropped in (False, True):
            prepared = [
                crop(im, m) if cropped else (im, m, np.zeros(2))
                for im, m in zip(images, masks, strict=True)
            ]
            for turns in range(4):
                im0, m0, offset0 = prepared[0]
                im1, m1, offset1 = prepared[1]
                h, w = im1.shape[:2]
                rotations = [
                    np.eye(3),
                    np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1.0]]),
                    np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1.0]]),
                    np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1.0]]),
                ]
                started = time.perf_counter()
                src, dst = matcher(im0, np.rot90(im1, turns).copy(), m0, np.rot90(m1, turns).copy())
                if len(dst):
                    dst = cv2.perspectiveTransform(dst[None], np.linalg.inv(rotations[turns]))[0]
                src, dst = (src + offset0).astype(np.float32), (dst + offset1).astype(np.float32)
                cv2.setRNGSeed(0)
                matrix, support, reason = verify_correspondences(src, dst, *masks, config)
                diagnostics = []
                if len(src) >= 12:
                    fits = [("homography", *cv2.findHomography(src, dst, cv2.RANSAC, 3.0))]
                    affine, inliers = cv2.estimateAffinePartial2D(
                        src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0
                    )
                    if affine is not None:
                        fits.append(("similarity", np.vstack((affine, [0, 0, 1.0])), inliers))
                    for model, candidate, inliers in fits:
                        if candidate is None:
                            continue
                        diagnostic = dict(model=model, ransac_inliers=int(inliers.sum()))
                        try:
                            validate_transform(candidate, masks[0].shape, masks[1].shape)
                        except EPError as error:
                            diagnostic["transform_rejection"] = str(error)
                        forward = cv2.perspectiveTransform(src[None], candidate)[0]
                        reverse = cv2.perspectiveTransform(dst[None], np.linalg.inv(candidate))[0]
                        valid = (
                            inliers.ravel().astype(bool)
                            & (np.linalg.norm(forward - dst, axis=1) <= 3)
                            & (
                                np.linalg.norm(reverse - src, axis=1)
                                * np.sqrt(masks[1].size / masks[0].size)
                                <= 3
                            )
                        )
                        diagnostic["symmetric_inliers"] = int(valid.sum())
                        diagnostic["ratio"] = float(valid.mean())
                        diagnostic["support"] = geometric_support(
                            src, dst, candidate, valid, *masks, config
                        )
                        diagnostics.append(diagnostic)
                overlap = None
                if matrix is not None:
                    try:
                        warped, common = align_pair(images[0], *masks, matrix, config)
                        overlap = float(common.sum() / masks[1].sum())
                        name = f"{job['case_id']}-crop{int(cropped)}-rot{turns}"
                        Image.fromarray(warped).save(OUT / f"{name}-warp.png")
                        Image.fromarray(images[1]).save(OUT / f"{name}-after.png")
                    except EPError as error:
                        reason = error.code
                record = dict(
                    case=job["case_id"],
                    crop=cropped,
                    turns=turns,
                    matches=len(src),
                    support=support,
                    reason=reason,
                    overlap=overlap,
                    diagnostics=diagnostics,
                    seconds=time.perf_counter() - started,
                )
                records.append(record)
                print(json.dumps(record), flush=True)
                if cropped and len(src) >= 24:
                    ys, xs = np.where(masks[0])
                    midx, midy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
                    for q in range(4):
                        selected = ((src[:, 0] >= midx) == bool(q % 2)) & (
                            (src[:, 1] >= midy) == bool(q // 2)
                        )
                        s, d = src[selected], dst[selected]
                        cv2.setRNGSeed(0)
                        local, supported, rejection = verify_correspondences(s, d, *masks, config)
                        record = dict(
                            case=job["case_id"],
                            crop=True,
                            turns=turns,
                            quadrant=q,
                            matches=len(s),
                            support=supported,
                            reason=rejection,
                        )
                        if local is not None:
                            predicted = cv2.perspectiveTransform(s[None], local)[0]
                            inverse = cv2.perspectiveTransform(d[None], np.linalg.inv(local))[0]
                            valid = (np.linalg.norm(predicted - d, axis=1) <= 3) & (
                                np.linalg.norm(inverse - s, axis=1)
                                * np.sqrt(masks[1].size / masks[0].size)
                                <= 3
                            )
                            hull = np.zeros(masks[1].shape, np.uint8)
                            cv2.fillConvexPoly(hull, cv2.convexHull(d[valid]).astype(np.int32), 1)
                            try:
                                warped, common = align_pair(images[0], *masks, local, config)
                                common &= cv2.erode(hull, np.ones((9, 9), np.uint8)).astype(bool)
                                record["local_overlap"] = float(common.sum() / masks[1].sum())
                                tile = np.concatenate([warped, images[1]], axis=1)
                                tile[~np.concatenate([common, common], axis=1)] //= 4
                                Image.fromarray(tile).save(
                                    OUT / f"{job['case_id']}-local-r{turns}-q{q}.png"
                                )
                            except EPError as error:
                                record["reason"] = error.code
                        records.append(record)
                        print(json.dumps(record), flush=True)
        matcher.close()
    sheet.save(OUT / "contact-sheet.jpg")
    if records:
        (OUT / "matching-experiment.json").write_text(json.dumps(records, indent=2), "utf-8")


if __name__ == "__main__":
    main()
