"""Reproducible v2/v3 controls and kernels; synthetic edits are not physical damage labels."""

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import psutil
from PIL import Image

from ep_engine.config import EP_ROOT
from ep_engine.cv.changes import find_changes
from ep_engine.cv.concurrency import worker_guard
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.geometry import align_pair, local_features
from ep_engine.cv.models import NativeModels
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.cv.quality import assess_quality
from ep_engine.schemas.models import Box
from ep_engine.v3.config import V3Config
from ep_engine.v3.gpu import align_cuda, appearance_cuda
from ep_engine.v3.matching import HybridMatcher, rootsift_correspondences, verify_correspondences
from ep_engine.v3.pipeline import CachedModels, V3Pipeline


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def timed(callback, repeats=7):
    import torch

    values, result = [], None
    for index in range(repeats + 2):
        torch.cuda.synchronize()
        start = time.perf_counter()
        result = callback()
        torch.cuda.synchronize()
        if index >= 2:
            values.append(time.perf_counter() - start)
    return {"median_seconds": float(np.median(values)), "samples_seconds": values}, result


def quality_audit(destination):
    records = []
    for path in sorted((EP_ROOT / "test_images").glob("[0-9][0-9]_*/*/*.jpg")):
        with Image.open(path) as image:
            source = np.asarray(image.convert("RGB"))
        variants = {"source": source}
        for side in (768, 1024):
            scale = min(1, side / max(source.shape[:2]))
            variants[str(side)] = cv2.resize(
                source,
                (round(source.shape[1] * scale), round(source.shape[0] * scale)),
                interpolation=cv2.INTER_AREA,
            )
        records.append(
            {
                "path": str(path.relative_to(EP_ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "labels": None,
                "quality": {
                    name: assess_quality(uuid4(), rgb, CVConfig(max_side=1024)).model_dump(
                        mode="json"
                    )
                    for name, rgb in variants.items()
                },
            }
        )
    report = {
        "images": len(records),
        "records": records,
        "note": "No reviewed focus labels. Thresholds unchanged; no calibration claimed.",
    }
    write(destination / "quality-audit.json", report)
    return {
        "images": len(records),
        "usable": {
            name: sum(row["quality"][name]["status"] == "usable" for row in records)
            for name in ("source", "768", "1024")
        },
    }


def kernel_benchmark(destination, config):
    import torch

    image = np.random.default_rng(83).integers(20, 230, (768, 768, 3), np.uint8)
    mask = np.zeros((768, 768), bool)
    mask[30:-30, 30:-30] = True
    matrix = np.array([[1, 0.01, 3], [0.008, 1, -2], [0.00001, 0, 1]], np.float64)
    after = cv2.warpPerspective(image, matrix, (768, 768))
    after_mask = cv2.warpPerspective(mask.astype(np.uint8), matrix, (768, 768)).astype(bool)
    result = {}
    cpu, (warped_cpu, overlap_cpu) = timed(
        lambda: align_pair(image, mask, after_mask, matrix, config)
    )
    gpu, (warped_gpu, overlap_gpu) = timed(
        lambda: align_cuda(image, mask, after_mask, matrix, config)
    )
    shared = overlap_cpu & overlap_gpu
    result["alignment"] = {
        "opencv": cpu,
        "cuda": gpu,
        "mean_absolute_pixel_error": float(
            np.abs(warped_cpu[shared].astype(float) - warped_gpu[shared]).mean()
        ),
        "overlap_iou": float(shared.sum() / (overlap_cpu | overlap_gpu).sum()),
    }
    changed = image.copy()
    cv2.line(changed, (250, 200), (280, 450), (0, 0, 0), 2)
    cpu, (diff0, regions0) = timed(lambda: find_changes(image, changed, mask, config))
    gpu, (diff1, regions1) = timed(lambda: appearance_cuda(image, changed, mask, config))
    result["appearance"] = {
        "opencv": cpu,
        "cuda": gpu,
        "max_map_error": float(np.max(np.abs(diff0 - diff1))),
        "cpu_regions": regions0,
        "gpu_regions": regions1,
    }
    feature_time, features = timed(
        lambda: (local_features(image, mask), local_features(after, after_mask)), repeats=5
    )
    result["rootsift_feature_extraction"] = feature_time
    src, dst = rootsift_correspondences(features)
    cpu, (_, support0, _) = timed(
        lambda: verify_correspondences(
            src, dst, mask, after_mask, config.model_copy(update={"geometry_backend": "opencv"})
        )
    )
    gpu, (_, support1, _) = timed(
        lambda: verify_correspondences(
            src, dst, mask, after_mask, config.model_copy(update={"geometry_backend": "kornia"})
        )
    )
    result["geometry"] = {
        "opencv": cpu,
        "kornia_cuda": gpu,
        "cpu_support": support0,
        "gpu_support": support1,
    }
    # Compare methods on the same actual pixels/correspondences and record cold model load.
    matcher = HybridMatcher(config.model_copy(update={"compare_matchers": True}))
    identifiers = uuid4(), uuid4()
    arguments = (*identifiers, image, after, mask, after_mask, 0.99, matcher.config, features)
    matcher(*arguments)
    result["matching_cold"] = matcher.records.copy()
    timed(lambda: matcher(*arguments), repeats=5)
    result["matching"] = matcher.records[-5:]
    result["matching_warm_median_seconds"] = {
        name: float(
            np.median(
                [
                    attempt["seconds"]
                    for record in matcher.records[-5:]
                    for attempt in record["attempts"]
                    if attempt["matcher"] == name
                ]
            )
        )
        for name in {
            attempt["matcher"] for record in matcher.records[-5:] for attempt in record["attempts"]
        }
    }
    matcher.close()
    result["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated()
    result["peak_cuda_reserved_bytes"] = torch.cuda.max_memory_reserved()
    write(destination / "kernels.json", result)
    return result


def photo_controls():
    source = Path(sys.prefix) / "Lib/site-packages/ultralytics/assets/bus.jpg"
    with Image.open(source) as photo:
        image = photo.convert("RGB")
        high_resolution = image.copy()
        high_resolution.thumbnail((1024, 1024))
        image.thumbnail((768, 768))
        before = np.array(image)
    target = Box(x1=0.03, y1=0.20, x2=0.99, y2=0.72)
    changed = before.copy()
    cv2.line(changed, (250, 200), (280, 400), (0, 0, 0), 2)
    missing = before.copy()
    missing[300:340, 400:450] = (110, 110, 110)
    displaced = before.copy()
    displaced[350:390, 350:400] = before[300:340, 400:450]
    bright = np.clip(before.astype(float) * 1.08 + 8, 0, 255).astype(np.uint8)
    h, w = before.shape[:2]
    matrix = np.array([[1, 0.012, -3], [0.008, 1, -2], [0.00003, 0.00001, 1]], np.float64)
    other_path = source.with_name("zidane.jpg")
    with Image.open(other_path) as photo:
        photo = photo.convert("RGB")
        photo.thumbnail((768, 768))
        other = np.array(photo)
    # Labels describe the generated operation only; no reviewed physical condition labels.
    return (
        before,
        target,
        {
            "unchanged": (before.copy(), target, False),
            "thin_line_edit": (changed, target, True),
            "patch_removal_edit": (missing, target, True),
            "patch_displacement_edit": (displaced, target, True),
            "quarter_turn": (
                np.rot90(before).copy(),
                Box(x1=0.20, y1=0.01, x2=0.72, y2=0.97),
                False,
            ),
            "moderate_perspective": (cv2.warpPerspective(before, matrix, (w, h)), target, False),
            "global_lighting": (bright, target, False),
            "poor_focus": (cv2.GaussianBlur(before, (51, 51), 15), target, None),
            "occlusion_edit": (missing, target, None),
            "cropped_object": (before[:, : w // 2].copy(), target, None),
            "different_photo": (other, Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95), None),
            "high_resolution": (np.array(high_resolution), target, False),
        },
    )


def native_benchmark(destination, config):
    before, target, cases = photo_controls()
    records = []
    for label, cls, cfg, models in (
        ("baseline", CVPipeline, CVConfig(), NativeModels("cuda")),
        ("v3", V3Pipeline, config, CachedModels(config)),
    ):
        for name, (after, after_target, edit) in cases.items():
            inputs = [
                InputImage(
                    uuid4(), stage, rgb.copy(), hashlib.sha256(rgb.tobytes()).hexdigest(), box
                )
                for stage, rgb, box in (("before", before, target), ("after", after, after_target))
            ]
            started = time.perf_counter()
            try:
                case_config = (
                    cfg.model_copy(update={"max_side": 1024}) if name == "high_resolution" else cfg
                )
                source_dir = destination / "sources" / name
                source_dir.mkdir(parents=True, exist_ok=True)
                manifest = {
                    "inspection_id": str(uuid4()),
                    "config": case_config.model_dump(mode="json"),
                    "evidence": [],
                }
                for row in inputs:
                    path = source_dir / f"{row.id}.png"
                    Image.fromarray(row.rgb).save(path)
                    manifest["evidence"].append(
                        {
                            "id": str(row.id),
                            "stage": row.stage,
                            "sha256": row.sha256,
                            "normalized_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "path": str(path),
                            "target": row.target.model_dump(mode="json"),
                        }
                    )
                write(source_dir / f"{label}-input.json", manifest)
                result = cls(case_config, models).run(uuid4(), inputs, destination / label / name)
                content = result.model_dump(mode="json")
                records.append(
                    {
                        "engine": label,
                        "case": name,
                        "synthetic_edit": edit,
                        "wall_seconds": time.perf_counter() - started,
                        "result": content,
                    }
                )
                print(label, name, result.outcome, len(result.candidates), flush=True)
            except Exception as exc:
                records.append(
                    {
                        "engine": label,
                        "case": name,
                        "synthetic_edit": edit,
                        "wall_seconds": time.perf_counter() - started,
                        "failure": getattr(exc, "code", type(exc).__name__),
                    }
                )
                print(label, name, "FAILED", records[-1]["failure"], flush=True)
            write(destination / "native.json", records)
        models.close()
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--checkpoint-sha256")
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to(EP_ROOT) or destination == EP_ROOT:
        raise ValueError("Reports must remain in a dedicated directory below ep/")
    destination.mkdir(parents=True, exist_ok=False)
    import torch

    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    torch.manual_seed(0)
    torch.cuda.reset_peak_memory_stats()
    config = V3Config(
        learned_matcher="loftr" if args.checkpoint else "disabled",
        checkpoint=args.checkpoint,
        checkpoint_sha256=args.checkpoint_sha256,
        compare_matchers=True,
    )
    with worker_guard():
        summary = {
            "date_local": "2026-11-10",
            "seed": 0,
            "versions": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "opencv": cv2.__version__,
                "gpu": torch.cuda.get_device_name(),
            },
            "config": config.model_dump(mode="json"),
            "source_sha256": {
                str(path.relative_to(EP_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for folder in ("ep_engine/cv", "ep_engine/v3")
                for path in sorted((EP_ROOT / folder).glob("*.py"))
            },
            "quality": quality_audit(destination),
        }
        kernels = kernel_benchmark(destination, config)
        summary["kernels"] = kernels
        records = []
        if args.native:
            records = native_benchmark(destination, config)
            summary["native_cases"] = len(records)
            summary["native_failures"] = [row for row in records if "failure" in row]
        memory = psutil.Process().memory_info()
        summary["peak_working_set_bytes"] = getattr(memory, "peak_wset", memory.rss)
        for field, current in (
            ("peak_cuda_allocated_bytes", torch.cuda.max_memory_allocated()),
            ("peak_cuda_reserved_bytes", torch.cuda.max_memory_reserved()),
        ):
            # NativeModels resets Torch peaks at lifecycle boundaries. Preserve the
            # largest observation across phases rather than reporting only the last one.
            summary[field] = max(
                current,
                kernels[field],
                *(row.get("result", {}).get("metrics", {}).get(field, 0) for row in records),
            )
        summary["payment_action"] = "none"
        summary["physical_damage_accuracy"] = None
        write(destination / "summary.json", summary)
    print("Report:", destination / "summary.json", flush=True)


if __name__ == "__main__":
    main()
