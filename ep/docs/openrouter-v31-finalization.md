# EP v3.1 OpenRouter finalization: measured results

This campaign is preserved as history. The subsequent
[bounded live-hybrid acceptance](openrouter-v31-hybrid-acceptance.md) validates the
updated citations and documents conservative abstention on geometric scope.

**One live VLM comparison passed strict JSON and source-citation validation. All
17/17 native checks pass with sequential process isolation.**
The hybrid live reply was correctly rejected for missing original-source citations;
the accepted VLM-only reply was separately tested through conservative CV fusion
without another API call. Independent damage accuracy remains unverified and
application integration is not justified.

## Confirmed routing cause and explicit free alternative

The configured `nvidia/nemotron-3.5-super-vl:free` is image-capable and exists.
A synthetic-text diagnostic returned HTTP 404, provider code 404 and sanitized
category `privacy_policy_no_eligible_endpoint`. Thus this configured route cannot
satisfy the required deny-collection policy. The prior 404 was a privacy-route
rejection, not proof that the model lacked vision. No raw provider error prose,
credentials or images were written into diagnostics. Only whitelisted codes and
categories leave the worker. The [model's data notice](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free)
and [routing rules](https://openrouter.ai/docs/guides/routing/provider-selection)
are consistent with that observed category.

Public and account-filtered catalogs had six free vision models. Two lacked JSON
mode; the two Gemma alternatives returned 429; DOTS accepted a synthetic route
probe with `data_collection=deny`, all price caps zero and fallbacks disabled.
The explicit selected model is `dots-studio/dots-3-note-preview:free`.
The backend `.env` was never changed. No real Gemini API call was made; removal of
its key has no effect on this OpenRouter path. Routing acceptance is not an
independent downstream privacy audit or a quality benchmark.

Four bounded synthetic route attempts and the first three authorized image attempts
remain preserved. The first DOTS image round returned two JSON replies and one
timeout. The replies failed the unchanged local contract: missing recapture guidance,
and a no-change reply containing change proposals. They were never scored as valid
model predictions or repaired to fit the schema. The corrected remote schema now
requires all fields, nonempty guidance/uncertainty and explicit safety values, with
clear empty-observation instructions for no-change/uncertain replies.

## Successful live comparison and hybrid safety

After new explicit authorization, one live synthetic schema check passed. Then the
same phone-front originals were sent in VLM-only and hybrid modes, with a total cap
of two image requests, five images maximum, reasoning disabled in the request and
the original 60-second deadline. All price caps remained zero and collection denied.

| Arm | Status | Seconds | Input / output tokens | Reported cost |
|---|---|---:|---:|---:|
|cv_only|completed: replayed_verified_cv_evidence|0.000|N/A / N/A|N/A|
|vlm_only|completed: unverified_visual_interpretation|28.578|3940 / 621|0|
|hybrid|failed: reply_or_evidence_validation|37.000|9014 / 1148|0|

The accepted VLM-only reply used 3,940 input and 621 output tokens, with provider
reported cost $0. It described a possible screen-appearance difference, offered
lighting/different-device alternatives, supplied recapture guidance, and retained
identity=false, human-review=true and payment_action=none. This is an unverified
model opinion, not a condition label or confirmed physical damage.

The 37-second hybrid reply used 9014 input and
1148 output tokens and reported $0, but cited crops
without including both original UUIDs in evidence_ids. The strict citation validator
rejected it. Its full CV report survived as `cv_fallback`. A final prompt/schema
refinement now explicitly requires both originals and enumerates attached source
IDs; that refinement has offline regression coverage and has not been live-retested.

The accepted live VLM-only reply was revalidated against original pixel hashes and
citations, then passed through the current hybrid overlap checks offline. Result:
`claimed_region_outside_verified_overlap`; combined decision `uncertain` and supported change
`None`. Both the CV evidence and VLM opinion
remain reviewable. This is a fusion test using actual live output, not a successful
independent hybrid-model generation. Broad model boxes do not become verified regions.

The accepted reply was also read from its validated cache with no new API call:
1 cache hit, 0.906 seconds. This is one cache reuse
measurement, not a general speedup claim. Cache keys include provider, model, source
pixels, prompt/schema/transport revision, reasoning setting and credential scope.

## Inconclusive CV geometry and memory

Hybrid routing now permits an independent original-image VLM opinion when geometry
is inconclusive, using the same explicit consent and budgets. It attaches a geometry
warning and no unsupported CV proposals. JSON and source citations still validate.
The model opinion remains separate; its supported hybrid change is always unknown.
Fusion independently enforces this even if an upstream prediction is accidentally
positive. Physical identity and confirmed damage remain false and payment_action none.

The eight original native failures were reproduced with a roughly 20 MiB controller.
Initial minimum available RAM was 0.596
GiB, below the unchanged 1.5 GiB host reserve. The direct-model checks refused before
loading weights; launcher failures likewise returned memory_reserve. No user process
was closed or system cache purged. Once RAM recovered, all eight passed in isolated
processes. A subsequent shared-process run passed 15 and refused two child workers
at memory_reserve; retaining the parent Torch/CUDA process increases the resource
envelope. Fresh-process isolation avoids that retained parent working set.

The complete isolated campaign verified the exact original 17 test identities:
**17 passed**. Controller peak was
20.5 MiB, maximum measured child-tree
working set 1.613 GiB, and minimum sampled
available RAM 1.578 GiB. Individual
process execution totaled 211.452 seconds. Failed
and successful XML/measurements remain separate; shared-process failure is not hidden.

Two avoidable wrapper allocations were removed without touching CV: collection arrays
are released before loading the next case (including the audit loop's last image),
and contiguous RGB arrays are hashed through their buffer instead of tobytes().
A 3 MiB generated control measured Python allocation peaks of
3145906 bytes before and
609 bytes after, with identical digests.
These are host-memory improvements, not a GPU speedup or lowered memory requirement.

## Verification, preservation and readiness

| Verification | Passed | Failed | Skipped |
|---|---:|---:|---:|
|regression-final.xml|329|0|2|
|policy.xml|2|0|0|
|observer.xml|1|0|0|
|native-complete.xml|15|2|0|
|Complete isolated native campaign|17|0|0|

The shared-process `native-complete.xml` refusals are preserved alongside the passing
isolated campaign. All early XML, process measurements and full test records are
retained in the private artifact directory and `acceptance.json`.
The opt-in synthetic data policy checks are run separately from general regression.
All 17 frozen exact-repeat controls retain scoped negative CV predictions
and zero coarse/boundary/original-tile proposals. All 56 archived
strict reports retain payment_action none. Current fusion tests cover unverified
identity, disagreement, missing credentials, financial invariance, prompt/citation
rules, disabled-provider silence, caching, retries and timeouts.

All 58 frozen EP source files and 34 original photograph hashes
match. CV models, thresholds, contracts, original evidence, application, payments,
Supabase and Git history are unchanged. No heavyweight download occurred.

**Suitable for bounded private standalone engineering review; application integration
is not justified.** There are no independently reviewed condition labels, no paired
validated live hybrid benefit, and no calibrated confidence or physical identity.
The tested free preview route may change or disappear. Local privacy/cost controls
and graceful fallback remain mandatory. The final citation-request refinement is
offline verified only; it has not been used to relabel the rejected live reply.

See [architecture and operator instructions](openrouter-v31.md). Actual reports and
receipts are private under `.test-artifacts/openrouter-finalization-20261111/`:
`validated-live/phone-front-vlm_only.json`, `validated-live/phone-front-hybrid.json`,
and `validated-live-reply-hybrid-replay.json`. Reproduction of native checks:

```powershell
& $epPython -B scripts/verify_native_isolated.py --campaign complete --all
& $epPython -B scripts/report_openrouter_finalization.py
```

Existing API campaign ledgers are exhausted. Rerunning diagnostics cannot silently
reset them; new image requests require new bounded authorization.
