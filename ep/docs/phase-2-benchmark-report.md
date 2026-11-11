# Phase 2 benchmark report

Date: 2026-11-08, Asia/Calcutta. Genuine native pretrained CUDA/CPU inference and a full
authenticated API-to-worker comparison were executed. Software execution is verified;
real-world accuracy validation remains **blocked** because independent labels are absent.

## Hardware, models and images

Native Windows, Python 3.11.16 from the approved `neighbourlend_yolo` environment;
Torch 2.11.0+cu128, CUDA 12.8, RTX 4060 Laptop GPU (8,585,216,000 VRAM bytes),
16,802,746,368 physical RAM bytes. Weights/source revisions/hashes are in the model audit.
Both models run sequentially in eval/inference mode, batch one; no extension or new package.

The image is the **already installed** Ultralytics 8.4.132 bundled `bus.jpg` at
`D:/Anaconda_Install/envs/neighbourlend_yolo/Lib/site-packages/ultralytics/assets/bus.jpg`.
Its original SHA-256 and source path are in `.test-artifacts/phase2-benchmark/results.json`.
It was read locally; no image or dataset was downloaded. Ultralytics package assets carry
their upstream licensing/provenance obligations; these local smoke derivatives are not
an independently licensed dataset release. Do not redistribute them as newly owned images.
No user rental evidence was used. All synthetic derivatives are explicitly documented.

The photograph is resized to 576x768. Target selection is the normalized box
`(0.03,0.20,0.99,0.72)` around the visible bus. The corresponding image is a byte-identical
derivative; it is not a new capture. Synthetic edit: RGB `(220,20,20)` painted over
rows 220:245 and columns 250:300. Perspective case uses the recorded near-identity
projective transform in `scripts/benchmark_phase2.py`; it is not a real camera-angle pair.
Blur uses a 71x71 Gaussian kernel, sigma 25; textureless return is uniform RGB 128.
There are no physical scratch/crack/dent labels, real changed-angle captures or verified
instance-identity annotations. Faces/background in the bundled image are not evaluated.

## Native forward probes

`scripts/probe_phase2_models.py` executed real masks and embeddings on both devices.
These are single-observation timings, including each stage's load, not throughput estimates.

| Measurement | CUDA | CPU |
| --- | ---: | ---: |
| EfficientSAM load, seconds | 0.7542 | 0.4827 |
| Segmentation including load, seconds | 1.9755 | 2.6215 |
| DINOv2 load, seconds | 0.8129 | 0.7862 |
| Embedding including load, seconds | 0.9853 | 0.9143 |
| Mask dimensions | 768x576 | 768x576 |
| Mask fraction | 0.2896502 | 0.2896299 |
| Embedding dimensions | 384 | 384 |
| Embedding norm | 0.99999994 | 1.0 |
| Process RSS at measurement, bytes | 1,408,229,376 | 1,443,553,280 |
| Peak Torch CUDA allocation, bytes | 486,762,496 | 0 (CPU work) |

Both outputs passed finite-value/type/shape guards. The CPU probe ran after CUDA in the
same probe process, so its RSS is not an isolated pure-CPU process baseline. A separate
real connected pipeline test also passed on each device at maximum side 512: complete
stage execution, supported pair, finite normalized features, no candidate for the unchanged
pair, private artifacts and model cleanup. Those assertions are software checks, not accuracy.

## Final end-to-end native worker benchmark

The final run includes queueing through TestClient, authorized source validation,
Windows worker locking, an actual hidden native subprocess, real pretrained inference,
validated result persistence, authorized result retrieval and PNG artifact retrieval.
Wall timing starts after queue creation and covers worker execution plus those reads;
it excludes the preceding upload/inspection/queue requests. Pipeline timing is measured
inside the child. Each case starts a fresh child, but filesystem/OS caches can be warm.

| Case | Outcome | Candidates | PNGs | Worker/read wall s | Pipeline s | Peak working set bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged photo derivative | comparable | 0 | 8 | 9.4800 | 6.9539 | 1,495,949,312 |
| Synthetic appearance edit | comparable | 1 | 10 | 8.9799 | 6.7998 | 1,495,777,280 |
| Synthetic perspective | comparable | 0 | 8 | 9.2212 | 6.8692 | 1,522,348,032 |
| Unusable blur | inconclusive | 0 | 2 | 8.7529 | 6.5186 | 1,521,909,760 |
| Insufficient texture | inconclusive | 0 | 2 | 8.7083 | 6.4575 | 1,521,422,336 |

All cases completed without software errors. The last two still analyze the usable
reference image but exclude the unusable return from matching; their two artifacts belong
to that reference. They are not successful comparisons or proof of unchanged condition.
Final worker RSS ranged from 1,401,716,736 to 1,428,299,776 bytes. Peak Torch allocation
was 486,762,496 bytes (about 464 MiB) for each CUDA child. Windows peak working set is the
OS-reported process value; Torch's peak is allocator-tracked tensors, not total device
memory including driver/context or other applications. Parent/API memory is not included.

Unchanged pair: cosine 1.0, 275/275 local inliers, overlap 0.8932. Synthetic edit:
cosine 0.99246, 269/269 inliers, overlap 0.8887, one localized appearance candidate.
Synthetic perspective: cosine 0.98617, 166/166 inliers, overlap 0.8684, no candidate.
These are measurements on three closely related derivatives, not calibrated identity
probabilities or generalization evidence. The generated synthetic-edit overlay was visually
inspected: the marked region encloses the painted rectangle. PNG dimensions/hashes and
package citations also passed automatic validation.

Per-model load times, every stage time, transforms, quality measures, UUIDs, weight hashes
and artifacts are retained in `.test-artifacts/phase2-benchmark/results.json` and individual
`*-package.json` files. Private artifacts stay under that benchmark's `private/cv/artifacts/`.
These results are single runs per case; no percentile latency, sustained throughput,
thermal-stability or repeated-trial confidence interval is claimed.

## Performance baseline and changes

The first successful full benchmark measured unchanged-pair wall/pipeline times of
9.8418/7.4571 seconds, worker RSS 1,421,856,768 bytes and peak Torch allocation
486,762,496 bytes. After reliability/validation changes, the final corresponding values
are 9.4800/6.9539 seconds, RSS 1,401,745,408 bytes and the same peak Torch allocation.
These are uncontrolled repeated observations under varying memory/cache conditions,
not evidence of a speed or memory improvement. No accuracy/performance tradeoff is claimed.
Final unchanged-pair stage times were quality 0.0257, segmentation 5.4541, features
1.1732, matching 0.0411, alignment 0.1415 and candidates 0.1151 seconds. Segmentation
includes first Torch/model setup and is the main measured cost. Reusing normalized
derivatives, bounded resolution/pair ranking, batch one and sequential models are current
design bounds. Cross-run model/embedding caching and approximate acceleration are deferred
until controlled repeated measurements and independent correctness data justify changes.

## Failures, evaluation and limitations

Two early end-to-end attempts correctly stopped with `memory_reserve` when free host RAM
was insufficient. The user freed application memory; subsequent full runs succeeded.
No unsafe inference was forced, no programs were closed automatically, and no safety
reserve or OS/package setting was changed. Final preflight available RAM was above 6 GB.

The generated manifest has five smoke cases, one object-image group, exact image hashes
and **null labels**. The evaluation CLI validated it with no missing predictions and reports:
identity/viewpoint/change metrics `blocked_no_labels`, localization
`blocked_no_assessable_regions`, segmentation `blocked_no_assessable_masks`.
There is no damage precision/recall/F1, real false-positive rate or segmentation IoU claim.
Correct-looking masks and expected synthetic behavior cannot replace independent truth.

Real camera-angle changes, varying illumination/backgrounds, actual scratches/cracks/dents,
missing parts, pre-existing damage, similar physical instances, real occlusions and missing
reference surfaces require a consented, reviewed collection before acceptance decisions.
Thresholds are experimental; homographies support only adequately matched visible regions.
Shadows, reflections, curved geometry and unseen areas can remain ambiguous. Human review
is mandatory; neither no candidates nor inconclusive output establishes no damage.

Commands and schema are in `phase-2-testing-report.md` and
`phase-2-evaluation-workflow.md`. No collection, labels or accuracy metrics were fabricated.
