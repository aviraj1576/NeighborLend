# Advisory CV improvements — 10 November 2026

This extension changes only the standalone EP package. It does not integrate with or
modify the NeighborLend application, payment subsystem or application database. All
outputs remain hypotheses requiring human review. No visual result has financial authority.

## Implementation

EfficientSAM now evaluates all three output masks instead of always taking the highest
predicted IoU score. Target occupancy, leakage, connected-component dominance, frame-border
occupancy and ambiguity checks reject implausible masks. The same validation applies to
injected adapters. `Segmentation.target_support` exposes these checks. Their values are
plausibility measurements, not segmentation accuracy or damage confidence. Explicit target
boxes remain required; the system does not claim a new automatic semantic object detector.
Tight targets are preferable to nearly full-frame prompts. Failed targeting remains inconclusive.

DINOv2 embeddings retain the whole masked object in a neutral square canvas. Four sequential
quarter-turn views are normalized and pooled, avoiding cropped object ends and bounding VRAM.
This changes similarity distributions, so production calibration still needs independent
reviewed data. The existing similarity threshold has not been relaxed, and DINO similarity
cannot by itself establish identity or a comparable view.

Local matching uses CLAHE only for feature extraction, RootSIFT descriptors and mutual
ratio matches. SIFT precise pyramid upscaling prevents a measured half-pixel localization
bias that produced false change boxes on a rotated copy of a photograph. Homographies
must have distributed convex-hull support in both images and bounded forward/reverse
reprojection error. A similarity-transform alternative requires the same correspondence,
inlier, spatial support and overlap safeguards. Low-texture objects still abstain when
correspondences are insufficient. No mask-only, box-only or embedding-only warp is accepted.

The appearance detector corrects bounded global gain and offset. It retains thin connected
structures previously removed by morphological opening, while maintaining overlap and area
checks. Candidates remain `local_appearance_change`; no crack, dent, tear, scratch or physical
damage classification is confirmed. Shadows, reflections, occlusions and articulation are
known remaining ambiguities.

`CVPackage.boundary_changes` is separate from appearance candidates. Each record references
a comparable pair, normalized source-frame boxes and pair-specific boundary artifacts. A
`potentially_missing` region means reference foreground lacks corresponding return foreground;
`additional_or_displaced` is the reverse. Neither proves loss or identifies a semantic part.
Clipped objects, gross silhouette disagreements and unsupported geometry abstain. Boundary
maps contain hypothesis bounding regions rather than pixel-level ground-truth masks.
Boundary hypotheses also require a corroborating photometric change in the proposed region.
Mask variations without such evidence are recorded as unsupported, not potentially missing parts.

The assessment layer leaves boundary hypotheses inconclusive and does not call a provider
for boundary-only evidence. A truncated candidate budget also leaves the comparison
inconclusive. Every assessment retains `payment_action="none"`, human review and unverified
physical identity.

## Quality, views and compatibility

Existing `CVConfig` defaults, including all quality, similarity, geometric and difference
thresholds, are unchanged. Quality is measured on unenhanced processing pixels. No sharpening,
upsampling or feature equalization can make an image pass quality checks. Quality failures
include recapture recommendations. Supply original-resolution photographs; the existing
maximum processing side is 768, with an already-supported 1024 option. Processing does not
recover information absent from an image.

Existing evidence viewpoint labels are passed to workers. Distinct nonempty labels prevent
cross-view matching; absent labels retain geometric matching. Labels never prove correspondence.
Direct `InputImage` callers can optionally set `view`. Matching still needs visual and geometric
support, even for identical labels.

Results record `models.algorithm_revision="ep-cv-2.1-advisory"` and preprocessing metadata.
The existing CV wire envelope remains readable, with additive optional fields and additional
artifact kinds: `aligned_before`, `alignment_overlay`, `boundary_change_map`, `boundary_overlay`.
Strict older consumers must update before consuming new results. Existing archived packages
remain readable and preserve their already-bound assessment digests when the new fields have
legacy defaults. Non-default new evidence changes the digest. No database migration is needed.

## Resources and verification

One pretrained model remains resident at a time. Rotation views execute sequentially.
Existing memory reserves, hard worker timeouts, cancellation and model cleanup stay active.
Metrics include synchronized neural forward time/counts per model, per-image operation wall
times, stage time, process memory and peak allocated/reserved CUDA memory. Per-image times
include lazy loads where applicable; nested forward times must not be added twice.

The full before/after artifacts are isolated in
`.test-artifacts/engine-improvement-20261110-01/`:

- `evaluation-report.md`: measured before/after results, tests, failures and limitations.
- `index.html`: actual source, mask, matching, alignment, appearance and boundary visualizations.
- `summary.json`, `before-after-comparison.json`: measured outcomes, abstention and resource use.
- `implementation.diff`, `modified-files.json`: exact source and regression changes.
- `verification.json`: source/checkpoint integrity, artifact validation and archive digest checks.
- `baseline/`, `baseline-recovery/`, `improved/`, `improved-final/`: preserved run attempts.
- `improved-release/`: final matched baseline comparison after all safeguards.
- `additional-probes/`, `additional-probes-final/`: preserved rotation and 1024-pixel probes.
- `additional-probes-release/`: final CUDA rotation/1024 evidence after appearance corroboration.
- Test XML/log files retain the actual commands' pass/fail/skip evidence.

Use the existing native environment from `ep/`:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:EP_RUN_REAL_CV = '1'
$env:EP_RUN_CONTROLLED_CV = '1'
& $epPython -B scripts/verify.py all
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
```

The evaluation starts from original files and preserves their hashes. The 42 user images
still fail the unchanged quality gate; successful capture controls do not establish success
on those images. Bundled photographs and clearly identified generated/edited controls test
implementation behavior. They are not independently reviewed physical-damage ground truth.
No real-world accuracy or false-alarm rate is claimed.

Before integration, collect sharp matched captures with reviewed object identity, target masks,
visibility, view and damage history. Validate masks and similarity on an independent object-level
holdout, assess occlusions and reflective/nonplanar surfaces, and review semantic part inventories.
Keep financial decisions outside the advisory engine.

API references: [pinned EfficientSAM example](https://github.com/yformer/EfficientSAM/blob/d525f622e6f640acf5a0fc37c7ca1f243da5bde0/EfficientSAM_example.py),
[DINOv2](https://github.com/facebookresearch/dinov2),
[OpenCV geometry](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html),
[OpenCV precise SIFT upscaling](https://docs.opencv.org/4.10.0/d7/d60/classcv_1_1SIFT.html).
