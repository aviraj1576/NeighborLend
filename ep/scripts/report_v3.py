"""Build a private, local gallery and comparison summary from actual v3 benchmark outputs."""

import argparse
import hashlib
import html
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.config import EP_ROOT
from ep_engine.cv.assets import verify_store


def read(path):
    return json.loads(path.read_text("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--kernels", required=True, type=Path)
    args = parser.parse_args()
    native, kernels = args.native.resolve(), args.kernels.resolve()
    if not all(path.is_relative_to(EP_ROOT) and path != EP_ROOT for path in (native, kernels)):
        raise ValueError("Use private EP benchmark directories")
    rows, timing = read(native / "native.json"), read(kernels / "kernels.json")
    summary, sections = [], []
    for row in rows:
        result = row.get("result", {})
        pairs = result.get("pairs", [])
        summary.append(
            {
                "engine": row["engine"],
                "case": row["case"],
                "outcome": result.get("outcome"),
                "appearance_proposals": len(result.get("candidates", [])),
                "boundary_hypotheses": len(result.get("boundary_changes", [])),
                "quality": [q["status"] for q in result.get("quality", [])],
                "segmentation": [q["status"] for q in result.get("segmentation", [])],
                "geometry": [
                    {
                        key: pair[key]
                        for key in (
                            "method",
                            "cosine_similarity",
                            "matches",
                            "inliers",
                            "inlier_ratio",
                            "source_coverage",
                            "target_coverage",
                            "symmetric_reprojection_error",
                            "alignment_status",
                            "reasons",
                        )
                    }
                    for pair in pairs
                ],
                "wall_seconds": row["wall_seconds"],
                "failure": row.get("failure"),
                "synthetic_edit": row.get("synthetic_edit"),
                "physical_damage_label": None,
            }
        )
        case, engine = row["case"], row["engine"]
        title = html.escape(f"{engine}: {case} — {result.get('outcome', 'failed')}")
        images = []
        manifest = read(native / "sources" / case / f"{engine}-input.json")

        def figure(path, label):
            path = path.resolve()
            if not path.is_relative_to(native):
                raise ValueError("Gallery image escaped benchmark directory")
            url = html.escape(path.relative_to(native).as_posix(), quote=True)
            return (
                f'<figure><a href="{url}"><img loading="lazy" src="{url}"></a>'
                f"<figcaption>{html.escape(label)}</figcaption></figure>"
            )

        for source in manifest["evidence"]:
            images.append(figure(Path(source["path"]), source["stage"]))
        for artifact in result.get("artifacts", []):
            if artifact["kind"] in {
                "object_mask",
                "feature_matches",
                "alignment_overlay",
                "candidate_overlay",
                "boundary_overlay",
                "difference_map",
            }:
                path = native / engine / case / (artifact["id"] + ".png")
                if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                    raise ValueError("Gallery artifact integrity mismatch")
                images.append(figure(path, artifact["kind"]))
        details = html.escape(json.dumps(summary[-1], indent=2))
        sections.append(
            f'<section><h2>{title}</h2><div class="images">{"".join(images)}</div>'
            f"<details><summary>Measured stages and geometry</summary><pre>{details}</pre>"
            "</details></section>"
        )
    report = {
        "cases": summary,
        "wall_median_seconds": {
            engine: statistics.median(
                row["wall_seconds"] for row in rows if row["engine"] == engine
            )
            for engine in ("baseline", "v3")
        },
        "kernels": timing,
        "physical_damage_accuracy": None,
        "payment_action": "none",
        "human_review_required": True,
        "reviewed_source_sha256": {
            str(path.relative_to(EP_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ("ep_engine/cv", "ep_engine/v3")
            for path in sorted((EP_ROOT / folder).glob("*.py"))
        },
    }
    (native / "comparison-summary.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    page = (
        '<!doctype html><meta charset="utf-8"><title>EP v3 private comparison</title>'
        "<style>body{font:16px system-ui;max-width:1400px;margin:30px auto;padding:20px}"
        ".images{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;width:250px}"
        "img{width:250px;height:220px;object-fit:contain;background:#eee}"
        "section{border-top:1px solid #bbb;margin-top:30px}pre{overflow:auto}</style>"
        "<h1>EP v3: actual baseline and v3 evidence</h1>"
        "<p>Private local technical controls. Synthetic edits are not verified physical damage. "
        "Abstention is not successful detection. Every result requires human review; "
        "payment_action=none.</p>" + "".join(sections)
    )
    (native / "index.html").write_text(page, encoding="utf-8")
    previous = EP_ROOT / ".test-artifacts/final-comparison-20261110-01/inventory.json"
    inventory = read(previous) if previous.is_file() else []
    unchanged = (
        all(
            hashlib.sha256((EP_ROOT / "test_images" / row["filename"]).read_bytes()).hexdigest()
            == row["sha256"]
            for row in inventory
        )
        if inventory
        else None
    )
    receipt = verify_store()
    integrity = {
        "original_images_checked": len(inventory),
        "all_original_images_unchanged": unchanged,
        "existing_model_store_verified_files": len(receipt["files"]),
    }
    (native / "integrity.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    if unchanged is False:
        raise ValueError("Source images differ from the preserved pre-v3 inventory")
    print(native / "index.html")


if __name__ == "__main__":
    main()
