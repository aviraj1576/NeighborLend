# EP v3.1 final bounded live-hybrid acceptance

The subsequent [offline coordinate and overlap investigation](hybrid-overlap-offline-verdict.md)
confirms correct abstention and a model localization limitation; no implementation
defect was confirmed.

Actual verdict: **completed_with_abstention**. Combined decision: **uncertain**.
Reason: `claimed_region_outside_verified_overlap`. No independently verified damage accuracy or application
integration readiness is established by this single consented engineering example.

One authorized phone-front hybrid request was reserved, with retries disabled.
Model: `dots-studio/dots-3-note-preview:free`. Original images and verified CV crops
were sent with `data_collection=deny`, all price caps zero, no paid/model fallback,
metadata stripping, five-image maximum and the existing configured timeout.
The metadata preflight verifies image/JSON support and zero catalog pricing before
generation. No synthetic generation or additional image request was made.

| Measurement | Actual result |
|---|---|
| Comparison record latency | 35.594 s |
| Provider token usage | `{"candidatesTokenCount": 1146, "promptTokenCount": 9319, "thoughtsTokenCount": 0}` |
| Provider reported cost | 0 USD |
| Local reserved cost | 0.0 USD |
| JSON contract valid | True |
| Required remote fields present | True |
| Source and attached-evidence citations valid | True |
| Supported change prediction | None |

| Observation | Before supported | After supported | Projected boxes intersect | Decision |
|---|---:|---:|---|---|
|0|76.99%|80.03%|True|abstained|
|1|76.99%|80.03%|True|abstained|

Both proposed boxes extend beyond verified overlap. The unchanged region gate requires
all assessed processing pixels in each source box to be supported, not just intersecting
projected bounding boxes. This is the precise remaining localization defect: the model
proposes broad screen regions spanning unsupported pixels. It is not a citation or
coordinate-unit failure. No unsupported appearance observation was promoted.
The detailed per-observation counts, artifact kinds, IDs and source bindings are retained
in private `validation-details.json`; overlap masks are evidence, not crop images.
Normalized coordinates and source frames use the unchanged strict reply contract.
Every positive must cite both originals; all crop references must be attached and
bound to those sources. Geometry and overlap use the existing verification gates.
Any unsupported region abstains; no model box is clipped, repaired, or promoted.

The original CV report remains intact in the combined report and a byte-identical
private evidence copy. All 58 frozen EP source files and 34 original photograph
hashes were verified before and after the call. Payment_action remains none,
physical identity and confirmed damage remain false, and human review is required.
No underlying CV, payment, database, application, model weight or Git change was made.

Affected regression and safety records: `{"affected-regressions.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 53.0, "time": 10.875}, "preflight-recheck.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 2.0, "time": 1.769}, "preflight-tests.xml": {"errors": 2.0, "failures": 0.0, "skipped": 0.0, "tests": 2.0, "time": 0.667}, "privacy-policy.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 2.0, "time": 0.158}}`.
The first preflight XML records two test-directory setup errors; its separate recheck
passed both tests. All 53 affected regressions and both privacy-policy checks passed.
Prior native verification is documented in [finalization](openrouter-v31-finalization.md);
it is not represented as a new native benchmark in this API-only acceptance run.

Actual private outputs are under `.test-artifacts/openrouter-hybrid-acceptance-20261111/live/`:
`combined-report.json`, `acceptance.json`, `provider-result.json` when available,
`request-schema.json`, `request-receipt.json`, `cv-evidence.json`, and the append-only
one-request ledger. Failed outputs are preserved. Re-running a completed campaign
does not make another API call. See [operator documentation](openrouter-v31.md).

**Readiness:** bounded standalone human review only. Independent labels, demonstrated
paired benefit and representative reliability measurements remain absent. This
single case cannot justify application integration or damage/financial automation.
