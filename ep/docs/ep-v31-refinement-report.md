# EP v3.1 refinement evaluation

ENGINEERING READY: bounded standalone human-review workflow. Evaluation completed on the existing RTX 4060 Laptop GPU (8 GB).
Physical identity, damage precision/recall, and deployment readiness remain unverified.
No payment, database, application integration, model download, or Git commit was performed.

## Measured result

| Measurement | Frozen v3 | Previous v3.1 | Refined v3.1 |
|---|---:|---:|---:|
|Real pairs|{'inconclusive': 10, 'comparable': 6, 'failed': 1}|{'inconclusive': 10, 'comparable': 7}|{'inconclusive': 9, 'comparable': 8}|
|Multiview jobs|{'inconclusive': 2, 'partially_comparable': 1, 'failed': 1, 'comparable': 1}|{'inconclusive': 1, 'partially_comparable': 3, 'comparable': 1}|{'inconclusive': 1, 'partially_comparable': 3, 'comparable': 1}|
|Exact repeats|{'comparable': 14, 'failed': 3}|{'comparable': 17}|{'comparable': 17}|
|Different-object controls|{'inconclusive': 5}|{'inconclusive': 5}|{'inconclusive': 5}|
|Archived unlabeled pairs|{'failed': 5, 'comparable': 7}|{'comparable': 11, 'inconclusive': 1}|{'comparable': 11, 'inconclusive': 1}|

All 56 refined jobs completed without runtime failure. Real-pair comparability is
8/17 (47.1%), versus 7/17 (41.2%) in previous v3.1 and 6/17 in frozen v3.
Phone improves from 1/3 to 2/3; bag remains 0/4, shoes 1/4, clock 2/3, speaker 3/3.
Bag-front additionally has local correspondence evidence covering about 6% of its
after mask, while its full-pair outcome remains inconclusive.
All 17 exact repeats have zero coarse candidates, boundary hypotheses, and additional
surface appearance regions. All five different-category controls abstain on identity.
1294 current artifact digests and all 56 strict reports were validated.
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

Refined real-pair median process wall time is 12.006 s;
previous v3.1 was 12.628 s.
These campaign medians reflect changing host load and extra surface work; they are
not a controlled end-to-end speedup claim. Across groups the maximum allocated CUDA
memory is 478.2 MiB,
reserved CUDA 966.0 MiB,
and host working set 1.68 GiB.

## Verification and readiness

Test records: `{"full-tests.xml": {"errors": 0.0, "failures": 4.0, "skipped": 2.0, "tests": 295.0, "time": 336.96}, "native-recheck.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 4.0, "time": 192.383}, "policy-tests.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 2.0, "time": 0.815}}`.
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
