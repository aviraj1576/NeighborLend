# EP Engine v3: standalone hybrid vision

Implemented 10 November 2026 (Asia/Calcutta). This opt-in engine is independently
executable. NeighborLend's AI routers, upload inference, frontend AI contracts and
payment authority do not invoke it. Existing v2 execution remains available.

## Execution and authority

```text
Unenhanced image quality gate
  -> explicit object target + EfficientSAM candidate validation (CUDA)
  -> whole-object, four-rotation DINOv2 embeddings (CUDA, bounded CPU cache)
  -> mutual RootSIFT matching (CPU)
  -> optional LoFTR fallback/comparison (CUDA, local verified checkpoint)
  -> independently verified homography or similarity transform
  -> overlap/footprint validation and alignment
  -> illumination-compensated appearance residual + separate boundary evidence
  -> structured advisory evidence / abstention / human review
```

The standalone JSON envelope always has `payment_action="none"`,
`human_review_required=true`, and `physical_identity_verified=false`. Regions are
appearance or boundary hypotheses. They do not prove a scratch, crack, missing
physical component, causation, liability, or physical object identity. There is no
automatic refund, deduction, settlement, or application integration.

Explicit normalized target boxes remain necessary. EfficientSAM evaluates its mask
candidates with the existing target occupancy, leakage, connected-component,
frame-border and ambiguity checks. Plausibility is not measured mask accuracy.
Frame contact warns about cropping; clipped boundary assessment abstains. No new
semantic detector, occlusion recognizer, or part inventory is claimed.

Quality and similarity thresholds inherit the baseline unchanged. CLAHE applies to
RootSIFT feature extraction only. Quality pixels are never enhanced to pass the
gate. Different explicit view labels prevent cross-view matching. Missing labels
still require visual and geometric support. DINO similarity cannot verify identity.

## Defaults chosen from measurement

| Operation | Default | Alternative |
| --- | --- | --- |
| Segmentation / embeddings | Existing CUDA EfficientSAM-Ti / DINOv2-S14 | Explicit CPU / auto device |
| Matching | RootSIFT first | LoFTR on weak geometry, or explicit comparison |
| Geometry | OpenCV RANSAC | Kornia CUDA RANSAC, experimental and slower in this benchmark |
| Alignment | OpenCV | Kornia CUDA warp, experimental |
| Appearance SSIM / quantiles | FP32 CUDA | OpenCV on explicit CPU, missing CUDA, or CUDA OOM |
| Precision | FP32 with inference mode | AMP remains disabled: no validation justifies changing precision |

Optional matching is disabled until explicitly configured. It never rescues an
embedding-inconsistent pair. Weak geometry means no valid transform, inlier ratio
below 0.65, or minimum spatial coverage below 0.10. These trigger extra computation;
they do not relax the acceptance thresholds. Every method must pass the original
minimum inlier count/ratio and 3% spatial coverage, transform plausibility,
bidirectional per-point reprojection checks and overlap validation.

RootSIFT and LoFTR use the same verification path. Points must be finite, within
both object masks, confidence-filtered and unique at both endpoints. At most 4,096
correspondences reach RANSAC. Both homography and lower-degree similarity candidates
are checked. Reflections, extreme scaling, projective horizons, concentrated
support, poor overlap and incompatible geometry fail closed. Dense learned matches
are correlated; selection balances coverage, inlier ratio and reprojection error,
with a capped inlier-count tiebreaker. More matches alone never wins.

Image warping preserves source-to-destination pixel coordinates. CUDA compares
only eroded object overlap within a fully covered sampling footprint. Heavy SSIM,
quantiles and appearance residuals run on CUDA; luminance conversion, connected
components and boundary analysis remain on CPU. This is GPU-first hybrid execution.

When alignment magnifies the reference by more than 5%, appearance comparison uses
the coarser available reference sampling density. The reference is rewarped onto
that grid and the return is area-resampled, rather than interpreting detail absent
from an enlarged reference as damage. Difference maps and region boxes map back to
the original target processing frame. A limitation explicitly identifies finer
unassessable detail. This corrects the measured 768-to-1024 false-proposal case
without changing quality, difference, or correspondence acceptance thresholds.

## Dependencies and local setup

Use the existing native Windows Python environment with the validated Torch CUDA
build, OpenCV, NumPy, Pillow and psutil. Existing EfficientSAM/DINO assets remain in
their original audited store. The optional extra pins `kornia==0.8.2` and
`kornia_rs==0.1.10`. This execution installed those two packages only into
`ep/.runtime/v3-packages`; it did not replace the shared environment or Torch.

From `NeighborLend/ep`:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTHONPATH = '.runtime/v3-packages;.'
# Only needed in another environment; existing local installation already exists:
# & $epPython -m pip install --no-deps --target .runtime/v3-packages kornia==0.8.2 kornia_rs==0.1.10

# Explicit optional download, only when the file is absent; refuses overwrite:
# & $epPython -B scripts/fetch_v3_loftr.py
```

LoFTR uses the upstream author's HTTPS outdoor checkpoint. This run downloaded
46,341,978 bytes to `.runtime/v3-models/loftr_outdoor.ckpt`, with SHA-256
`21f5bec5968178e8bc8b7633441836fe5de4f47d861dd2cd7dc38e271b0479ec`.
Its separate receipt records provenance. The digest was recorded on first download;
it is not an upstream signature. Runtime loading verifies the configured digest,
uses `torch.load(weights_only=True)` and strict finite tensor state, and constructs
`LoFTR(pretrained=None)`. Inference never downloads checkpoints. LightGlue was not
installed or benchmarked; LoFTR supplies the requested optional learned path.

## Run an independent inspection

Create a private JSON manifest inside `ep/`, using the existing evidence-worker
format. Each derivative is an integrity-bound PNG named for its UUID, also inside
`ep/`. `sha256` identifies its source and `normalized_sha256` binds PNG bytes.

```json
{
  "inspection_id": "00000000-0000-4000-8000-000000000001",
  "config": {"device": "cuda", "max_side": 768},
  "evidence": [
    {
      "id": "00000000-0000-4000-8000-000000000002",
      "stage": "before",
      "path": "ABSOLUTE_EP_PRIVATE_PATH/00000000-0000-4000-8000-000000000002.png",
      "sha256": "REPLACE_WITH_SOURCE_SHA256",
      "normalized_sha256": "REPLACE_WITH_PNG_SHA256",
      "view": "front",
      "target": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9}
    }
  ]
}
```

The example shows one record; supply at least one `before` and one `after` with
distinct UUIDs and actual paths/digests. Defaults need no learned checkpoint. To
enable LoFTR, add `learned_matcher="loftr"`, the absolute local `checkpoint` path and
`checkpoint_sha256`. Use `compare_matchers=true` only for explicit evaluation.
`alignment_backend="cuda"` and `geometry_backend="kornia"` are independent opt-ins.

```powershell
& $epPython -B scripts/run_v3.py .runtime/private-inspection/input.json --output .runtime/private-inspection/run-001
```

Output directories must be new and within EP. `result.json`, `worker.log` and cited
PNG artifacts are private local files. The launcher acquires the existing Windows
worker lock and enforces a subprocess deadline (`timeout_seconds`, default 180).
Timeout terminates the child and returns a typed failure with no financial action.
The engine has no newly exposed HTTP endpoint.

## Memory, caching and recovery

Only one existing segmentation/embedding model is resident at a time. Four DINO
rotations run sequentially. DINO is released before learned matching; LoFTR is
released at the end of the inspection. Images remain bounded to 768 pixels by
default and 1,024 maximum; LoFTR has a separate 512 default / 640 maximum side.
Dimensions are divisible by eight with exact inverse coordinate scales.

The bounded per-model embedding LRU holds at most 32 CPU vectors by default (128
maximum). Keys bind image/mask content, shape, dtype, preprocessing, device and
verified model receipt. Returned arrays are defensive copies. This is not a shared
cross-user disk cache. Repeated image feature extraction within a run is avoided.

Existing host/VRAM reserves remain. LoFTR checks host and device reserves before
loading. Optional matcher OOM records failure and keeps valid RootSIFT evidence or
abstains. CUDA kernel/geometry OOM has a recorded CPU fallback with the same gates;
other runtime errors are not silently suppressed. Timings, matcher attempts,
current allocation, CUDA high-water observations and process RSS/peak working set
are exposed in metrics. Peak allocated/reserved Torch memory is different from
whole-device usage and does not include other applications.

## Reproduction and limitations

```powershell
$env:EP_RUN_REAL_CV = '1'
$env:EP_RUN_CONTROLLED_CV = '1'
$env:EP_RUN_V3_CUDA = '1'
& $epPython -B scripts/verify.py all
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
& $epPython -B scripts/benchmark_v3.py --output .test-artifacts/NEW-v3-run --native --checkpoint .runtime/v3-models/loftr_outdoor.ckpt --checkpoint-sha256 21f5bec5968178e8bc8b7633441836fe5de4f47d861dd2cd7dc38e271b0479ec
```

The benchmark records versions, seeds, source hashes, quality at original/768/1024
sizes, warm/cold matcher metrics, CPU/GPU parity and annotated native cases. UUIDs,
timings and GPU operations are not promised bit-for-bit deterministic. Each output
directory is new; prior evaluations and checkpoints are retained.

See [the completion report](../../docs/final-payment-ep-v3-report.md) for measured
results and test counts. Physical-damage accuracy remains unavailable: there is no
adequately reviewed real damage holdout. The 42-image rental collection has no
reviewed condition/focus labels and remains quality-rejected. Synthetic controls
test software behavior, not real damage recognition. One thin photo edit is missed;
occlusion edits can produce appearance proposals. Masks, glare, shadows, cropped
views, low texture, nonplanar surfaces and moderate parallax remain limitations.
No-candidate output does not establish an undamaged object.

**Integration recommendation: NOT READY for automated physical-condition or
liability decisions.** Further standalone human-supervised evaluation is possible.
Review matched original captures, object identity, targets, visibility, damaged and
unchanged regions on an independent object-level holdout before any integration.

Implementation references: [Kornia warp coordinates](https://kornia.readthedocs.io/en/latest/geometry.transform.html),
[Kornia RANSAC](https://kornia.readthedocs.io/en/latest/geometry.ransac.html),
[LoFTR implementation](https://github.com/kornia/kornia/blob/v0.8.2/kornia/feature/loftr/loftr.py),
[LightGlue alternative](https://github.com/cvg/LightGlue).
