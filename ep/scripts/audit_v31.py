"""Read-only provenance and environment audit; writes only private release evidence."""

import hashlib
import importlib.metadata
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / ".runtime/v3-packages"))

import numpy as np
import psutil
import torch
from PIL import Image

from ep_engine.cv import assets
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.quality import assess_quality
from ep_engine.v31.contracts import InspectionFailure, InspectionReport, InspectionRequest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/ep-v31-20261111"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    checksums = json.loads((OUT / "dataset-checksums.json").read_text("utf-8-sig"))
    changed = [row["Path"] for row in checksums if digest(Path(row["Path"])) != row["Hash"].lower()]
    inventories = {}
    historical_images = []
    for directory in sorted((ROOT / ".test-artifacts").iterdir()):
        if directory == OUT or not directory.is_dir():
            continue
        manifest = directory / "inventory.json"
        if manifest.is_file():
            content = json.loads(manifest.read_text("utf-8-sig"))
            inventories[directory.name] = {
                "manifest_sha256": digest(manifest),
                "records": len(content),
                "has_independent_condition_labels": False,
            }
            for row in content:
                if not isinstance(row, dict) or not row.get("path") or not row.get("id"):
                    continue
                source = Path(row["path"])
                if not source.is_file() or not source.resolve().is_relative_to(ROOT):
                    continue
                if digest(source) != row["normalized_sha256"]:
                    raise ValueError("Historical derivative integrity failed")
                with Image.open(source) as image:
                    if image.width * image.height > 16_000_000:
                        raise ValueError("Historical derivative exceeds pixel bound")
                    image = image.convert("RGB")
                    image.thumbnail((768, 768))
                    quality = assess_quality(UUID(row["id"]), np.asarray(image), CVConfig())
                historical_images.append(
                    {
                        "collection": directory.name,
                        "filename": row.get("filename"),
                        "sha256": row["sha256"],
                        "normalized_sha256": row["normalized_sha256"],
                        "quality": quality.model_dump(mode="json"),
                    }
                )
    (OUT / "historical-image-quality.json").write_text(
        json.dumps(historical_images, indent=2) + "\n", encoding="utf-8"
    )
    for name, record in inventories.items():
        record["rechecked_derivatives"] = dict(
            Counter(
                row["quality"]["status"] for row in historical_images if row["collection"] == name
            )
        )
    audit = {
        "date_local": "2026-11-11",
        "timezone": "Asia/Calcutta",
        "os": platform.platform(),
        "python": sys.version,
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "numpy",
                "opencv-python",
                "Pillow",
                "psutil",
                "pydantic",
                "pytest",
                "kornia",
                "kornia_rs",
            )
        },
        "hardware": {
            "gpu": torch.cuda.get_device_name(0),
            "vram_bytes": torch.cuda.get_device_properties(0).total_memory,
            "host_ram_bytes": psutil.virtual_memory().total,
            "logical_cpu_count": psutil.cpu_count(),
        },
        "verified_model_store": assets.verify_store(),
        "loftr_sha256": digest(ROOT / ".runtime/v3-models/loftr_outdoor.ckpt"),
        "dataset_images": len(checksums),
        "changed_originals": changed,
        "discovered_historical_inventories": inventories,
        "current_source_sha256": {
            str(path.relative_to(ROOT)): digest(path) for path in (ROOT / "ep_engine").rglob("*.py")
        },
        "frozen_source_sha256": {
            str(path.relative_to(OUT / "frozen")): digest(path)
            for path in (OUT / "frozen/ep_engine").rglob("*.py")
        },
        "financial_authority": "none",
        "external_service_calls": 0,
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    for name, contract in (
        ("request", InspectionRequest),
        ("report", InspectionReport),
        ("failure", InspectionFailure),
    ):
        (ROOT / f"docs/ep-v31-{name}.schema.json").write_text(
            json.dumps(contract.model_json_schema(), indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "originals_checked": len(checksums),
                "changed": changed,
                "historical_inventories": inventories,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
