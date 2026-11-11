# Real-image evaluation

Evaluated 2026-11-08 using the existing native Windows Conda interpreter and approved
EfficientSAM-Ti/DINOv2-S/14 weights on CUDA. No downloads, dependencies, training,
Gemini, architecture changes or changes outside EP. No application code or thresholds changed.

## Images and agreed comparisons

Seven originals decoded successfully. Inventory includes full SHA-256 hashes, dimensions,
available EXIF and quality measurements in
[`inventory.json`](../.test-artifacts/real-image-evaluation/inventory.json).
Hash prefixes below identify those records; all original bytes were verified unchanged.
Quality is measured after the existing maximum-side-768 preprocessing.

| Photograph | Dimensions W×H | SHA-256 prefix | Focus variance | Global quality |
| --- | --- | --- | ---: | --- |
| chair1.jpeg | 365×547 | febb9195ffca | 3731.0 | usable |
| drill1.jpg | 1500×1101 | a115ec907777 | 372.3 | usable |
| drill2.jpeg | 558×358 | 440d92b875a2 | 118.8 | usable |
| drill3.jpeg | 335×597 | f43d722413a5 | 819.0 | usable |
| headphone1.jpeg | 480×640 | b892f76ccede | 765.0 | usable |
| headphone2.jpeg | 447×447 | 3621e1e59c21 | 1636.6 | usable |
| suitcase1.jpeg | 451×680 | 88a4b411999e | 331.7 | usable |

No inventoried EXIF established capture order/device/time. The user explicitly authorized
the three exploratory directions below, with **actual before/after roles, physical identity
and condition labels unverified**. Directions are computational inputs, not capture history.
The chair and suitcase have no established counterpart and were not paired artificially.
Manually selected normalized target boxes identify the pictured drill assembly or headphones;
no largest-object heuristic selected a target. Boxes, normalized-image hashes and unresolved
labels are in the private `manifest-template.json`. Supporting hands may occlude the target.

## Actual CV results

| Exploratory direction | Outcome | Cosine | Candidates | Worker wall s | Pipeline s |
| --- | --- | ---: | ---: | ---: | ---: |
| drill1.jpg → drill2.jpeg | inconclusive | 0.49338 | 0 | 16.409 | 12.911 |
| drill1.jpg → drill3.jpeg | inconclusive | 0.46169 | 0 | 13.477 | 10.590 |
| headphone1.jpeg → headphone2.jpeg | inconclusive | 0.45313 | 0 | 15.777 | 12.257 |

All runs used real pretrained inference. Each produced two structurally valid object masks
and two object crops. All pairs stopped at `embedding_inconsistent`, below the unchanged
0.65 gate. **Local matching, RANSAC and alignment were not evaluated by the pipeline.**
Their default zero match/inlier counters are not measured correspondence counts.
Consequently no valid overlap, difference map or candidate overlay was generated; creating
those for rejected pairs would imply unsupported alignment. No candidate count is a damage
judgment or a measured false-positive rate.

Peak worker Windows working sets were 1,488,121,856 / 1,489,887,232 / 1,488,674,816 bytes
respectively; peak Torch CUDA allocations were 486,651,904 / 486,651,904 / 486,303,744 bytes.
These are single-run measurements including fresh-worker setup, not latency percentiles.
Existing host/VRAM guards, timeout, Windows worker lock and checkpoint validation remained active.

## Visual findings and changes

Inspected all mask overlays and three tentative descriptor-match previews:

- The drill masks largely select the intended tools; `drill3` also includes portions of
  the supporting fingers. `headphone2` includes detached background fragments. Its mask
  contains components of 105,495, 2,109 and 178 pixels (components >=25 pixels), consistent
  with the visible leakage. These are model prediction limitations despite passing
  structural mask validation, not independently measured segmentation accuracy.
- The headphone2 quality record warns `possible_cropping` while retaining `usable` status.
  A usable focus/exposure score does not establish complete visibility or mask correctness.
- Tentative matches link visually different details, especially across drills and headphone
  views. These previews show the top 20 cross-checked SIFT descriptor matches per pair,
  **without ratio/RANSAC acceptance**. They are diagnostic only and do not override the gate.
- Visible design differences, background/occlusion variation and watermarks constrain
  interpretation. The stock watermark on `drill1` passes ordinary quality checks; those
  checks do not authenticate rental evidence. Provenance/licensing remains unverified.

No reproducible software defect or falsely definitive change result was demonstrated.
No fixes, new regression tests or threshold tuning were justified. Arbitrarily removing
disconnected components or retaining the largest component could discard real target parts
and is not supported by this unlabeled collection. Mask leakage needs reviewed target masks
and representative occlusion cases before a general cleanup/quality rule is adopted.

## Private evidence and validation

All generated data is under `.test-artifacts/real-image-evaluation/`:

- `inventory.json`, `contact-sheet.png`: inventory and source thumbnail review.
- `private/manifest-template.json`, `predictions.json`, `evaluation.json`, `results.json`:
  approved exploratory cases, explicit null labels, blocked metrics and measured outcomes.
- `private/cv/work/<case-id>/input.json`, `package.json`, `worker.log`, `output/*.png`:
  original/normalized hash citations, prompt boxes, model hashes, timings, masks and crops.
- `private/cv/work/<case-id>/tentative-unverified-matches.png` and `private/mask-review.png`:
  inspected diagnostic previews. Case IDs are `drill1-to-drill2`, `drill1-to-drill3`,
  and `headphone1-to-headphone2`.
- `run_evaluation.py`: archived focused execution, reusing the existing decoder,
  `ProcessRunner`, contracts, Windows lock and artifact validator. For another execution,
  use a fresh output workspace so artifacts from different runs are not mixed.
- `targeted-tests.log`, `full-tests.log`: complete test execution logs.

Artifact manifests, PNG metadata and hashes passed existing validation. The existing
`scripts/evaluate_phase2.py` validated all three cases with no missing predictions;
identity/viewpoint/change metrics report `blocked_no_labels`, and localization/mask metrics
report no assessable labels. No accuracy, precision, recall or mask IoU was fabricated.

Native PowerShell test commands, with the approved interpreter:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/verify.py unit
$env:EP_RUN_REAL_CV = '1'
& $epPython -B scripts/verify.py all
```

Focused unit checks: **40 passed**, 0 failures/skips, 4.52 s. Final complete Phase 1 +
Phase 2 suite, executed once: **114 passed**, 0 failures/errors/skips, 49.48 s, including
genuine CUDA/CPU tests. Retained upstream warnings: one TestClient notice in unit tests;
seven TestClient/xformers notices in the full suite. Coverage and model benchmarks were
not rerun. Originals were hash-verified after inference and final tests.

## Missing evidence and Phase 3 readiness

Need confirmed captures of the same physical item before/after, target-mask annotations,
comparable-view labels, independently reviewed condition/change regions, provenance and
permission to use the photos. No currently successful real-photo alignment/change example
exists in this collection. Abstention execution is verified; correct abstention rates and
change-detection accuracy are not. Phase 3's package interface exists, but these results
do **not** establish accuracy or production readiness. Review mask leakage and collect
genuinely corresponding labeled pairs before relying on downstream conclusions.
