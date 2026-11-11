# Phase 2 implementation inventory

Paths below are relative to `ep/`. Original baseline work was untracked and preserved.

## Modified original files

- `README.md`
- `docs/api-contract.md`
- `docs/testing-report.md`
- `ep_engine/main.py`
- `ep_engine/pipeline/orchestrator.py`
- `pyproject.toml`
- `scripts/verify.py`
- `tests/conftest.py`

## New source and documentation files

- `docs/phase-2-architecture.md`
- `docs/phase-2-audit-boundary.json`
- `docs/phase-2-baseline-report.md`
- `docs/phase-2-benchmark-report.md`
- `docs/phase-2-evaluation-workflow.md`
- `docs/phase-2-implementation-plan.md`
- `docs/phase-2-installation-plan.json`
- `docs/phase-2-integration-report.md`
- `docs/phase-2-inventory.md`
- `docs/phase-2-model-audit.md`
- `docs/phase-2-report.md`
- `docs/phase-2-testing-report.md`
- `docs/phase-2-verification.json`
- `ep_engine/cv/__init__.py`
- `ep_engine/cv/api.py`
- `ep_engine/cv/artifacts.py`
- `ep_engine/cv/assets.py`
- `ep_engine/cv/changes.py`
- `ep_engine/cv/concurrency.py`
- `ep_engine/cv/contracts.py`
- `ep_engine/cv/evaluation.py`
- `ep_engine/cv/geometry.py`
- `ep_engine/cv/models.py`
- `ep_engine/cv/pipeline.py`
- `ep_engine/cv/quality.py`
- `ep_engine/cv/service.py`
- `ep_engine/cv/store.py`
- `ep_engine/cv/worker.py`
- `scripts/audit_phase2_environment.py`
- `scripts/audit_phase2_weight_headers.py`
- `scripts/benchmark_phase2.py`
- `scripts/evaluate_phase2.py`
- `scripts/fetch_phase2_models.py`
- `scripts/probe_phase2_models.py`
- `scripts/run_cv_worker.py`
- `scripts/verify_phase2_boundary.py`
- `tests/integration/test_cv_pipeline.py`
- `tests/integration/test_cv_real.py`
- `tests/integration/test_cv_service.py`
- `tests/security/test_cv_assets.py`
- `tests/security/test_cv_checkpoint_loading.py`
- `tests/security/test_cv_output_validation.py`
- `tests/unit/test_cv_evaluation.py`
- `tests/unit/test_cv_geometry_changes.py`
- `tests/unit/test_cv_model_contracts.py`
- `tests/unit/test_cv_quality.py`
- `tests/unit/test_cv_worker_failures.py`

## Approved runtime downloads

- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/LICENSE`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/__init__.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/hub/__init__.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/hub/backbones.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/hub/utils.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/__init__.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/attention.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/block.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/dino_head.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/drop_path.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/layer_scale.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/mlp.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/patch_embed.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/layers/swiglu_ffn.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/models/__init__.py`
- `.runtime/models/source/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/models/vision_transformer.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/LICENSE`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/__init__.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/build_efficient_sam.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/efficient_sam.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/efficient_sam_decoder.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/efficient_sam_encoder.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/mlp.py`
- `.runtime/models/source/efficientsam-d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam/two_way_transformer.py`
- `.runtime/models/weights/dinov2_vits14_pretrain.pth`
- `.runtime/models/weights/efficient_sam_vitt.pt`

All downloaded hashes are in `.runtime/models/integrity.json`. Generated test reports/caches and isolated databases are under `.test-artifacts/`. Benchmark PNG UUIDs and hashes are enumerated in its individual package JSONs. Runtime worker locks/model caches stay under `.runtime/`. These generated data directories are excluded from the authored-source inventory and Git.
