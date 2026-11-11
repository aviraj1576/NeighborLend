# Phase 2 benchmark workflow

The Phase 1 benchmark specification remains the annotation/split policy. Phase 2 provides
an executable schema-2 local adapter, not fabricated labels or a replacement dataset.
Manifests and their images must be inside EP; all image paths resolve beneath the manifest
directory. Generated smoke artifacts are local diagnostics and should not be redistributed
as a licensed independent dataset. The bundled photograph's source/license provenance is
recorded in the benchmark report; no new image download was authorized.

## Manifest and predictions

Use JSON with `cases` or JSONL with one case per line. A case contains:

```json
{
  "schema_version": "2.0",
  "case_id": "replace-with-case-id",
  "object_instance_group": "replace-with-physical-object-group",
  "split": "development",
  "scenario_tags": ["same_object_changed_lighting"],
  "provenance": "Document collection consent, source, license and capture method",
  "annotation_status": "unlabelled",
  "labels": null,
  "views": [{"path": "images/example.png", "sha256": "replace-with-actual-sha256"}]
}
```

This is a format example, not an existing labeled example. The loader rejects hash
mismatches, duplicate case IDs, object-instance split leakage, duplicate-image split leakage,
path escapes and labels without `independently_reviewed` status. Splits are `development`,
`calibration`, `test` or `smoke`. Keep every physical object/session and near-duplicate
group in one split; exact hashes do not detect all perceptual duplicates, so collection
review must handle near duplicates. The status field records human review; software cannot
prove an annotator's independence or consent from that field alone.

Only after independent annotation may `labels` contain nullable booleans
`identity_consistent`, `viewpoint_comparable`, `change_present`, plus `regions` and `masks`
keyed by stable view identifier. Regions are lists of normalized `[x1,y1,x2,y2]` boxes on
the orientation-corrected source. Masks are binary 0/255 PNG specifications with `path`
and `sha256`, aligned to that source. Preserve annotation basis, reviewer/adjudicator
identifiers, uncertainty and pre-existing/new distinctions in the collection metadata.

Predictions are JSON `{ "predictions": [...] }` with one record per `case_id`, the same
nullable task fields and optional `regions`/`masks` maps. Missing/unknown assessments are
null, not forced negatives. For full-size mask IoU, explicitly resample a processing mask
into the annotated source grid using nearest-neighbor mapping and record that conversion.
The evaluator rejects differing mask dimensions; it never silently resizes truth.

`identity_consistent` predictions derived from this pipeline are visual-consistency
observations, not physical-identity proof. Keep this distinction when analyzing errors
against independently verified identity labels. Smoke script predictions intentionally
abstain when no comparison is supported.

## Commands

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/benchmark_phase2.py
& $epPython -B scripts/evaluate_phase2.py .test-artifacts/phase2-benchmark/manifest.json
& $epPython -B scripts/evaluate_phase2.py .test-artifacts/phase2-benchmark/manifest.json --predictions .test-artifacts/phase2-benchmark/predictions.json --output .test-artifacts/phase2-benchmark/evaluation.json
```

Replace paths with an approved private labeled collection for real evaluation. Never
tune thresholds on the final test split. Version and hash model weights, sources,
preprocessing, prompts, thresholds and collection manifest before a held-out run.

Binary metrics report labeled/assessed counts, abstention, TP/FP/TN/FN, precision, recall,
F1 and false-positive rate on assessed cases. Unlabeled truth is excluded explicitly;
missing predictions count as abstention. Region metrics use deterministic one-to-one
greedy matching at IoU >=0.3 and report matched IoUs, precision and recall per view.
Segmentation reports mask IoU per annotated/assessed view. Missing region/mask assessments
are not silently scored as correct; retain missing-prediction counts and review coverage.
No physical damage subtype or severity metric is inferred from appearance candidates.

For release evaluation, lock acceptance criteria and sample sizes before viewing outcomes,
report per-stratum and per-object counts, unknown labels, false positives, false negatives,
abstention, failures and object-group bootstrap confidence intervals. The utility provides
core metrics; independent collection, adjudication, confidence-interval analysis and
release acceptance remain prerequisites, not completed evaluations.

Required real-data strata are unchanged objects, lighting, background, camera angle,
scratches, cracks, dents, missing components, pre-existing damage, different physical
instances of one category, blur/occlusion and insufficient reference surfaces. Current
smoke data covers software execution with a single photograph and synthetic transforms;
it does not satisfy those real-data strata. Accuracy validation remains blocked.
