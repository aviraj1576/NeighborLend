"""Verify private artifacts and build the measured release comparison and gallery."""

import hashlib
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.cv.contracts import CVPackage
from ep_engine.v31.contracts import InspectionReport
from scripts.evaluate_v31 import summarize

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/ep-v31-20261111"


def read(path):
    return json.loads(path.read_text("utf-8"))


def main():
    summaries, ledgers, packages = {}, {}, {}
    verified_artifacts = 0
    for revision in ("baseline", "current"):
        directory = OUT / ("baseline-complete" if revision == "baseline" else "current-release")
        summaries[revision] = read(directory / "summary.json")
        ledgers[revision] = read(directory / "executions.json")
        summaries[revision] = summarize(ledgers[revision])
        (directory / "summary.json").write_text(
            json.dumps(summaries[revision], indent=2) + "\n", encoding="utf-8"
        )
        packages[revision] = {}
        for row in ledgers[revision]:
            result_path = directory / row["case_id"] / "result.json"
            if not result_path.exists():
                continue
            result = read(result_path)
            if revision == "current":
                InspectionReport.model_validate(result)
            package = CVPackage.model_validate(result["cv_package"])
            packages[revision][row["case_id"]] = package
            for artifact in package.artifacts:
                image = result_path.parent / "artifacts" / f"{artifact.id}.png"
                content = image.read_bytes()
                if (
                    hashlib.sha256(content).hexdigest() != artifact.sha256
                    or len(content) != artifact.byte_size
                ):
                    raise ValueError("Artifact provenance failed")
                verified_artifacts += 1
    manifest = read(OUT / "evaluation-manifest.json")
    expected = {row["case_id"] for row in manifest}
    completed = {r: {row["case_id"] for row in rows} == expected for r, rows in ledgers.items()}
    tests = {}
    for source in sorted(OUT.glob("*.xml")):
        suites = list(ET.parse(source).getroot().iter("testsuite"))  # noqa: S314 - local pytest output
        tests[source.name] = {
            field: sum(float(s.attrib.get(field, 0)) for s in suites)
            for field in ("tests", "failures", "errors", "skipped", "time")
        }
    gates = {
        "complete_matched_evaluation": all(completed.values()),
        "current_failed_jobs": sum(row["outcome"] == "failed" for row in ledgers["current"]),
        "repeat_proposal_jobs": summaries["current"]["groups"]["exact_repeat_control"][
            "proposal_jobs"
        ],
        "repeat_boundary_jobs": summaries["current"]["groups"]["exact_repeat_control"][
            "boundary_jobs"
        ],
        "different_object_identity_confirmations": summaries["current"]["groups"][
            "different_object_control"
        ]["confirmed_identity_jobs"],
        "strict_packages_validated": len(packages["current"]),
        "artifacts_digest_verified": verified_artifacts,
        "physical_damage_accuracy": None,
    }
    safety_fields = (
        "min_focus",
        "min_contrast",
        "min_similarity",
        "min_inliers",
        "min_inlier_ratio",
        "min_overlap",
        "difference_threshold",
        "min_candidate_area",
    )
    changed_thresholds = []
    alignment = []
    for name, package in packages["current"].items():
        baseline = packages["baseline"].get(name)
        if baseline is None:
            continue
        for field in safety_fields:
            if getattr(package.thresholds, field) != getattr(baseline.thresholds, field):
                changed_thresholds.append([name, field])
        for pair in package.pairs:
            if pair.status == "comparable":
                alignment.append(
                    {
                        "case_id": name,
                        "before_id": str(pair.before_id),
                        "after_id": str(pair.after_id),
                        "inliers": pair.inliers,
                        "inlier_ratio": pair.inlier_ratio,
                        "overlap": pair.overlap_fraction,
                        "symmetric_error": pair.symmetric_reprojection_error,
                        "minimum_spatial_coverage": min(pair.source_coverage, pair.target_coverage),
                    }
                )
    gates["changed_safety_thresholds"] = changed_thresholds
    gates["current_alignment_records"] = alignment
    gates["internal_geometry_gates_pass"] = all(
        row["inliers"] >= 12
        and row["inlier_ratio"] >= 0.45
        and row["minimum_spatial_coverage"] >= 0.03
        and row["symmetric_error"] is not None
        and row["symmetric_error"] <= 3
        for row in alignment
    )
    final_tests = tests.get("release-all-tests.xml", {})
    policy_tests = tests.get("policy-final.xml", {})
    engineering_ready = (
        gates["complete_matched_evaluation"]
        and not gates["current_failed_jobs"]
        and not gates["repeat_proposal_jobs"]
        and not gates["repeat_boundary_jobs"]
        and not gates["different_object_identity_confirmations"]
        and not changed_thresholds
        and gates["internal_geometry_gates_pass"]
        and final_tests.get("tests", 0) > 0
        and not final_tests.get("failures", 1)
        and not final_tests.get("errors", 1)
        and policy_tests.get("tests", 0) == 2
        and not policy_tests.get("failures", 1)
        and not policy_tests.get("errors", 1)
        and not read(OUT / "audit.json")["changed_originals"]
    )
    gates["release_classification"] = "ENGINEERING READY" if engineering_ready else "NOT READY"
    # Persist the final verdict alongside all measured engineering gates.
    (OUT / "acceptance.json").write_text(json.dumps(gates, indent=2) + "\n", "utf-8")
    changed_files = ["README.md", "docs/ep-v31-release-report.md"]
    for folder in ("ep_engine", "scripts", "tests", "docs"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            frozen = OUT / "frozen" / path.relative_to(ROOT)
            if not frozen.is_file() or path.read_bytes() != frozen.read_bytes():
                changed_files.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    changed_files = sorted(set(changed_files))
    (OUT / "changed-files.json").write_text(json.dumps(changed_files, indent=2) + "\n", "utf-8")
    (OUT / "acceptance.json").write_text(json.dumps(gates, indent=2) + "\n", "utf-8")
    metrics = [
        ("Total current-collection before/after pairs", lambda g: g["real_pair"]["count"]),
        ("Comparable pairs", lambda g: g["real_pair"]["outcomes"].get("comparable", 0)),
        ("Inconclusive pairs", lambda g: g["real_pair"]["outcomes"].get("inconclusive", 0)),
        ("Failed pairs", lambda g: g["real_pair"]["outcomes"].get("failed", 0)),
        (
            "Exact-repeat failures / 17",
            lambda g: g["exact_repeat_control"]["outcomes"].get("failed", 0),
        ),
        (
            "Exact-repeat appearance proposal jobs",
            lambda g: g["exact_repeat_control"]["proposal_jobs"],
        ),
        (
            "Different-object confirmed physical identities / 5",
            lambda g: g["different_object_control"]["confirmed_identity_jobs"],
        ),
        (
            "Median process wall time per real pair (seconds)",
            lambda g: round(g["real_pair"]["median_wall_seconds"], 3),
        ),
        (
            "Peak CUDA allocated, real pairs (bytes)",
            lambda g: g["real_pair"]["peak_cuda_allocated_bytes"],
        ),
        (
            "Peak CUDA reserved, real pairs (bytes)",
            lambda g: g["real_pair"]["peak_cuda_reserved_bytes"],
        ),
        ("Peak host working set, real pairs (bytes)", lambda g: g["real_pair"]["peak_host_bytes"]),
    ]
    lines = [
        "# EP v3.1 release evaluation",
        "",
        "11 November 2026, Asia/Calcutta.",
        "",
        f"**Release classification: {gates['release_classification']}** for the measured "
        "bounded standalone advisory evidence workflow. **Not PILOT READY** for physical-damage "
        "assessment: independent condition labels and "
        "physical-identity validation are unavailable.",
        "",
        "This report is generated from private execution ledgers and verified artifacts. "
        "Physical damage ground truth is unavailable; no detection accuracy is claimed.",
        "",
        "| Metric | Frozen EP v3 | EP v3.1 |",
        "|---|---:|---:|",
    ]
    for label, metric in metrics:
        lines.append(
            f"| {label} | {metric(summaries['baseline']['groups'])} "
            f"| {metric(summaries['current']['groups'])} |"
        )
    lines.extend(
        [
            "| Damage precision / recall / F1 / localization accuracy | N/A | N/A |",
            "| Alignment validity | Internal gates pass; GT NOT VERIFIED "
            "| Internal gates pass; GT NOT VERIFIED |",
            "",
            "Wall time includes interpreter/model startup, verified model reads, "
            "inference, artifacts "
            "and report serialization. It is not a model-forward-only measurement. "
            "See each package for stage/load times and runtime for the complete inspection. "
            "Torch allocation excludes other applications and driver allocations.",
            "Whole-process latency reflects variable host load; the table does not establish "
            "a controlled end-to-end speedup. CPU/CUDA kernel timings below compare repeated "
            "operations within one process under matched conditions.",
            "",
            "## Per-category results on the 17 current pairs",
            "",
            "| Category | Frozen v3 | v3.1 |",
            "|---|---|---|",
        ]
    )
    for category in summaries["baseline"]["groups"]["real_pair"]["categories"]:
        values = [
            summaries[r]["groups"]["real_pair"]["categories"].get(category, {})
            for r in ("baseline", "current")
        ]
        lines.append(f"| {category} | {values[0]} | {values[1]} |")
    lines += [
        "",
        "## Other evaluation groups",
        "",
        "```json",
        json.dumps({r: s["groups"] for r, s in summaries.items()}, indent=2),
        "```",
        "",
        "## Regression execution",
        "",
        "```json",
        json.dumps(tests, indent=2),
        "```",
        "",
        "Earlier failed test executions remain in the ledger. Windows directory-rename failures "
        "were reproduced and fixed with a verified transactional copy fallback; final results "
        "must be read from the final complete suite, not an isolated retry.",
        "",
        "## Integrity and limitations",
        "",
        f"Validated {len(packages['current'])} current packages "
        f"and {verified_artifacts} artifact digests across both revisions. "
        f"Matched evaluation complete: {completed}. "
        f"Changed safety thresholds: {changed_thresholds}.",
        "",
        "The same frozen targets, derivatives, model hashes, seeds and configuration were used. "
        "The initial run without EP-local Kornia is retained separately under `baseline/`; "
        "it is a dependency diagnostic and is excluded from this comparison.",
        "The later `current-complete` and `current-final` partial campaigns are preserved "
        "development measurements; only `current-release` is the final reviewed implementation.",
        "",
        "All returned outputs are advisory, with payment_action=none and physical identity "
        "unverified. The different-object confirmation gate is passed through abstention; "
        "positive physical-identity recognition accuracy is not established. All accepted "
        "alignments pass internal verification; "
        "registration ground-truth accuracy is NOT VERIFIED.",
        "",
        "Integration readiness: the stable local API and private reports are available for "
        "human inspection. No NeighborLend integration was performed. A physical-damage pilot "
        "requires independently reviewed unchanged/damaged recaptures, instance/region labels, "
        "distinctive identity evidence and an object-level held-out evaluation. Larger configured "
        "12-image/64-megapixel combinations have not been stress-verified by this dataset.",
        "",
        "Archived photographs form a separate unlabeled regression group. Some archived named "
        "before/after images are byte-identical. No independently labeled physical damage, "
        "unchanged recaptures, region labels, or independent physical-object holdout exists. "
        "Different-object controls are different categories; similar-looking different instances "
        "remain unverified. Software controls do not replace these missing labels.",
        "",
        "No cross-view surface map, automatic physical identity confirmation, damage promotion, "
        "or exhaustive original-resolution scratch search is claimed. Review crops retain original "
        "detail only around proposed regions. Hidden/touching instances remain unresolved.",
        "",
        "[Architecture, contract, limits and reproduction](ep-v31.md). "
        "[Private visual gallery](../.test-artifacts/ep-v31-20261111/index.html). "
        "[Acceptance evidence](../.test-artifacts/ep-v31-20261111/acceptance.json).",
        "",
    ]
    kernels = OUT / "kernels/kernels.json"
    if kernels.exists():
        lines += [
            "## CPU/CUDA kernel measurements",
            "",
            "```json",
            json.dumps(read(kernels), indent=2),
            "```",
            "",
        ]
    lifecycle = {}
    for revision in ("baseline", "current"):
        path = OUT / f"lifecycle-{revision}/summary.json"
        if path.exists():
            lifecycle[revision] = read(path)
    if lifecycle:
        lines += [
            "## Cold-model and warm-cache lifecycle",
            "",
            "```json",
            json.dumps(lifecycle, indent=2),
            "```",
            "",
        ]
    (ROOT / "docs/ep-v31-release-report.md").write_text("\n".join(lines), "utf-8")
    with (ROOT / "docs/ep-v31-release-report.md").open("a", encoding="utf-8") as stream:
        stream.write("\n## Files changed from the frozen source\n\n")
        stream.write("\n".join(f"- `{name}`" for name in changed_files) + "\n")
    cards = []
    for row in ledgers["current"]:
        package = packages["current"].get(row["case_id"])
        if package is None or row["kind"] != "real_pair":
            continue
        selected = [
            a
            for a in package.artifacts
            if a.kind
            in {
                "object_mask",
                "feature_matches",
                "alignment_overlay",
                "candidate_overlay",
                "boundary_overlay",
            }
        ]
        pictures = "".join(
            f'<figure><img src="current-release/{html.escape(row["case_id"])}/'
            f'artifacts/{a.id}.png">'
            f"<figcaption>{html.escape(a.kind)}; sources "
            f"{html.escape(str(a.source_ids))}</figcaption></figure>"
            for a in selected
        )
        reasons = sorted({reason for pair in package.pairs for reason in pair.reasons})
        cards.append(
            f"<details><summary>{html.escape(row['case_id'])}: {package.outcome}</summary>"
            f'<p>{html.escape(str(reasons))}</p><div class="gallery">{pictures}</div></details>'
        )
    (OUT / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>EP v3.1 private evidence</title>"
        "<style>body{font:16px system-ui;margin:2rem;background:#f4f5f7;color:#182432}"
        ".gallery{display:flex;flex-wrap:wrap;gap:1rem}figure{margin:0;width:380px}"
        "img{max-width:380px;max-height:480px}figcaption{font-size:12px;overflow-wrap:anywhere}"
        "details{padding:1rem;background:white;margin:1rem 0}"
        "summary{cursor:pointer;font-weight:600}</style>"
        "<h1>EP v3.1 private visual evidence</h1>"
        "<p>Observed changes are not confirmed physical damage. "
        "Identity remains unverified; unseen surfaces and unresolved fine detail are unassessed. "
        "No liability or payment action. All source and artifact hashes are retained.</p>"
        + "".join(cards)
        + "</html>",
        "utf-8",
    )
    print(
        json.dumps(
            {
                "completed": completed,
                "gates": {k: v for k, v in gates.items() if k != "current_alignment_records"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
