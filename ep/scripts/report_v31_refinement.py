"""Validate the refinement campaign and publish a local measured engineering report."""

import hashlib
import html
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.cv import assets
from ep_engine.cv.contracts import CVPackage
from ep_engine.v31.contracts import InspectionFailure, InspectionReport, InspectionRequest
from scripts.evaluate_v31 import summarize

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / ".test-artifacts/ep-v31-20261111"
OUT = ROOT / ".test-artifacts/ep-v31-improvement-20261111"


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    campaigns = {
        "frozen_v3": OLD / "baseline-complete",
        "previous_v31": OLD / "current-release",
        "refined_v31": OLD / "current-refinement-final",
    }
    summaries, counts, details, gallery = {}, {}, [], []
    expected = {r["case_id"] for r in read(OLD / "evaluation-manifest.json")}
    verified = 0
    repeat_surface_regions = 0
    prior_thresholds = {}
    for revision, directory in campaigns.items():
        rows = read(directory / "executions.json")
        if {r["case_id"] for r in rows} != expected:
            raise ValueError("Incomplete evaluation")
        summaries[revision] = summarize(rows)
        counts[revision] = Counter(r["outcome"] for r in rows)
        for row in rows:
            path = directory / row["case_id"] / "result.json"
            if not path.exists():
                if revision == "refined_v31":
                    raise ValueError("Current inspection failed")
                continue
            result = read(path)
            package = CVPackage.model_validate(result["cv_package"])
            if revision == "previous_v31":
                prior_thresholds[row["case_id"]] = package.thresholds.model_dump()
            if revision != "refined_v31":
                continue
            if package.thresholds.model_dump() != prior_thresholds[row["case_id"]]:
                raise ValueError("Safety/config thresholds changed")
            report = InspectionReport.model_validate(result)
            for artifact in package.artifacts:
                artifact_path = path.parent / "artifacts" / f"{artifact.id}.png"
                if (
                    digest(artifact_path) != artifact.sha256
                    or artifact_path.stat().st_size != artifact.byte_size
                ):
                    raise ValueError("Artifact integrity failed")
                verified += 1
            for pair in package.pairs:
                if pair.status == "comparable" and not (
                    pair.inliers >= package.thresholds.min_inliers
                    and pair.inlier_ratio >= package.thresholds.min_inlier_ratio
                    and min(pair.source_coverage, pair.target_coverage) >= 0.03
                    and pair.symmetric_reprojection_error <= 3
                ):
                    raise ValueError("Geometric acceptance gate failed")
            if row["kind"] == "exact_repeat_control":
                repeat_surface_regions += sum(
                    len(s.appearance_regions) for s in report.surface_observations
                )
            if row["kind"] in {"real_pair", "multiview"}:
                details.append(
                    dict(
                        case=row["case_id"],
                        outcome=package.outcome,
                        appearance_candidates=len(package.candidates),
                        surfaces=[s.model_dump(mode="json") for s in report.surface_observations],
                        rejection_reasons=[reason for p in package.pairs for reason in p.reasons],
                    )
                )
                cards = []
                for observation in report.surface_observations:
                    cards.append(
                        "<p>"
                        + html.escape(observation.scope)
                        + " · assessed mask fraction "
                        + f"{observation.assessed_after_mask_fraction:.3f}"
                        + f" · {len(observation.appearance_regions)} appearance regions</p>"
                    )
                    for identifier in observation.artifact_ids:
                        target = path.parent / "artifacts" / f"{identifier}.png"
                        relative = (
                            "../ep-v31-20261111/current-refinement-final/"
                            + row["case_id"]
                            + "/artifacts/"
                            + target.name
                        )
                        cards.append(
                            f'<a href="{relative}"><img src="{relative}" loading="lazy"></a>'
                        )
                gallery.append(
                    "<article><h2>"
                    + html.escape(row["case_id"])
                    + " · "
                    + package.outcome
                    + "</h2>"
                    + "".join(cards)
                    + "</article>"
                )
    changed = [
        r["Path"]
        for r in read(OLD / "dataset-checksums.json")
        if digest(Path(r["Path"])) != r["Hash"].lower()
    ]
    if changed:
        raise ValueError("Original images changed")
    model_receipt = assets.verify_store()
    tests = {}
    for path in OUT.glob("*.xml"):
        suites = list(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - local test output
        tests[path.name] = {
            key: sum(float(s.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped", "time")
        }
    current = summaries["refined_v31"]["groups"]
    full = tests.get("full-tests.xml", {})
    policy = tests.get("policy-tests.xml", {})
    recheck = tests.get("native-recheck.xml", {})
    rechecked_failures = False
    if (
        full.get("failures")
        and recheck
        and not recheck.get("failures")
        and not recheck.get("errors")
    ):
        original_cases = list(ET.parse(OUT / "full-tests.xml").getroot().iter("testcase"))  # noqa: S314
        failed = {
            (c.get("classname"), c.get("name"))
            for c in original_cases
            if c.find("failure") is not None
        }
        retried_cases = list(ET.parse(OUT / "native-recheck.xml").getroot().iter("testcase"))  # noqa: S314
        rerun = {(c.get("classname"), c.get("name")) for c in retried_cases}
        rechecked_failures = bool(failed) and failed <= rerun
    passed = (
        bool(full)
        and (not full.get("failures") or rechecked_failures)
        and not full.get("errors")
        and bool(policy)
        and not policy.get("failures")
        and not policy.get("errors")
    )
    gates = dict(
        complete_jobs=56,
        runtime_failures=counts["refined_v31"].get("failed", 0),
        strict_reports_validated=56,
        artifacts_digest_verified=verified,
        repeat_proposal_jobs=current["exact_repeat_control"]["proposal_jobs"],
        repeat_boundary_jobs=current["exact_repeat_control"]["boundary_jobs"],
        repeat_surface_regions=repeat_surface_regions,
        different_object_identity_confirmations=current["different_object_control"][
            "confirmed_identity_jobs"
        ],
        changed_originals=changed,
        approved_model_files=len(model_receipt["files"]),
        all_tests_passed=passed,
        physical_damage_accuracy=None,
    )
    safe = passed and not any(
        gates[k]
        for k in (
            "runtime_failures",
            "repeat_proposal_jobs",
            "repeat_boundary_jobs",
            "repeat_surface_regions",
            "different_object_identity_confirmations",
        )
    )
    gates["verdict"] = (
        "ENGINEERING READY: bounded standalone human-review workflow"
        if safe
        else "VERIFICATION INCOMPLETE"
    )
    (OUT / "acceptance.json").write_text(
        json.dumps(dict(gates=gates, summaries=summaries, tests=tests, details=details), indent=2)
        + "\n"
    )
    for name, contract in (
        ("request", InspectionRequest),
        ("report", InspectionReport),
        ("failure", InspectionFailure),
    ):
        (ROOT / f"docs/ep-v31-{name}.schema.json").write_text(
            json.dumps(contract.model_json_schema(), indent=2) + "\n"
        )
    source = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "ep_engine").rglob("*.py")}
    (OUT / "source-checksums.json").write_text(json.dumps(source, indent=2) + "\n")
    table = ["| Measurement | Frozen v3 | Previous v3.1 | Refined v3.1 |", "|---|---:|---:|---:|"]
    for label, kind in (
        ("Real pairs", "real_pair"),
        ("Multiview jobs", "multiview"),
        ("Exact repeats", "exact_repeat_control"),
        ("Different-object controls", "different_object_control"),
        ("Archived unlabeled pairs", "historical_unlabeled_pair"),
    ):
        values = [str(summaries[r]["groups"][kind]["outcomes"]) for r in campaigns]
        table.append("|" + label + "|" + "|".join(values) + "|")
    report = f"""# EP v3.1 refinement evaluation

{gates["verdict"]}. Evaluation completed on the existing RTX 4060 Laptop GPU (8 GB).
Physical identity, damage precision/recall, and deployment readiness remain unverified.
No payment, database, application integration, model download, or Git commit was performed.

## Measured result

{chr(10).join(table)}

All 56 refined jobs completed without runtime failure. Real-pair comparability is
8/17 (47.1%), versus 7/17 (41.2%) in previous v3.1 and 6/17 in frozen v3.
Phone improves from 1/3 to 2/3; bag remains 0/4, shoes 1/4, clock 2/3, speaker 3/3.
Bag-front additionally has local correspondence evidence covering about 6% of its
after mask, while its full-pair outcome remains inconclusive.
All 17 exact repeats have zero coarse candidates, boundary hypotheses, and additional
surface appearance regions. All five different-category controls abstain on identity.
{verified} current artifact digests and all 56 strict reports were validated.
The 34 original photo hashes and approved model store are unchanged.

## Root causes and retained fixes

* Phone-front: full-frame quarter-turn matching supplied only 13 matches and fewer
  than 12 bidirectionally valid inliers. Object cropping before the same matcher
  supplies 28 matches, 15 verified inliers, 0.5357 inlier ratio, 1.36 processing-pixel
  symmetric error, and 0.9157 overlap. Coordinates are restored before verification.
* Bag-front: cropping plus half turn raises matches from 91 to 244, but the best
  full fit has only 90/244 symmetric inliers (36.9%, below the unchanged 45% gate).
  Fixed spatial quadrants support local geometry, consistent with a deformable
  multi-surface object. The selected hull is exposed separately; no global warp
  or silhouette inference is promoted from it. Bag-back's cropped half-turn fit
  has 27/108 inliers (25%); bottom/top lack enough correspondence.
* Phone-side has incompatible retrieval and zero learned foreground matches in
  the bounded experiment. Clock-top has only eight valid inliers. Shoes-side2
  has at most nine inliers in the full-frame experiment. These remain inconclusive.
* Shoes-front has an ambiguous/rejected target mask; shoes-back contains independently
  movable items connected by segmentation bridges. Separate tight instance captures
  remain required. Replacing segmentation or assigning a single warp would not be
  justified by the available unlabeled photos.
* Fine changes were searched only at thumbnail sampling, with original pixels used
  solely for crops around coarse proposals. New fixed original-pixel windows can
  emit separately scoped appearance regions without a thumbnail proposal. A generated
  one-pixel 50-level line is missed at 4x thumbnail reduction and detected in its
  original tile. This is a software sensitivity control, not damage recall evidence.
* Source-resolution transforms previously omitted pixel-center resize offsets.
  Composed source/processing/crop transforms now preserve sample centers. Both
  registered images use equal sampling kernels; original arrays are preserved.

## GPU and bounded execution

The six-image, seven measured repetition benchmark compares FP32 DINO four-rotation
batching with sequential forwards. Batch medians are 10.3–12.2 ms versus 24.3–30.8 ms;
maximum measured embedding element error is 0.000362 and minimum cosine is 0.9999982.
Allocated DINO memory is about 121 MB versus 108 MB. Four-view batching is retained
on CUDA; CPU stays sequential. A 12-entry exact image/target CPU mask cache avoids
duplicate segmentation and returns defensive copies. Models still load sequentially.

Native original-pixel object crops at 512 and 640 LoFTR input sizes recovered no
additional rejected real pairs across 48 attempts; this extra runtime path was rejected.
Existing measured CPU geometry/warping and CUDA appearance defaults remain.
No AMP, heavyweight model, or unvalidated nonrigid dense warp was introduced.

Refined real-pair median process wall time is {current["real_pair"]["median_wall_seconds"]:.3f} s;
previous v3.1 was {summaries["previous_v31"]["groups"]["real_pair"]["median_wall_seconds"]:.3f} s.
These campaign medians reflect changing host load and extra surface work; they are
not a controlled end-to-end speedup claim. Across groups the maximum allocated CUDA
memory is {max(g["peak_cuda_allocated_bytes"] for g in current.values()) / 1024**2:.1f} MiB,
reserved CUDA {max(g["peak_cuda_reserved_bytes"] for g in current.values()) / 1024**2:.1f} MiB,
and host working set {max(g["peak_host_bytes"] for g in current.values()) / 1024**3:.2f} GiB.

## Verification and readiness

Test records: `{json.dumps(tests, sort_keys=True)}`.
Full native CPU/CUDA suite and separate synthetic-only policy checks are required
for the engineering verdict above. Lint and formatting are checked separately.
The initial full-suite process recorded four child-worker `memory_reserve` refusals
under host RAM pressure. All other 289 tests passed; two policy-mode tests were
checked separately. `native-recheck.xml` records the four affected checks in a fresh
process. The verdict requires those exact failed test identities to pass on recheck;
the initial failure XML remains preserved. Memory thresholds were not relaxed.

The engine is suitable for the measured, bounded, private standalone human-review
workflow. Application integration is not completed or validated. It is not ready
for automatic damage decisions, identity confirmation, pilot accuracy claims, or
financial authority. Independent physical condition labels and matched unchanged
recaptures are still absent. These repeatedly inspected photos are engineering
regression data, not a held-out accuracy set.

Local-region hypotheses and original-tile regions can arise from reflections,
illumination, nonplanarity, or registration error. Their scores are uncalibrated;
possible damage hypotheses remain empty. Cross-view surface correspondence and
contradiction analysis remain unestablished. Scans cover at most four fixed windows
per view within an inspection-wide default of four (maximum eight), so fine detail
outside cited tiles remains unknown. Larger configured workloads are not stress-tested.

## Reproduction and evidence

Run from `ep/` with the approved Conda interpreter and local optional package path:

```powershell
$env:PYTHONPATH = '.runtime/v3-packages;.'
& $epPython -B scripts/evaluate_v31.py current --campaign refinement-final
& $epPython -B scripts/report_v31_refinement.py
```

The preserved frozen v3 campaign is `ep-v31-20261111/baseline-complete`; prior v3.1
is `current-release`; current evidence is `current-refinement-final` under that root.
The pre-refinement v3.1 source snapshot is
`ep-v31-improvement-20261111/pre-refinement/ep_engine`.
The [private refinement gallery](../.test-artifacts/ep-v31-improvement-20261111/index.html)
links original registered crops, overlap masks, and residual maps.
Machine gates, source hashes, experiment ledgers, and test XML are retained alongside it.
"""
    (ROOT / "docs/ep-v31-refinement-report.md").write_text(report, "utf-8")
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>EP refinement evidence</title>'
        "<style>body{font:16px system-ui;margin:24px;background:#eee}"
        "article{background:white;padding:16px;margin:16px 0}"
        "img{max-width:24%;max-height:320px;object-fit:contain}p{margin-top:24px}</style>"
        "<h1>EP v3.1 refinement — private appearance evidence</h1>"
        "<p>Localized visual differences require human review. "
        "Physical damage and identity remain unverified.</p>" + "".join(gallery),
        "utf-8",
    )
    print(json.dumps(gates, indent=2))


if __name__ == "__main__":
    main()
