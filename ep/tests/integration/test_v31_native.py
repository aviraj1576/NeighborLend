"""Actual standalone launcher/worker contract using generated pixels and local models."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from ep_engine.v31.contracts import InspectionReport


@pytest.mark.real_inference
@pytest.mark.controlled_inference
@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_standalone_v31_native_launcher_and_private_schema(tmp_path, device):
    if os.environ.get("EP_RUN_CONTROLLED_CV") != "1":
        pytest.skip("Explicit controlled native execution required")
    root = Path(__file__).resolve().parents[2]
    before = np.full((256, 256, 3), 230, np.uint8)
    before[48:208, 48:208] = np.random.default_rng(42).integers(30, 170, (160, 160, 3), np.uint8)
    after = before.copy()
    after[105:135, 110:140] = 0
    evidence = []
    for stage, rgb in (("before", before), ("after", after)):
        key = uuid4()
        path = tmp_path / f"{key}.png"
        Image.fromarray(rgb).save(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        evidence.append(
            {
                "id": str(key),
                "path": str(path),
                "stage": stage,
                "sha256": digest,
                "normalized_sha256": digest,
                "target": {"x1": 0.16, "y1": 0.16, "x2": 0.84, "y2": 0.84},
            }
        )
    manifest = tmp_path / "request.json"
    manifest.write_text(
        json.dumps(
            {
                "inspection_id": str(uuid4()),
                "evidence": evidence,
                "config": {"device": device, "max_side": 256},
                "high_resolution_crops": 0,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "result"
    execution = subprocess.run(  # noqa: S603 - fixed local interpreter/launcher; no shell
        [
            sys.executable,
            "-B",
            str(root / "scripts/run_v31.py"),
            str(manifest),
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert execution.returncode == 0, execution.stderr + (output / "worker.log").read_text("utf-8")
    report = InspectionReport.model_validate_json((output / "result.json").read_text("utf-8"))
    assert report.cv_package.outcome == "comparable"
    assert report.cv_package.candidates
    assert report.runtime["device"] == device
    assert report.schema_version == "3.1" and report.payment_action == "none"
    assert not report.physical_identity_verified and not report.possible_damage_hypotheses
    for artifact in report.cv_package.artifacts:
        data = (output / "artifacts" / f"{artifact.id}.png").read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact.sha256
