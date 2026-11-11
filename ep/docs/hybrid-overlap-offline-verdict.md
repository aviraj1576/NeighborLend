# Offline investigation of the preserved hybrid abstention

Verdict: **correct conservative abstention caused by unsupported VLM localization**.
No coordinate conversion, transform direction, mask-frame, crop-binding, or region-gate
implementation defect was confirmed. No production code or thresholds were changed.
The observations are model interpretations, not verified damage findings.

The preserved response is
`.test-artifacts/openrouter-hybrid-acceptance-20261111/live/provider-result.json`,
SHA-256 `c08c318be25b7c7c00c42aa826a10d67bbc3ff3bf0c5bd0988e809c16377a417`.
Both observations use exactly the same broad source-image boxes despite describing
different features. They fail independently with
`claimed_region_outside_verified_overlap`.

| Frame | Original dimensions (W x H) | Processing dimensions | Unchanged normalized VLM box | Original-image box (x1, y1, x2, y2) |
|---|---|---|---|---|
| Before | 724 x 1600 | 348 x 768 | [0.39, 0.19, 0.98, 0.68] | [282.36, 304, 709.52, 1088] |
| After | 1864 x 843 | 768 x 347 | [0.31, 0.32, 0.75, 0.79] | [577.84, 269.76, 1398, 665.97] |

Original coordinates are continuous box edges. The gate uses floor for lower edges
and ceil for upper edges in the processing raster, without cropping the claim to
supported pixels.

| Assessed box, identical for both observations | Processing rectangle, exclusive upper edges | Supported / assessed pixels | Unsupported pixels | Supported fraction |
|---|---|---|---|---|
| Before, inverse-warped verified mask | [135, 145, 342, 523] | 60,242 / 78,246 | 18,004 | 76.990517% |
| After, verified mask | [238, 111, 576, 275] | 44,361 / 55,432 | 11,071 | 80.027782% |

The after box fails first in the implementation. Independently measuring the before
box shows that it also fails the full-support requirement. A positive claim needs
every assessed pixel of both boxes supported; the presence of some supported pixels
or an intersection between projected rectangles is insufficient.

The saved homography maps **before processing pixels to after processing pixels**:

```text
[-0.044653146410, -0.830937589042, 655.286760135993]
[ 0.669722111779, -0.029388898469,  10.572535256717]
[-0.000116174329, -0.000430144324,   1.000000000000]
```

The exact full-precision values are retained in the diagnostic JSON. The before
box corners project into normalized after coordinates approximately as follows:

```text
(0.746060, 0.303922), (0.752586, 0.753475),
(0.364764, 0.875928), (0.369025, 0.326730)
```

The projected bounds intersect the proposed after box, but do not imply full
common-surface support. Dimension-scaled original/processing projections agree
within 1.14e-13 processing pixels; applying the inverse homography recovers the
corners within 3.42e-13 processing pixels. These are numerical consistency checks,
not independent physical ground truth. The saved symmetric reprojection error is
1.360445 processing pixels, and the saved geometry passes the existing verifier.

The overlap artifact `1f3a661e-1fc9-42d4-ae26-fed53c390841` is a 768 x 347 binary
mask in the after processing frame, not an image crop. Reconstructing it from the
saved segmentation masks using the saved forward homography, nearest-neighbor
mask warping, intersection, and the existing 9 x 9 erosion gives **zero differing
pixels**. Its inverse warp supplies the before-frame support mask.

The limitation is larger than a rasterization or erosion boundary effect:

- 6,985 after-box pixels lie outside the saved after-object segmentation.
- 7,260 after-box pixels lack raw common overlap, even before erosion.
- Erosion excludes a further 3,811 after-box pixels, yielding 11,071 unsupported pixels.
- 9,093 before-box pixels lie outside the saved before-object segmentation.

Visual inspection of the overlays confirms that the VLM rectangles include phone
border and surrounding fabric beyond verified support. The model did not provide
separate, tightly localized boxes for its claimed shattered corner and diagonal
line. This is a model region-localization limitation relative to the available
verified evidence. It does not establish that a more specific observation would
be supportable, that segmentation is perfect, or that the proposed damage occurred.

All five reconstructed attachments match their saved receipt dimensions and PNG
hashes, including both original-resolution captures. Both attached candidate
crops match the source processing-image pixels at their recorded candidate boxes
and have the correct source bindings. Citation validation passes. There is no
evidence of exchanged axes, pixel versus normalized units, unintended source
resizing, a crop-local box interpreted as an original-image box, or reversed
homography use in this replay.

Only an offline audit script, regression tests, and this report were added. The
VLM boxes were not clipped or repaired; no observations were promoted. No new API
calls, inference, model downloads, or changes to application/payment behavior were
made. All 13 files under the preserved live directory, including its cache and
one-request ledger, remained byte-identical across the audit and replay.

Verification: **61 tests passed**, including eight new tests covering independent
replay of both live observations, exact mask reconstruction and support counts,
coordinate mapping, receipt/crop pixel provenance, conservative fusion, and
generated controls checking rejection in either source frame. The preserved
response tests block socket access and provider-worker creation. Existing provider
regressions use mocked transports. No external provider was contacted.

Reproduce from `ep/` with the documented Conda interpreter:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/audit_hybrid_overlap.py --output .test-artifacts/hybrid-overlap-offline-20261111
$env:EP_RUN_HYBRID_REPLAY = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& $epPython -B -m pytest tests/regression/test_hybrid_overlap_replay.py tests/regression/test_vlm_evaluation.py tests/regression/test_openrouter.py --basetemp=.test-artifacts/hybrid-overlap-offline-20261111/pytest-tmp --junitxml=.test-artifacts/hybrid-overlap-offline-20261111/regressions.xml -q
```

New private artifacts are in `.test-artifacts/hybrid-overlap-offline-20261111/`:
`diagnostics.json`, `before-overlap.png`, `after-overlap.png`, and `regressions.xml`.
Green shows verified support; red shows the unchanged boxes shared by both
observations. The earlier `validation-details.json` remains at the acceptance
campaign root, not inside its `live/` subdirectory, and agrees with these counts.

The final combined decision remains **uncertain**, supported prediction **null**,
confirmed damage **false**, physical identity verified **false**, payment action
**none**, and human review **required**. Standalone human review remains the
engineering verdict; this case supplies no basis for damage or financial automation.
