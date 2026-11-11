# Payment completion and standalone EP v3 report

10 November 2026, Asia/Calcutta. Existing uncommitted/untracked implementation was
preserved. No branches, commits, pushes, remote changes, live credentials, real
transactions, or application-database migrations were made. EP v3 was not
integrated into NeighborLend. Existing production-facing AI modules are unchanged.

## Payment result

The existing lifecycle is implemented and verified offline: immutable accepted
offer terms -> booking -> integer-paise INR rental fee plus deposit -> mock or
Razorpay Test checkout -> authoritative captured-payment verification -> private
handover evidence and two-party acknowledgement -> active rental -> return ->
full/partial deposit refund or frozen dispute -> human-authorized allocation ->
confirmed refund and simulated lender receivable.

The accounting journal is balanced and append-only. Deposits and lender allocations
are simulations, not regulated escrow custody, bank transfers or payouts. A clean
return refunds the deposit; eligible pre-receipt cancellation refunds rent plus
deposit. Damage deductions require exact borrower consent or administrator review
with a reason. AI reports have no financial authority.

This pass hardened provider response shapes and collection limits, resource-specific
provider identifiers, blank secrets, authoritative integer order amounts, and live
order rejection. Journal replays must match the existing booking and exact immutable
allocation. Conflicting reuse no longer silently returns an unrelated posting.
Frontend checkout now shares concurrent script loads, cleans failed loads for
retry, and rejects invalid paise/currency before opening the hosted widget.

Existing tests retain raw-body webhook HMAC, replay/duplicate prevention,
out-of-order event handling, amount/currency/signature checks, authentication and
authorization, capture gating, full/partial/zero refunds, cancellation, dispute
freezes, unauthorized deductions, timeout recovery with the same refund key,
provider reconciliation, stale-dispatch fencing, concurrent SQLite operations,
balanced/immutable journals, and rollback of physical return plus refund intent.
Private evidence, status/history, administrator controls and local mock demonstrations
remain functional.

Setup and exact demo steps remain in
[payment-system-verification.md](payment-system-verification.md). Keep
`PAYMENT_PROVIDER=disabled` by default. Local mock requires
`PAYMENT_PROVIDER=mock`, `PAYMENT_DEMO_MODE=true`, and direct loopback exposure.
The existing three-role seeder refuses to overwrite an existing demo database.

For later Razorpay Test Mode, privately configure the existing names:
`PAYMENT_PROVIDER=razorpay_test`, `RAZORPAY_KEY_ID=rzp_test_...`,
`RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`. Test credentials select the
official fixed API host; live keys are rejected, and secrets stay server-side.
Register `/api/payments/webhook` with the same webhook secret.

**Still credential-dependent:** actual hosted checkout, dashboard capture policy,
gateway order/payment reads, real sandbox webhook delivery/redelivery, and sandbox
full/partial refund creation, failures and reconciliation. No such request was
made or claimed successful. Adapter tests replace transport only.

## EP v3 implementation

The [v3 execution guide](../ep/docs/ep-v3.md) covers architecture, dependencies,
configuration, manifests, commands, limits and failure handling. The independent
entrypoint is `ep/scripts/run_v3.py`; the existing v2 routes and wire envelope remain
available. Its wrapper always records `payment_action=none`, human review and
unverified physical identity.

The pipeline preserves unenhanced quality checks, EfficientSAM mask-candidate
validation, rotation-pooled whole-object DINOv2, and CPU RootSIFT. V3 adds bounded
content/weight-bound CPU embedding caching; optional verified local LoFTR inference;
shared bidirectional, distributed geometric verification; explicit GPU geometry
and warp alternatives; and FP32 CUDA SSIM/appearance analysis. Foreground endpoint
filtering, duplicate removal, correspondence caps, degeneracy rejection, model
selection and overlap checks precede comparison. Valid RootSIFT evidence survives
optional model failures. OOM fallback is explicit; unrelated errors are not hidden.

When the reference must be enlarged, v3 compares appearance at the coarser reference
sampling density, then maps evidence back to target coordinates. Fine detail absent
from the reference is explicitly unassessable. This fixes the measured high-resolution
false proposals without changing quality or difference acceptance thresholds.

Segmentation/embedding models execute sequentially and unload before learned
matching. Image bounds, a separate learned-matcher resolution cap, inference mode,
RAM/VRAM reserves, cleanup, worker locking and subprocess deadlines control resources.
AMP remains disabled. CPU geometry, connected components, masks and boundary analysis
remain part of this hybrid pipeline; execution is not described as entirely GPU.

Kornia 0.8.2 and kornia_rs 0.1.10 were installed only into the ignored
`ep/.runtime/v3-packages` directory. The existing Torch 2.11.0+cu128 environment and
26-file audited model store were preserved. The optional upstream LoFTR checkpoint
is separate, checksum-bound and loaded with `weights_only=True`; no inference-time
download occurs. LightGlue was not installed or evaluated. LoFTR supplies the
requested optional learned-matcher path; no LightGlue performance claim is made.

## Actual performance measurements

RTX 4060 Laptop GPU, 8 GB VRAM; native Windows Python 3.11.16; OpenCV 5.0.0.
Numbers below are synchronized wall-clock medians including transfers/CPU portions,
after two warmups, on a deterministic 768x768 technical control. Seven measured
samples per kernel; five per matcher/feature-stage comparison. They are not
production latency percentiles or broad workload guarantees.

| Operation | CPU | GPU | Decision |
| --- | ---: | ---: | --- |
| Image alignment | 7.84 ms | 12.78 ms | OpenCV default; CUDA optional |
| Appearance analysis | 59.65 ms | 9.63 ms | CUDA default, about **6.2x** faster on this control |
| Geometric verification | 2.89 ms | 26.61 ms | OpenCV default; Kornia experimental |

Warp overlap IoU was 1.0; mean absolute pixel error was 0.00408 intensity levels.
Appearance maps differed by at most 0.000001192; candidate boxes and areas matched.
GPU RANSAC retained the same 276 inliers as CPU on the geometry comparison, with
slightly larger symmetric reprojection error (0.158 vs 0.089 pixels). It offered
no demonstrated speed or quality advantage on that control.

| Matcher on the same perspective control | RootSIFT | LoFTR |
| --- | ---: | ---: |
| Filtered matches / verified inliers | 218 / 218 | 3,024 / 3,024 |
| Inlier ratio | 1.0 | 1.0 |
| Minimum spatial coverage | 0.9495 | 0.9664 |
| Symmetric median reprojection error | 0.0869 px | 0.4662 px |
| Warm matching / verification | 35.86 ms | 233.25 ms |
| First matching call | 37.69 ms | 690.58 ms, including model load |

RootSIFT's separately measured two-image feature stage was 278.02 ms; its matcher
column excludes that stage. LoFTR's column includes learned feature processing.
These columns therefore must not be misrepresented as equal end-to-end work.
LoFTR supplies denser support but a less precise warp here. The final selector
retains RootSIFT on this control; LoFTR stays opt-in for weak geometry or explicit
comparison. Dense count alone does not establish a better alignment.

In the 12-case full photo replay, median pipeline wall time was 2.464 seconds for
baseline and 3.034 seconds for v3 with **forced comparison of both matchers**. This
configuration is slower overall; no general end-to-end speedup is claimed. Normal
v3 operation leaves learned matching disabled unless explicitly configured, then
uses it selectively for weak geometry.

Largest measured process peak across the kernel/native sessions was
2,180,796,416 bytes (2.03 GiB). Peak Torch allocation was 945,297,920 bytes
(901.5 MiB); reserved peak was 1,340,080,128 bytes (1,278 MiB). Final native replay
alone peaked at 1,987,817,472 bytes process working set and 742,136,320 bytes CUDA
allocation. These are process/Torch observations, not whole-device peaks. No actual
OOM occurred in these runs; OOM handling was additionally verified by fault injection.

## Evaluation outcomes and remaining defects

There is no adequately reviewed physical-damage holdout. Existing manifests mark
physical identity and condition labels unresolved/unlabelled. **Real damage
precision, recall, false-positive and false-negative rates are therefore unavailable.**
Synthetic image operations are documented controls, not verified damaged-object
photographs. Abstention is never counted as successful damage detection.

| Final matched control | Baseline | V3 |
| --- | --- | --- |
| Sharp unchanged photo | Comparable, 0 proposals | Comparable, 0 proposals |
| Thin line edit | Comparable, 0; edit missed | Comparable, 0; edit missed |
| Patch removal edit | Comparable, 1 appearance proposal | Comparable, 1 appearance proposal |
| Patch displacement edit | Comparable, 1 appearance proposal | Comparable, 1 appearance proposal |
| Quarter-turn unchanged | Comparable, 0 proposals | Comparable, 0 proposals |
| Moderate perspective unchanged | Comparable, 0 proposals | Comparable, 0 proposals |
| Global lighting change | Comparable, 0 proposals | Comparable, 0 proposals |
| Poor focus | Inconclusive | Inconclusive |
| Occlusion edit | Comparable, 1 appearance proposal | Comparable, 1 appearance proposal |
| Cropped object | Comparable visible region, 0 proposals | Comparable visible region, 0 proposals |
| Different photo | Inconclusive | Inconclusive |
| Unchanged 768-to-1024 resolution | **20 false appearance proposals** | **0 proposals after sampling fix** |

Both versions yielded appearance proposals on two of three programmed edit cases;
both missed the thin line on this photograph. This is a control outcome, not damage
recall. The occlusion proposal demonstrates unresolved causation. Cropped visible
region comparison does not certify the complete item. Boundary-only hypotheses
remain conservative; existing regressions cover missing tabs, displaced silhouettes,
mask jitter without pixel change, crop rejection and photometric corroboration.
Generated CUDA tests separately verify thin scratch/crack-like connected regions,
pre-existing marks, global lighting, quarter turns, footprints and CPU/GPU parity.

The supplied rental collection contains **42 images across seven object groups**,
including six smartphone images. All 42 remain quality-rejected in baseline and
v3. Source, 768 and 1024 quality audits give the same focus range, 2.735–20.122,
below the unchanged threshold 25. These files already fit within 768 pixels;
resizing is not the explanation. Visual inspection shows softness/low-texture and
glare in phone views, but no independently reviewed focus labels establish which
rejections are erroneous. No sharp image was declared falsely rejected without
such evidence, and no safeguard was lowered to make this collection pass.

**AI integration recommendation: NOT READY** for automated physical-condition,
liability or financial decisions. The standalone experimental engine is usable for
further human-supervised evaluation. Reviewed original matched captures, target
masks, visibility/view labels, condition regions and an independent object-level
holdout are required before integration. No new application integration was made.

## Verification

| Check | Result |
| --- | --- |
| Backend: `python -B scripts/verify_payments.py` | **128 passed, 3 skipped**, 87.65 s; no failures |
| Frontend: `npm test` | **25 passed**, no failures |
| Frontend: `npm run build` | Passed, 1,656 modules |
| EP full suite with real/controlled/v3 CUDA flags | **256 passed, 2 skipped**, 74.56 s; no failures |
| The two EP policy checks in synthetic-only mode | **2 passed** separately |
| Final native baseline/v3 photo replay | **24 runs, 0 execution failures**; algorithm misses listed above |
| EP full Ruff lint and formatting | Passed |
| Changed payment modules/tests Ruff lint and formatting | Passed |
| SQLite migrations, repeat migration and transaction rollback | Passed in isolated backend tests |
| PostgreSQL migrations/locking/refunds | Not executed: local service unavailable; three explicit skips |
| Existing image/model integrity | All 42 original hashes unchanged; existing 26-file model store verified |
| Razorpay sandbox | Not executed: credentials unavailable |
| Dedicated static type checker / browser automation | Not configured / not executed; no claim of either |

Native tests exercise actual CPU and CUDA pretrained models, private API/worker
flow and advisory outputs; HTTP provider boundaries remain mocked. Existing
Starlette/HTTPX deprecation and disabled/unavailable xFormers warnings remain.
Initial v3 verification found a float64 correspondence conversion issue; it was
corrected and regression-tested. Intermediate high-resolution failures and earlier
benchmarks are retained rather than relabelled as passes.

## Files and evidence

Files changed by this execution, relative to `NeighborLend/`:

| Files | Purpose |
| --- | --- |
| `backend/app/services/razorpay_service.py` | Provider validation and safe response handling |
| `backend/app/services/payments.py` | Strict authoritative order amount/type and mode checks |
| `backend/app/services/escrow_service.py` | Exact immutable journal replay validation |
| `backend/tests/test_payment_v3_hardening.py` | Eight provider/journal financial regressions |
| `frontend/src/components/paymentFlow.js`, `payments.test.js` | Concurrent loader recovery and money checks, two tests |
| `ep/ep_engine/cv/pipeline.py` | Protected operation hooks; unchanged v2 default operations |
| `ep/ep_engine/v3/{__init__,config,gpu,matching,pipeline,worker}.py` | Independent v3 implementation |
| `ep/scripts/{fetch_v3_loftr,run_v3,benchmark_v3,report_v3}.py` | Explicit assets, standalone worker, benchmark, gallery |
| `ep/tests/unit/test_v3.py`, `ep/tests/integration/test_v3_cuda.py` | 17 safety/behavior and nine actual GPU parity cases |
| `ep/pyproject.toml` | Optional pinned v3 dependencies |
| `ep/docs/ep-v3.md`, both READMEs, `docs/payment-system-verification.md`, this report | Setup, architecture, measured results and limitations |

Private local evidence:

- [Final visual comparison gallery](../ep/.test-artifacts/v3-20261110-03/index.html).
- [Final per-case stages, geometry, timing and source review hashes](../ep/.test-artifacts/v3-20261110-03/comparison-summary.json).
- [Final full native packages](../ep/.test-artifacts/v3-20261110-03/native.json).
- [Kernel/matcher measurements](../ep/.test-artifacts/v3-20261110-02/kernels.json).
- [42-image source-resolution quality audit](../ep/.test-artifacts/v3-20261110-02/quality-audit.json).
- [Image/model integrity result](../ep/.test-artifacts/v3-20261110-03/integrity.json).
- [Standalone CLI high-resolution replay](../ep/.test-artifacts/v3-high-resolution-fix-01/result.json).
- [Backend JUnit](../backend/.payment-verification/backend.xml),
  [EP JUnit](../ep/.test-artifacts/all.xml), [policy JUnit](../ep/.test-artifacts/v3-policy.xml).

The first two v3 benchmark directories preserve pre-fix behavior. Existing earlier
evaluation folders, models, checkpoints and datasets were retained. Runtime
packages, weights and private evidence remain ignored local assets.
