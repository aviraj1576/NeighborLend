# Phase 2 continuation and installation approval plan

Historical approval-gate record. The user subsequently approved the exact JSON payload;
implementation and native inference proceeded. Current results are in the Phase 2 model,
architecture, testing, benchmark and integration reports. The JSON manifest remains immutable.

This is the concrete plan at the approval gate, not a claim of implementation.
Baseline verification passed; details are in `phase-2-baseline-report.md`.

## Approval requested

Approve **only** the official assets enumerated in `phase-2-installation-plan.json`:

- EfficientSAM-Ti checkpoint, 40,982,470 bytes.
- DINOv2 ViT-S/14 checkpoint, 88,283,115 bytes.
- 24 pinned inference Python/license files, 117,864 bytes combined.
- Total approximately 129.4 MB / 123.4 MiB, written only under `ep/.runtime/models/`.

No pip/Conda changes, Torch/TorchVision upgrades, new environment, training dependencies,
model training, paid APIs or changes outside EP are proposed. If further dependencies
become necessary after actual inference tests, report exact additions and request
authorization before changing the environment.

The user's Phase 2 brief requires: “If approval is required, stop at the installation
gate, present the exact changes, and resume implementation only after authorization.”
Work therefore stops at this gate until authorization arrives.

## Proposed download commands — not executed

The following PowerShell commands show the requested checkpoint transfers explicitly.
They use HTTPS and temporary targets inside EP; validation/promotion must precede loading.
The companion JSON manifest supplies every pinned source URL and exact destination.

```powershell
Set-Location 'D:\neighborlend_project\NeighborLend\ep'
New-Item -ItemType Directory -Force '.runtime/models/weights' | Out-Null
curl.exe --fail --location --proto '=https' --proto-redir '=https' --max-filesize 41000000 --output '.runtime/models/weights/efficient_sam_vitt.pt.part' 'https://raw.githubusercontent.com/yformer/EfficientSAM/d525f622e6f640acf5a0fc37c7ca1f243da5bde0/weights/efficient_sam_vitt.pt'
curl.exe --fail --location --proto '=https' --proto-redir '=https' --max-filesize 89000000 --output '.runtime/models/weights/dinov2_vits14_pretrain.pth.part' 'https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth'
```

After authorization, the download implementation must use the fixed manifest, enforce
destination containment and size limits, reject unsafe source paths/redirects, validate
available Git identities, record SHA-256 and atomically promote complete files. Never
import a partially downloaded module or load an unvalidated checkpoint. No full source
archive or embedded extra checkpoint is authorized by this plan.

## Actual Phase 1 integration constraints

- `pipeline/interfaces.py` defines nine stages, including future damage verification,
  fusion and reporting. `Orchestrator.run` requires all nine. Phase 2 must introduce an
  explicit CV-only execution path using the real first-stage contracts; it must not fill
  LLM stages with fake successful adapters.
- `Repository.transition` always rejects `completed`. Existing regression tests assert
  this guard. A successful CV sub-result must not pretend full inspection/LLM analysis
  completed. Define explicit stage-level result persistence and completion semantics,
  with schema migration/recovery tests before any necessary state change.
- Existing `InspectionService` validates same-rental, before/after selections and both
  original/derivative hashes. Worker execution must repeat authorization, evidence
  selection and integrity checks, then load normalized derivatives through private storage.
- `LocalStorage` currently handles only original/normalized images; startup recovery
  enumerates its dedicated evidence directory. Derived masks/crops/overlays need a
  separate private artifact adapter/directory and metadata references, so evidence recovery
  never mistakes CV artifacts for orphan uploads.
- Existing protected routes, raw-body upload behavior, error envelopes, CORS defaults,
  request IDs, isolated tests and 85% coverage gate must remain intact.

## Implementation sequence after approval

1. Write versioned concrete CV package/artifact/quality/segmentation/embedding/match/
   alignment/candidate contracts and behavioral/failure tests first.
2. Implement measured image quality with versioned configurable thresholds; use real
   contrast/exposure/focus/clipping measures and reject corrupted/unusable inputs.
3. Implement lazy EfficientSAM-Ti with explicit per-evidence target boxes/points. Missing
   target selection or multi-object ambiguity is inconclusive; largest-area selection
   cannot identify the rental object. Check mask shape/type/finite values/area/coordinates.
4. Implement deterministic DINOv2-S/14 preprocessing and finite unit-norm embeddings.
   Combine embedding similarity with local features/geometry/visible-detail consistency;
   return uncertain identity when evidence is insufficient, never a fabricated probability.
5. Rank multi-view pairs independently of upload order; verify with SIFT/ORB descriptor
   filters and RANSAC, track unmatched views and contradictory/unsupported regions.
6. Validate geometry, inliers, warp stability and mask intersection; exclude invalid
   overlap and reject degenerate/non-planar unsupported comparisons.
7. Implement SSIM/regional/edge-change candidates only inside valid overlapping masks,
   with configurable illumination handling, artifact removal, coordinate mappings and
   private diagnostic overlays/crops. Candidates remain visual changes, not proven damage.
8. Connect explicit worker execution, typed errors, authorization/integrity, private
   artifact/result persistence, cancellation/timeouts, concurrency bounds and restart
   recovery. Avoid GPU work in synchronous HTTP handlers; document local queue durability.
9. Add manifest/hash/split validation and label-aware metrics, plus real-inference and
   latency/RAM/VRAM measurement tools. Keep mocked failure tests and genuine inference
   results separate. Never derive ground truth from a model's own output.
10. Run every original/new test, full coverage, Ruff, genuine pretrained CUDA/CPU checks,
    end-to-end demonstrations and boundary verification. Generate all five requested
    Phase 2 architecture/testing/benchmark/integration/model reports from actual results.

## Explicit prerequisites and currently blocked claims

Native Windows model compatibility, segmentation usefulness, DINO embeddings, end-to-end
CV results, GPU/CPU latency and peak memory are not yet measured. Current free RAM was
only about 0.52 GiB during audit; resource preflight must recheck before loading models.
The 8 GB GPU's free memory does not guarantee model fit or acceptable latency.

EP has no real labeled physical-object image sets, only synthetic decoder samples.
Empirical accuracy validation is blocked until consented/provenanced real data with
independent annotations is supplied or an explicitly documented suitable dataset is
obtained. Real inference demonstrations must disclose their image provenance and any
synthetic transformations; they cannot be reported as physical-damage accuracy tests.
Do not tune thresholds on the final held-out split or fabricate labels to fill this gap.

No Gemini, financial settlement, deposit deduction, frontend or production backend
integration belongs to this phase. Stop after Phase 2 once its actual verification gate
passes, or report remaining blocked requirements truthfully.
