# Phase 3/4 engineering report

2026-11-08, Asia/Calcutta. Implementation and controlled software verification passed.
External VLM execution, production readiness and real-world damage accuracy are unverified.

## A. Implementation

Phase 3 reuses existing mask-aware SIFT/RANSAC alignment and SSIM localization. Added
explicit matching/alignment/overlap metadata; fixed a crash on missing RANSAC support
and checking overlap before boundary erosion. Synthetic tests cover valid correspondence,
weak/missing support, implausible transforms, wrong pairing, masked occlusion and changes.
Similarity and quality thresholds were not tuned or relaxed; no universal mask cleanup.

Phase 4 adds executable evidence preparation, provider abstraction, schema/citation
validation, uncertainty, fusion, reporting, authenticated queue/results, persistence,
idempotent job reuse, cancellation, recovery and an explicit native worker. Default
unavailable and explicit mock paths are functional and honest about execution.
The optional HTTPS JSON VLM gateway is transport-tested with mocks, not live-verified.

## B. Architecture

Existing authorized evidence/CV worker -> validated Phase 3 pairs/candidates/artifacts ->
queued assessment -> deterministic support gates -> bounded selected crops/context ->
provider -> existing final-three stage protocols -> private human-review report.
Missing support blocks image preparation/provider calls. Crops carry UUIDs, source boxes,
frame mappings and hashes. Invented/cross-source citations and unexpected financial fields
fail validation; stored-report citations are revalidated on reads. Original hashes and CV
fingerprints are rechecked before/after processing. Parent inspection status is preserved.
Full API/configuration and privacy contract: [implementation guide](phase-3-4-implementation.md).

## C. Exact authored file changes

All paths are relative to `ep/`; existing untracked work was preserved. No commit created.

| Files | Purpose |
| --- | --- |
| `ep_engine/assessment/__init__.py`, `ep_engine/assessment/contracts.py` | Versioned constrained assessment/observation/options/usage/report models |
| `ep_engine/assessment/engine.py` | Support gates, selected evidence preparation/mapping, strict claim validation, protocol execution |
| `ep_engine/assessment/providers.py` | Disabled/mock/HTTPS JSON adapters; timeout, bounded retry/response, optional usage/cost |
| `ep_engine/assessment/store.py`, `ep_engine/assessment/service.py`, `ep_engine/assessment/api.py` | Private atomic persistence, source/config-bound job reuse, authorization and API |
| `ep_engine/core/data_policy.py` | Milestone path exclusion before child-worker image access |
| `ep_engine/cv/contracts.py`, `ep_engine/cv/geometry.py`, `ep_engine/cv/pipeline.py`, `ep_engine/cv/worker.py` | Additive phase metadata, geometric safeguards, overlap references, data policy |
| `ep_engine/pipeline/orchestrator.py`, `ep_engine/main.py` | Assessment protocol entry point and service/router wiring |
| `scripts/run_assessment_worker.py`, `scripts/verify.py` | Explicit native worker and synthetic-only verification mode/source-only lint scope |
| `tests/conftest.py`, `tests/security/test_phase34_data_policy.py` | Path audit guard, explicit photo skips, isolated provider environment and exclusion tests |
| `tests/regression/test_phase3_safeguards.py` | Controlled geometric/occlusion/abstention regressions |
| `tests/unit/test_assessment_engine.py`, `tests/unit/test_assessment_providers.py` | Evidence, schema, privacy, budgets, uncertainty and mocked transport failures |
| `tests/integration/test_phase34_integration.py`, `tests/integration/test_controlled_native.py` | Four-image workflow, auth/cache/persistence/cancel/rollback, generated-pixel native CUDA/CPU |
| `pyproject.toml`, `README.md` | Test marker/exclusions, already-installed optional HTTPX requirement, current milestone instructions |
| `docs/development-handoff.md`, `docs/phase-3-4-implementation.md`, `docs/phase-3-4-report.md` | Handoff, operator contract and this report |

No backend, frontend, root configuration/CI or existing evaluation report was modified.
The photographs were not read, inspected, hashed, calibrated, changed or used indirectly.
Generated controlled artifacts/logs remain in `.test-artifacts/`; no prior exploratory
artifact supplies validation evidence.

## D. Executed verification

Native PowerShell, from `ep/`:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/verify.py all --synthetic-only
& $epPython -B scripts/verify.py coverage --synthetic-only
& $epPython -B scripts/verify.py lint --synthetic-only
& $epPython -B scripts/verify.py format --synthetic-only
```

Baseline `all`: **112 passed, 2 explicitly skipped**. Focused controlled checks ran
through development; new failure specifications initially reproduced the RANSAC crash,
pre-erosion support issue, persisted citation-tampering gap and incomplete crop mapping.
Each was fixed and its targeted tests passed. Existing Photo tests were inspected in source
before execution and skipped by collection; an audit hook rejects excluded opens before
I/O, and the child CV worker also enforces the excluded-path policy.

Final full `coverage` run: **158 passed, 0 failed/errors, 2 skipped**, 57.36 seconds.
The two skips are the pre-existing bundled-photograph CUDA/CPU cases; this milestone uses
generated pixels instead. No failing test was silently skipped. All original Phase 1 cases
and relevant Phase 2 regressions ran. No excluded-image evaluation script was executed.

Actual combined statement/branch coverage: **92.85260482846252%**, gate **85% unchanged**.
Statements 2,347/2,468 (95.10%); branches 576/680 (84.71%). Remaining gaps are disclosed;
aggregate coverage is not proof of semantic correctness. The 41 existing abstract Protocol
lines remain default-excluded; no new executable application exclusions were added.
Ruff lint passed; formatting check passed for 86 source/test Python files.

Full log: `.test-artifacts/phase34-final-coverage.log`; JUnit/coverage JSON and HTML use
the existing runner locations. Seven retained upstream TestClient/xformers warnings are
not failures. No packages were changed to hide warnings.

A prior final rerun had **2 native failures at the host-memory reserve**, with 156 other
tests passing. The failure log is preserved as `phase34-resource-guard.log`. After free
RAM recovered, the entire final run passed. No memory reserve, similarity threshold or
other guard was weakened, and no application was closed automatically.

## E. Measured execution and efficiency

Controlled generated 256x256 textured shape; no photograph or physical-damage label.
The CUDA case includes a synthetic pixel edit and traverses genuine pretrained CV plus
the explicitly mocked assessment. The CPU unchanged case avoids provider invocation.

| Final controlled case | CV pipeline seconds | Assessment seconds | Provider attempts | Peak Windows working set bytes | Peak Torch CUDA allocation bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| CUDA, synthetic appearance edit | 3.2912 | 0.1128 | 1 mock | 1,481,134,080 | 483,944,448 |
| CPU, unchanged generated pixels | 6.9245 | 0.0019 | 0 | 1,884,532,736 | 0 for CPU work |

CV timing includes lazy model loads inside `CVPipeline.run`, but excludes the preceding
`NativeModels` constructor/Torch import. These are single observations, not throughput or
percentiles. Working-set peaks are cumulative in the shared pytest process; CPU/GPU memory
values are not isolated process comparisons. Torch allocation excludes driver/other-process
memory. The CUDA mock received six unique images totaling 226,772 PNG bytes and correctly
abstained; no genuine VLM inference happened. No-change status is scoped, not no damage.

The four-image API/persistence workflow separately uses deterministic CV adapters and a
mock VLM. Duplicate requests reuse the completed job with one mock call, not a second call.
Images are deduplicated, CV results are reused without recalculating embeddings, and all
provider work is bounded. No global unbounded cache or permanent extra GPU model was added.

Raw current metrics: `.test-artifacts/phase34-{cuda,cpu}-controlled.json` and
`phase34-mock-integration.json`. Real VLM requests: **none**. Real token usage, billable
model calls, cost and Codex token savings are unavailable, not invented. Cost arithmetic
is tested only using explicitly synthetic usage/rates; production estimates remain null
without configured prices and reported usage.

## F. Limits

No genuine VLM assessment or vendor API compatibility was verified. A configured gateway
must implement the documented JSON protocol; no live endpoint/key is presumed. HTTP timeouts
and bounded retries apply, but there is no provider hard-kill subprocess or distributed
queue guarantee. Production authorization/ACLs, consent, retention, operations and complete
inspection/dispute semantics still need reviewed integration.

Image text and provider content are untrusted. Schema/citation gates constrain scope, not
prove that a semantic defect claim is correct. Unknown occlusions, hands, reflections,
nonplanar geometry and segmentation ambiguity need real-data evaluation. No accuracy,
precision/recall, calibrated confidence, liability, repair cost or deduction is claimed.

## G. Remaining work

A separate evaluation milestone must collect newly verified before/after photographs of
the same physical objects, consent/provenance, target masks, visible-view correspondence
and independently reviewed condition/change labels. Lock splits and acceptance criteria
before calibrating. Only an explicitly permitted endpoint and approved test data can verify
live VLM execution. There is no remaining implementation task authorized for this milestone.

## H. Handoff

Read [development-handoff.md](development-handoff.md) and the operator guide, then use the
approved interpreter with `--synthetic-only`; inspect only a failing component if resuming.
API: queue through `/v1/cv-runs/{id}/assessments`, execute using
`scripts/run_assessment_worker.py`, retrieve `/v1/assessments/{id}/result`. Provider defaults
to disabled; `mock` is an explicitly labeled offline development mode. Keep excluded images
and historical artifacts untouched. Stop after Phase 4.
