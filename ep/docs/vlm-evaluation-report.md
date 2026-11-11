# EP v3.1 standalone VLM evaluation: measured report

**Integration is not justified.** The existing available collection has zero
independently reviewed physical-condition or appearance-change labels. The live
pilot is an unlabeled engineering experiment. No damage precision, recall, F1,
localization accuracy or physical-identity accuracy can be reported.

## Executed comparisons

The prepared manifest binds all 56 existing cases to original source-resolution
captures and the refined v3.1 reports. The CV architecture, existing EP source files,
application, payments and databases were preserved. No Git command or operation
was performed. Existing CV comparability remains 8/17 real pairs; the harness has
stricter eligibility for exporting observations and does not change that outcome.

CV-only is verified evidence replay, not fresh model inference or a neural latency
benchmark. VLM-only sees no CV output. Hybrid sees the same original pixels plus
verified CV evidence and cannot override geometry, coverage or positive CV evidence.

| Case | CV-only | VLM-only | Hybrid |
|---|---|---|---|
|phone-front|completed: appearance difference|failed: abstained|failed: abstained|
|repeat-phone-front|completed: no difference in assessed scope|failed: abstained|failed: abstained|
|bag-front|completed: abstained|failed: abstained|completed: abstained|

Every appearance result above remains unverified. A negative is restricted to
assessed visible scope; no result establishes physical identity, physical damage
causation, liability or payment authority. The VLM receives source citations and
normalized boxes, but correct-looking citations do not independently validate its
visual interpretation. Only a future independent labeled study can establish benefit.

## Free-tier API execution

The user explicitly authorized the three named image pairs to Google's Gemini API,
confirmed that the project has billing disabled, and approved the images for unpaid
service processing. No paid fallback or billing change was made. All executed live
configs use zero token prices, a zero-dollar budget and finite per-campaign request caps.
Billing-disabled status is operator-confirmed, not independently verifiable from
an API key. Cost records are local estimates, not a provider invoice.

The first Gemini 2.5 Flash-Lite attempt was rejected at token preflight. A separate
synthetic-text token-count diagnostic returned HTTP 404 and explained that the model
is unavailable to new users, recommending Gemini 3.5 Flash-Lite. Model metadata alone
had returned HTTP 200 and was insufficient as an availability check. The replacement
passed synthetic token counting before the private pilot. Its free tier is documented
by [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

The historical 2.5 rejection ledger remains intact. No generation was issued after
a failed preflight. The replacement pilot uses its own bounded ledger; no automatic
retry, provider switching or paid upgrade exists in the harness. Private images and
their model outputs are subject to Google's unpaid-service terms, explicitly approved
by the user. See [data terms](https://ai.google.dev/gemini-api/terms).

The first six 3.5 generations returned JSON but failed local validation. Their raw
outputs were not retained, so a shared cause across all six is not established.
One subsequently authorized diagnostic captured a 0–1000 coordinate response,
which correctly failed the mandatory 0–1 unit checks. Five remaining authorized
requests with remote numeric constraints returned HTTP 400 and no model replies.
The final compact remote schema keeps complete local validation and is verified
offline only. No additional live requests beyond the authorized allowance were made.

Live final summary: `{"arms": 9, "budget": {"attempts": [{"context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "fingerprint": "70c6fda675db86d50c401996d7cd735e22691d948e22cec40ceee1868495a1c7", "index": 1, "reserved_usd": "0.0"}, {"context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "fingerprint": "c2e0d4066390772786769ed8c49fb27c3e68c97d193f9f56ffe0e411818f4707", "index": 2, "reserved_usd": "0.0"}, {"context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "fingerprint": "2acd72df69ab925596fc32ff7b9f862612a0befa738d44e00dc0dd0520ee64f1", "index": 3, "reserved_usd": "0.0"}, {"context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "fingerprint": "0ae74d4bcd16ca47fd48d285092826bde2f8d7725eb43ede4ce65dd2356c6022", "index": 4, "reserved_usd": "0.0"}, {"context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "fingerprint": "b2f1d1b84a670186c5aa1635b7ee86f9a0f3018b59990a055b30b550029d4eab", "index": 5, "reserved_usd": "0.0"}], "context": "f160fef5da4b7ced47e14aa5bc3211c01ee8605a2720613967d547ff75b80112", "requests": 5, "reserved_usd": "0.0"}, "cases": 3, "credential_available": true, "cv_timing_scope": "CV report verification/replay, not fresh model inference", "independently_labeled_cases": 0, "integration_recommendation": "NOT JUSTIFIED: independent held-out live VLM benefit has not been established", "modes": {"cv_only": {"abstentions": 1, "cache_hits": 0, "live_requests": 0, "median_record_seconds": 0.0, "metrics": {"calibration": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "development": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "software_control": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "test": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}}, "positive_unverified": 1, "statuses": {"completed": 3}}, "hybrid": {"abstentions": 3, "cache_hits": 0, "live_requests": 0, "median_record_seconds": 8.18800000000192, "metrics": {"calibration": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "development": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "software_control": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "test": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}}, "positive_unverified": 0, "statuses": {"completed": 1, "failed": 2}}, "vlm_only": {"abstentions": 3, "cache_hits": 0, "live_requests": 0, "median_record_seconds": 10.203000000001339, "metrics": {"calibration": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "development": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "software_control": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}, "test": {"labelled": 0, "positive_labels_including_abstentions": 0, "recall_lower_bound_including_abstentions": null, "status": "blocked_no_labels"}}, "positive_unverified": 0, "statuses": {"failed": 3}}}, "paired_completed_case_ids": [], "paired_completed_independently_labeled_cases": 0, "physical_damage_accuracy": null, "total_wall_seconds": 49.40600000000268}`.
The [OpenRouter follow-up](openrouter-v31-report.md) contains current wrapper,
provider, regression and native-check results; the records here are historical.

## Offline and safety benchmarks

The complete CV-only cohort and offline fixture cohort both use the same 56 cases.
Offline fixtures return deterministic uncertainty and are excluded from VLM accuracy.
The fixture run tests original-image export preparation, citations, geometry gates,
resource limits and cache persistence; it is not a local VLM or model benchmark.
Over-budget/deadline-skipped requests remain explicitly not run, not successful.

Sanitized per-campaign reason counts: `{"disabled-final": {"provider_unconfigured": 112, "replayed_verified_cv_evidence": 56}, "free-diagnostic": {"replayed_verified_cv_evidence": 1, "reply_or_evidence_validation": 1, "request_budget_exhausted": 1}, "live-free-current": {"replayed_verified_cv_evidence": 3, "reply_or_evidence_validation": 6}, "live-free-final": {"cv_geometry_gate_abstained_without_api": 1, "provider_rejected": 5, "replayed_verified_cv_evidence": 3}, "live-free-pilot": {"provider_rejected": 6, "replayed_verified_cv_evidence": 3}, "offline-fixture": {"replayed_verified_cv_evidence": 56, "request_evidence_budget": 6, "vlm_abstained": 106}}`.

Test records (including preserved early failures): `{"regression-all.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 297.0, "time": 100.822}, "regression-final.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 304.0, "time": 57.424}, "tests-final.xml": {"errors": 0.0, "failures": 2.0, "skipped": 0.0, "tests": 24.0, "time": 24.782}, "tests-first.xml": {"errors": 19.0, "failures": 0.0, "skipped": 0.0, "tests": 19.0, "time": 1.436}, "tests-second.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 19.0, "time": 5.618}, "tests-verified.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 24.0, "time": 7.035}}`.
The final regression suite excludes neural inference markers because this change
does not modify the established CV architecture or model code. Dedicated tests cover
original-pixel fidelity, metadata removal, label blindness, content hashes, invalid
citations, geometry/overlap in both sources, free-only admission, credential handling,
truncated output, redirects/response bounds, worker deadlines, usage, ledger fsync,
interrupted-write recovery, cache corruption, split leakage and abstention metrics.

A real Windows DELETE-sharing refusal during an early benchmark checkpoint exposed
an avoidable rename dependency. Diagnostic JSON snapshots now use one locked writer;
the authoritative spend reservations are append-only, fsynced before any remote call.
A failed snapshot cannot refund a reservation. A torn ledger fails closed. Early
test/benchmark failures are retained separately and are not reported as final passes.

## Decision and remaining requirements

**Keep the standalone harness; do not integrate a VLM into the application yet.**
There are no independently labeled cases, no complete damage-detection study and
no calibrated uncertainty. The pilot's sample is deliberately small and selected
for engineering behaviors, not a representative holdout. Cross-view surfaces,
nonrigid items, lighting/reflections and identity remain unresolved.

Before considering integration, collect independently reviewed matched unchanged,
changed, lighting, pose, occlusion and different-instance cases. Lock object/session
splits, annotations, prompts/model versions and decision criteria before evaluation.
Measure paired error counts, assessed coverage/abstention, localization, latency and
cost with object-group uncertainty intervals. Do not infer damage from unlabeled
appearance differences or use provider availability as quality evidence.

## Reproduction

See [operator documentation](vlm-evaluation.md) and
[free-only configuration](vlm-evaluation-live-config.example.json).
All private manifests, sanitized outcomes, cache entries, schemas, test XML and
reservation ledgers are under `.test-artifacts/vlm-evaluation-20261111/`.
Keys and original-image bytes are not copied into report/cache files.
The supplied key is read only from the explicitly named local key file.
