# Gemini assessment adapter

Added 2026-11-08. Direct Google Gemini REST compatibility uses the already installed
HTTPX client, without a vendor SDK, dependency changes or a new assessment schema.
**No live Gemini request has been authorized or executed for this change.** Verification
uses synthetic images and HTTPX MockTransport responses only.

## Configuration and consent

Export settings in the native Windows API/worker environment; EP does not load dotenv
files. Configure before queue creation. Leave external processing disabled until a
separate live-call authorization and evidence-consent review.

| Variable | Meaning |
| --- | --- |
| `EP_VLM_PROVIDER` | Explicit `gemini`; default remains `disabled`. `mock` and `json_http` remain supported. |
| `GEMINI_API_KEY` | Gemini credential, read from the process environment only. Never put it in a CLI argument or report. |
| `EP_VLM_MODEL` | Explicit bare `gemini-*` model ID supporting images and structured JSON. No model is selected or downloaded automatically. |
| `EP_VLM_ENDPOINT` | Leave unset; Gemini fixes the official HTTPS URL from the validated model ID. Only that exact URL is accepted if supplied. |
| `EP_VLM_ALLOW_EXTERNAL` | Must be exactly `1` for external provider configuration; unset/default denies it. |

An assessment request must independently set `allow_external=true`; its default remains
false. Without request consent, no image preparation or provider call occurs. A credential
alone never selects or enables Gemini. `EP_VLM_API_KEY` continues to belong to the JSON
gateway and does not substitute for `GEMINI_API_KEY`. Missing credentials, malformed model
IDs and endpoint overrides fail closed. Existing timeout, retry and optional explicit
price settings (`EP_VLM_*`) also apply. No root configuration or database is accessed.

## Wire contract and safeguards

The adapter posts to the official `v1beta/models/{model}:generateContent` endpoint with
`x-goog-api-key` in the header, never the URL. It supplies the conservative instruction in
`systemInstruction`, the existing selected evidence manifest as user text, and each
attachment's UUID/source/hash/box metadata immediately before its PNG `inlineData` part.
It requests one JSON candidate, 2048 output tokens and `ProviderReply.model_json_schema()`
as `generationConfig.responseJsonSchema`. These mappings follow Google's
[generateContent reference](https://ai.google.dev/api/generate-content) and
[structured-output contract](https://ai.google.dev/gemini-api/docs/structured-output).
Provider-side JSON Schema support is a subset; the full unchanged local Pydantic schema
and evidence-citation checks remain authoritative regardless of remote enforcement.

Exactly one completed `STOP` candidate with final text is required. Prompt blocks,
non-STOP finishes (including truncation), missing text and malformed envelopes fail
closed. Thought parts are excluded from assessment text. The existing engine rejects
malformed JSON, invented citations, extra financial claims and unsupported findings.
Neither Gemini nor any other provider establishes physical identity, damage causation or
liability. Every report retains human review and `payment_action=none`.

The shared transport preserves TLS verification, disabled environment proxies/redirects,
bounded retries on transient failures, timeouts, a one-MB response limit and refusal of
compressed responses. Existing image/candidate budgets, private storage, authorization,
queue fingerprints and cancellation semantics are unchanged. No tools, URL fetching or
safety-setting overrides are requested. Raw provider errors and credentials do not enter
public reports. No new dependency or model is needed.

Usage maps prompt tokens to input and candidate plus reported thinking tokens to output;
missing usage remains unknown. Cost stays null unless usage and explicit operator rates
are supplied; it is an estimate, not a bill or a guarantee about retries/cached-token pricing.

## Verification

Commands, using PowerShell from `ep/`:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:EP_SYNTHETIC_ONLY = '1'
& $epPython -B -m pytest tests/unit/test_gemini_provider.py tests/unit/test_assessment_providers.py tests/unit/test_assessment_engine.py tests/integration/test_phase34_integration.py -q --tb=short --junitxml=.test-artifacts/gemini-targeted.xml
& $epPython -B scripts/verify.py all --synthetic-only
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
```

Initial test-first run reproduced the missing adapter and missing Gemini consent gate
(39 failures, 18 passes). An intermediate command named a nonexistent integration test
file and collected nothing; it was corrected to the existing Phase 3/4 integration file.
Final targeted run: **82 passed, 0 failed/errors/skipped**, 16.11 seconds. Final complete
`all --synthetic-only` run: **203 passed, 0 failed/errors, 2 skipped**, 40.41 seconds.
Both controlled native pretrained CPU/CUDA cases passed using generated pixels. RAM
preflight reported 5.57 GiB available; existing guards were retained. Ruff lint passed
and its formatting check reported all 87 Python files formatted. No coverage rerun was
requested or performed; historical coverage is not claimed for the new adapter.
Logs/JUnit: `.test-artifacts/gemini-targeted.log`, `gemini-targeted.xml`,
`gemini-full.log` and `all.xml`. The targeted run has one existing Starlette HTTPX
deprecation warning; the full run has seven warnings including existing optional
xFormers notices. No dependencies were installed to suppress them.

Review traced environment selection, consent gates, fixed-host request construction,
bounded response parsing, usage mapping, local schema/citation validation and persistence.
No outstanding defect was identified in this scope. All code/document edits are inside
`ep/`; no tracked repository changes outside EP were reported by Git. Phases 1–4 were
retained, with no CV model/threshold or existing assessment-schema changes.
The synthetic-only audit hook denies excluded exploratory image paths; two legacy tests
using a separate bundled photograph are intentionally skipped. Historical image reports
are preserved and supply no validation evidence.

Live API acceptance, model/account availability and real VLM quality remain unverified.
No accuracy or damage-detection metrics are claimed. A later live test requires separate
authorization and permitted verified image pairs.
