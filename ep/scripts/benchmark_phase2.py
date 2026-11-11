"""Native end-to-end smoke benchmark; photographic derivatives, not damage ground truth."""

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from ep_engine.config import Settings
from ep_engine.core.security import Grant, LocalAuthorization
from ep_engine.main import create_app


def encode(array):
    stream = io.BytesIO()
    Image.fromarray(array).save(stream, format="PNG")
    return stream.getvalue()


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / ".test-artifacts" / "phase2-benchmark"
    destination.mkdir(exist_ok=True)
    source = Path(sys.prefix) / "Lib/site-packages/ultralytics/assets/bus.jpg"
    with Image.open(source) as photo:
        image = photo.convert("RGB")
        image.thumbnail((768, 768))
        base = np.array(image)
    changed = base.copy()
    # A synthetic appearance perturbation, not a labeled physical scratch/crack/dent.
    changed[220:245, 250:300] = (220, 20, 20)
    matrix = np.array([[1, 0.012, -3], [0.008, 1, -2], [0.00003, 0.00001, 1]], np.float64)
    perspective = cv2.warpPerspective(base, matrix, (base.shape[1], base.shape[0]))
    cases = {
        "unchanged_photo": base,
        "synthetic_appearance_edit": changed,
        "synthetic_perspective": perspective,
        "unusable_blur": cv2.GaussianBlur(base, (71, 71), 25),
        "insufficient_texture": np.full_like(base, 128),
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=list(cases))
    selected = parser.parse_args().case
    if selected:
        cases = {selected: cases[selected]}
    authorization = LocalAuthorization(
        {
            "benchmark-local-lender": Grant(
                subject="smoke-lender", rentals={"smoke-rental": "lender"}
            ),
            "benchmark-local-borrower": Grant(
                subject="smoke-borrower", rentals={"smoke-rental": "borrower"}
            ),
        }
    )
    app = create_app(Settings(data_dir=destination / "private"), authorization=authorization)
    records = []
    manifest = []
    predictions = []
    (destination / "before.png").write_bytes(encode(base))
    target = {"x1": 0.03, "y1": 0.20, "x2": 0.99, "y2": 0.72}
    with TestClient(app) as client:
        before = client.post(
            "/v1/evidence?rental_id=smoke-rental&stage=before",
            content=encode(base),
            headers={"Authorization": "Bearer benchmark-local-lender"},
        ).json()
        for name, after_image in cases.items():
            (destination / f"{name}.png").write_bytes(encode(after_image))
            after = client.post(
                "/v1/evidence?rental_id=smoke-rental&stage=after",
                content=encode(after_image),
                headers={"Authorization": "Bearer benchmark-local-borrower"},
            ).json()
            headers = {"Authorization": "Bearer benchmark-local-lender"}
            inspection = client.post(
                "/v1/inspections",
                json={
                    "rental_id": "smoke-rental",
                    "reference_ids": [before["id"]],
                    "return_ids": [after["id"]],
                },
                headers=headers,
            ).json()
            run = client.post(
                f"/v1/inspections/{inspection['id']}/cv-runs",
                json={"targets": {before["id"]: target, after["id"]: target}},
                headers=headers,
            ).json()
            started = time.perf_counter()
            package = app.state.cv.execute(
                run["id"], authorization.authenticate(headers["Authorization"])
            )
            # Verify the API and private attachment retrieval after actual subprocess inference.
            response = client.get(f"/v1/cv-runs/{run['id']}/result", headers=headers)
            if response.status_code != 200 or (
                package.artifacts
                and client.get(
                    f"/v1/cv-runs/{run['id']}/artifacts/{package.artifacts[0].id}", headers=headers
                ).status_code
                != 200
            ):
                raise RuntimeError("End-to-end artifact/API verification failed")
            report = {
                "case_id": name,
                "run_id": run["id"],
                "inspection_id": inspection["id"],
                "outcome": package.outcome,
                "candidate_count": len(package.candidates),
                "artifact_count": len(package.artifacts),
                "wall_seconds": time.perf_counter() - started,
                "metrics": package.metrics,
                "pairs": [row.model_dump(mode="json") for row in package.pairs],
                "quality": [row.model_dump(mode="json") for row in package.quality],
                "ground_truth": None,
            }
            (destination / f"{name}-package.json").write_text(
                package.model_dump_json(indent=2), encoding="utf-8"
            )
            records.append(report)
            manifest.append(
                {
                    "schema_version": "2.0",
                    "case_id": name,
                    "object_instance_group": "bundled-bus-single-source",
                    "split": "smoke",
                    "scenario_tags": [name],
                    "annotation_status": "unlabelled",
                    "labels": None,
                    "provenance": "Local bundled photograph and documented synthetic derivatives",
                    "views": [
                        {
                            "path": filename,
                            "sha256": hashlib.sha256(
                                (destination / filename).read_bytes()
                            ).hexdigest(),
                        }
                        for filename in ("before.png", f"{name}.png")
                    ],
                }
            )
            comparable = package.outcome in ("comparable", "partially_comparable")
            predictions.append(
                {
                    "case_id": name,
                    "identity_consistent": True if comparable else None,
                    "viewpoint_comparable": True if comparable else None,
                    "change_present": bool(package.candidates) if comparable else None,
                }
            )
            print(json.dumps(report), flush=True)
    report = {
        "source": {
            "origin": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "provenance": (
                "Existing Ultralytics 8.4.132 bundled photograph, used locally only; "
                "no additional image downloads"
            ),
            "limitations": (
                "Single photographic source with synthetic derivatives. No independently "
                "captured angle/damage or verified physical identity labels. "
                "Not an accuracy dataset."
            ),
        },
        "cases": records,
        "accuracy_status": "blocked_no_independent_labels",
    }
    (destination / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (destination / "manifest.json").write_text(
        json.dumps({"cases": manifest}, indent=2), encoding="utf-8"
    )
    (destination / "predictions.json").write_text(
        json.dumps({"predictions": predictions}, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
