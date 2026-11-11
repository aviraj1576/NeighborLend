# Phase 2 delivery report

## A. Executive summary

The connected native Windows CV implementation and software verification gate passed.
Both approved pretrained models executed on CUDA and CPU, and five real API-to-worker
smoke comparisons ran successfully. Independent real-world accuracy validation remains
blocked; this is not an unconditional claim that all Phase 2 empirical validation is complete.
Work stops after Phase 2.

## B. Model architecture

Explicit target boxes -> EfficientSAM-Ti masks -> DINOv2-S/14 embeddings plus SIFT ->
mutual descriptor matching/RANSAC -> validated overlapping object geometry -> masked
SSIM appearance candidates. Small official pretrained models require no added packages
or custom extension. [Architecture](phase-2-architecture.md), [model audit](phase-2-model-audit.md).

## C. Implementation inventory

[Complete authored-file and approved-model inventory](phase-2-inventory.md).
The original evidence/database/state interfaces remain; main wiring and the explicit
orchestrator CV path are backward-compatible. Shared test fixtures isolate new caches/locks.
No original test case was removed or rewritten. Generated private artifacts are enumerated
in the benchmark packages; model files and hashes have an integrity receipt.

## D. Pipeline demonstration

Actual authenticated uploads, inspections and queued CV runs executed in a native
subprocess, persisted validated results and served authorized PNGs. Unchanged derivative:
zero candidates; synthetic edit: one; synthetic perspective: zero; unusable blur and
textureless returns: inconclusive. Masks, crops, matches, valid overlap, difference maps,
overlays and candidate crops were generated. The synthetic edit overlay was visually
inspected. These are derivatives of one installed photograph, not real damage labels.

## E. Testing

114 passed, zero failed/errors/skipped/blocked automated cases. All original 60 cases
pass; 54 new cases cover CV, access control and failures. Combined statement/branch
coverage is 93.34% against the unchanged 85% gate. Ruff lint and formatting passed.
Actual CUDA/CPU inference is separate from deterministic injected-model tests.
[Full testing evidence, commands and fixes](phase-2-testing-report.md).

## F. Benchmarking

Final five-case wall times: 8.7083–9.4800 seconds; worker peak Windows working set up to
1,522,348,032 bytes; peak Torch CUDA allocation 486,762,496 bytes. Individual stage/load
times, source hashes and numerical outputs are recorded. Quality rejected blur/no texture.
Independent identity/viewpoint/change labels, masks and regions are absent, so empirical
accuracy metrics are blocked. [Benchmark report](phase-2-benchmark-report.md),
[evaluation workflow](phase-2-evaluation-workflow.md).

## G. Security and reliability

Rental authorization and both evidence hashes are rechecked; private UUID artifacts need
matching run membership, complete PNG metadata and hash validation. Unsafe checkpoint
loading, malformed outputs, resource limits, queue/concurrency, cancellation/timeouts,
interruption and rollback paths are tested. A Windows OS lock prevents worker/recovery
races. No reproducible critical software failures remain. Physical identity, nonplanar
geometry, reflections, local authorization, deployment ACLs and uncalibrated thresholds
remain material limitations. No candidate is confirmed damage.

## H. Integration

CV results use separate persistence and state. Parent Phase 1 inspections stay `created`
with analysis unavailable. HTTP enqueues; an explicit local worker executes. There is
no automatic production scheduler or distributed retry guarantee. Versioned packages
retain source citations, rejection reasons, artifacts and limitations for future review.
[Integration and API report](phase-2-integration-report.md).

## I. Environment

Existing approved `neighbourlend_yolo` interpreter, native Windows Torch 2.11.0+cu128 and
RTX 4060. No Phase 2 package installation/change. Exactly 26 authorized source/license/
weight files, 129,383,449 bytes, validated inside `.runtime/models/`. No training,
provider call, additional model download or OS change. Low-RAM attempts safely refused
work; execution succeeded after the user freed memory without weakening guards.

## J. Change boundary

Final Git status reports no path outside `ep/`. Existing untracked EP work is preserved;
no commit, root CI edit, backend/frontend modification or production database operation.
[Machine-readable verification](phase-2-verification.json) compares source hashes,
audited package versions, test/coverage results and all approved model files.

## K. Next steps

Obtain consented independently annotated real object/view/damage collections, lock splits,
evaluate the required strata and calibrate thresholds before any accuracy acceptance.
Phase 3 planning must define reviewed provider evidence/citation input, uncertainty,
consent/retention, actual authorization and full-inspection completion semantics. No such
provider, financial or frontend integration was implemented. Stop at this delivery.
