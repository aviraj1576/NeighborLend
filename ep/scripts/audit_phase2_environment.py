"""Read-only package/operator audit; no pretrained loading, downloads or installations."""

import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    artifacts = ROOT / ".test-artifacts" / "phase-2-baseline"
    artifacts.mkdir(parents=True, exist_ok=True)
    for variable, folder in {
        "TORCH_HOME": "torch",
        "HF_HOME": "huggingface",
        "XDG_CACHE_HOME": "cache",
        "CUDA_CACHE_PATH": "cuda-cache",
        "TORCH_EXTENSIONS_DIR": "torch-extensions",
        "TORCHINDUCTOR_CACHE_DIR": "torch-inductor",
        "TRITON_CACHE_DIR": "triton-cache",
        "TMP": "tmp",
        "TEMP": "tmp",
        "TMPDIR": "tmp",
    }.items():
        target = artifacts / folder
        target.mkdir(exist_ok=True)
        os.environ[variable] = str(target)
    packages = (
        "torch",
        "torchvision",
        "ultralytics",
        "opencv-python",
        "Pillow",
        "numpy",
        "fastapi",
        "pydantic",
        "pytest",
        "pytest-cov",
        "coverage",
        "httpx",
        "ruff",
        "uvicorn",
        "scikit-image",
        "transformers",
        "timm",
        "sam2",
        "segment-anything",
        "efficient-sam",
        "safetensors",
        "huggingface-hub",
        "psutil",
        "omegaconf",
        "xformers",
        "iopath",
    )
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    report = {
        "interpreter": sys.executable,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": versions,
        "operators": {},
        "cuda": {},
    }
    import cv2
    import numpy as np
    import torch
    import torchvision

    report["opencv"] = {
        "runtime_version": cv2.__version__,
        "sift_available": hasattr(cv2, "SIFT_create"),
        "orb_available": hasattr(cv2, "ORB_create"),
        "ssim_quality_module": hasattr(cv2, "quality"),
        "decode_smoke_shape": list(
            cv2.cvtColor(np.zeros((8, 8, 3), dtype=np.uint8), cv2.COLOR_RGB2GRAY).shape
        ),
    }
    boxes = torch.tensor([[0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 1.0, 1.0]])
    scores = torch.tensor([0.9, 0.8])
    report["operators"]["torchvision_nms_cpu"] = torchvision.ops.nms(boxes, scores, 0.5).tolist()
    report["cuda"] = {"available": torch.cuda.is_available(), "runtime": torch.version.cuda}
    if torch.cuda.is_available():
        report["operators"]["torchvision_nms_cuda"] = (
            torchvision.ops.nms(boxes.cuda(), scores.cuda(), 0.5).cpu().tolist()
        )
        report["cuda"].update(
            name=torch.cuda.get_device_name(0),
            free_bytes=torch.cuda.mem_get_info(0)[0],
            total_bytes=torch.cuda.mem_get_info(0)[1],
        )
    try:
        import psutil

        memory = psutil.virtual_memory()
        report["ram"] = {"total_bytes": memory.total, "available_bytes": memory.available}
    except ImportError:
        report["ram"] = {"status": "psutil unavailable"}
    (artifacts / "environment.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
