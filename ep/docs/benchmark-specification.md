# Future AI benchmark v1 — specification only

No model has been evaluated in Phase 1. No physical-object labels, ground-truth damage
annotations or accuracy numbers have been fabricated. Decoder fixtures are synthetic
pixels solely for software tests and must never be counted as this benchmark.

Store a versioned manifest as JSON Lines under an approved private location inside EP
for local work. Each record must contain: `schema_version`, `case_id`, `rental_context`,
`object_instance_group`, `category`, `scenario_tags`, `before` and `after` view arrays
(each evidence UUID, original SHA-256, orientation-corrected dimensions, unverified
capture metadata), `annotation_status`, nullable `ground_truth`, and provenance/consent
information. No production personally identifying information belongs in exported data.

`ground_truth` remains null until actual independent review. Once reviewed, record:
verified same/different/unknown physical identity, comparable surface/view pairs,
pre-existing versus new damage, category/severity, per-view boxes/masks in normalized
orientation-corrected coordinates, visibility/occlusion, physical-inspection basis,
annotator IDs, disagreements, adjudication and unresolved uncertainty. Model output must
never become ground truth just by being copied into the annotation field.

Required scenario strata:

| Scenario | Evaluation question |
| --- | --- |
| Identical before/after objects with unchanged condition | False positive damage rate on comparable surfaces |
| Same object under different lighting | Robustness to shadows, exposure and reflections |
| Different camera angles | Correct viewpoint matching and abstention when unmatchable |
| Different backgrounds | Background independence |
| Scratches | Localized subtle surface damage; distinguish reflection/texture |
| Cracks | Visible structural discontinuities |
| Dents | Geometry/lighting ambiguity |
| Missing components | Verified absence versus occlusion/out-of-frame view |
| Pre-existing damage | Avoid relabeling existing damage as new |
| Different physical objects of the same category | Avoid confusing similarity with identity |
| Blurry or partially obscured images | Quality gating and justified abstention |
| Insufficient reference views | Inconclusive result for previously unobserved regions |

Use independent human annotation with adjudication, ideally supported by physical
inspection and controlled recapture. An image alone cannot establish invisible damage.
Cases without defensible truth remain explicitly unknown and are evaluated for appropriate
abstention, not forced into positive/negative labels. Document sampling/class balance and
object-category coverage. Do not decide sample counts or acceptance thresholds after
seeing final test outcomes.

Partition development/calibration/final evaluation by **physical object instance**,
rental session and near-duplicate image groups so no item leaks across partitions.
Model weights remain pretrained/frozen; development data is for adapter/prompt/threshold
selection only, never training/fine-tuning. Lock dataset hashes, splits, prompts,
preprocessing, model/provider versions, decoding parameters and hardware before final
evaluation. Keep the final set hidden from threshold/prompt tuning.

Report stage-level match precision/recall, alignment success, quality rejection, damage
precision/recall/F1 on assessable surfaces, false positives on unchanged/pre-existing
damage strata, localization IoU where annotations justify it, identity confusions,
abstention/coverage, selective error-versus-coverage curves, unsupported citation rate,
human-review rate, latency, peak RAM/VRAM and any API cost. Include per-stratum counts,
unknown labels, missing results/failures and object-group bootstrap confidence intervals.
Never silently drop difficult cases or equate selective accuracy with overall accuracy.

Use deterministic software fixtures to test benchmark loaders, hashes, split isolation,
annotation validation and metric calculations before running real adapters. Compare a
simple baseline, CV-only stages, optional LLM verification and fusion ablations on the same
locked cases. LLM confidence is not a calibrated probability; calibration, if required,
needs held-out verified labels and an explicitly defined scoring method. Reports should
link every finding to evidence and require human review; no benchmark authorizes liability.
