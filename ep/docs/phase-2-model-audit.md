# Phase 2 model audit — verified native execution

Current status, 2026-11-08: the user approved the exact immutable download manifest.
All 26 source/license/weight files (129,383,449 bytes) downloaded and validated inside
`ep/.runtime/models/`. Both pretrained models imported, initialized, securely loaded
and completed finite native CUDA and CPU forward passes. Connected pipeline tests passed
on both devices, and an authenticated API-to-subprocess comparison executed successfully.
No package or operating-system change was needed. The older review below is historical.

## Approved assets and observed integrity

| Weight | Actual bytes | SHA-256 |
| --- | ---: | --- |
| EfficientSAM-Ti | 40,982,470 | `dff858b19600a46461cbb7de98f796b23a7a888d9f5e34c0b033f7d6eb9e4e6a` |
| DINOv2-S/14 | 88,283,115 | `b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9` |

The 24 pinned Python/license files total 117,864 bytes. Exact sizes and Git blob identities
where available were checked before atomic promotion. All SHA-256 values are recorded in
`.runtime/models/integrity.json`. Subsequent loads verify every asset and reject unexpected
files. Certificate validation stayed enabled and redirects were rejected.

The immutable installation-plan SHA-256 is
`97409ffe16f12908087a724bd1d4adca775247f222340f7b4aa0c64046d6533d`.
Its `awaiting_user_approval` field remains historical so the authorized bytes stay unchanged.
The user's later session approval authorized its execution. EfficientSAM's weight has a
pinned Git identity; DINO's initial trust remains official HTTPS plus size, then recorded
SHA-256. A local receipt is not an independent publisher signature.

## Verified compatibility and loading

The approved `neighbourlend_yolo` interpreter uses native Windows PyTorch 2.11.0+cu128,
TorchVision 0.26.0+cu128 and the RTX 4060 Laptop GPU. No custom CUDA extension is required
by the executed source paths. Optional xformers is explicitly disabled; its warnings
are retained. Only reviewed pinned source is imported, architectures disable implicit
pretrained downloading, `torch.load(weights_only=True, map_location='cpu')` rejects
unrestricted executable checkpoint loading, and finite tensors/strict keys/shapes are
validated before transfer to the device. No unsafe fallback or training was introduced.

CUDA and CPU probes produced boolean `(768,576)` masks and finite unit-normalized
`(384,)` vectors. Real connected 512-side pipeline tests also passed on both devices.
Actual timings, RAM/VRAM and comparison behavior are in `phase-2-benchmark-report.md`;
raw probe results are in `.test-artifacts/phase2-native-probe.json`.

The implemented guard requires 1.5 GiB free host RAM and 2 GiB GPU memory before model
loading, superseding the preliminary estimate below. Actual low-memory attempts stopped
with `memory_reserve`. After the user freed RAM, comparisons succeeded without weakening
the guard. Batch size is fixed at one; models load sequentially. CPU is explicit or
selected by `auto` when CUDA is unavailable; OOM is not silently retried on CPU.

Compatibility and execution are verified. Physical-object identity, segmentation and
damage accuracy remain blocked pending independently reviewed real labels. No additional
download, package installation, model training or provider call occurred.

## Historical pre-approval selection review (superseded status)

Status on 2026-11-08: baseline and environment audit verified; proposed pretrained
downloads await explicit user approval. No Phase 2 inference or installation has occurred.
This document records model-selection reasoning, not a model-performance claim.

## Verified environment

Interpreter: `D:/Anaconda_Install/envs/neighbourlend_yolo/python.exe`, Python 3.11.16.
Windows build reported by Python: `Windows-10-10.0.26300-SP0` (the platform API's label
does not itself distinguish Windows 10 from Windows 11 branding).

| Component | Actual version/status |
| --- | --- |
| PyTorch | 2.11.0+cu128 |
| TorchVision | 0.26.0+cu128; NMS operator executed on CPU and CUDA, result `[0]` on both |
| CUDA | Available; runtime 12.8 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| VRAM | 8,585,216,000 total; 7,426,015,232 bytes free at audit |
| RAM | 16,802,746,368 total; 558,559,232 bytes available at audit |
| OpenCV | Distribution 5.0.0.93; runtime 5.0.0; SIFT and ORB constructors available |
| Pillow / NumPy | 12.3.0 / 2.4.6 |
| FastAPI / Pydantic | 0.162.0 / 2.14.1 |
| pytest / pytest-cov / coverage | 9.1.1 / 7.1.0 / 7.17.2 |
| HTTPX / Ruff / Uvicorn | 0.28.1 / 0.17.2 / 0.54.0 |
| psutil | 7.2.2 |
| Ultralytics | 8.4.132; existing YOLO weights/code left untouched |
| Not installed | scikit-image, transformers, timm, sam2, segment-anything, efficient-sam, safetensors, huggingface-hub, omegaconf, xformers, iopath |

The audited OpenCV build has no `cv2.quality` module. SSIM can be implemented from its
documented Gaussian-window formula using existing OpenCV/NumPy, with numerical tests;
there is no need to install scikit-image just for this operation.

Low available host RAM is a current resource constraint, not a measured model OOM.
Recheck RAM immediately before inference, load models sequentially with batch size one,
bound images and pair counts, and refuse/defer work if the configured resource reserve
cannot be met. An initial configurable 2 GiB free-host-memory reserve is an engineering
guard pending measurement, not a scientific model requirement. Do not close user programs
or change memory settings automatically. CPU fallback still needs sufficient host RAM.

Full machine-readable audit is in `.test-artifacts/phase-2-baseline/environment.json`.
Only tiny operator tests ran; no pretrained network was constructed or evaluated.

## Candidate review and proposed selection

| Candidate | Evidence and tradeoff | Decision for the first implementation |
| --- | --- | --- |
| SAM 2 / SAM 2.1 Hiera variants | Official installation instructions target Linux and strongly recommend WSL on Windows; custom CUDA postprocessing can be skipped, but native Windows operation is not established by that fact. Additional installation/configuration surface is unnecessary for the first image-only pipeline. | Defer rather than change the working environment; no claim that SAM 2 is categorically impossible on Windows. |
| TorchVision pretrained instance segmentation | Existing TorchVision operators work; this remains a possible adapter for supported detector classes. Category-limited masks do not cover arbitrary rented objects or resolve which visible object is the target. | Not the default class-agnostic target segmenter. |
| EfficientSAM-Ti | Small promptable pretrained segmenter; reviewed inference modules use installed Torch/NumPy and standard-library imports. Supports points/boxes and avoids custom native extensions in the selected path. | Proposed default with explicit per-image target prompts; absent/ambiguous target selection must produce inconclusive output. |
| DINOv2 ViT-S/14, no registers | Small pretrained backbone, 384-dimensional embeddings and patch size 14. These features supplement local correspondence; they are not identity proof. | Proposed embedding backbone; start with deterministic 224-pixel evaluation crops and versioned preprocessing, then benchmark before increasing resolution. |

These selections are compatibility and resource hypotheses. Native Windows pretrained
forward passes, useful segmentation, latency, RAM and VRAM remain unverified until the
approved weights are available and genuine inference runs.

Official sources reviewed:

- [SAM 2 installation and Windows/extension notes](https://github.com/facebookresearch/sam2/blob/main/INSTALL.md).
- [EfficientSAM official repository and prompt examples](https://github.com/yformer/EfficientSAM).
- [EfficientSAM source at the selected commit](https://github.com/yformer/EfficientSAM/tree/d525f622e6f640acf5a0fc37c7ca1f243da5bde0/efficient_sam).
- [EfficientSAM package metadata](https://github.com/yformer/EfficientSAM/blob/d525f622e6f640acf5a0fc37c7ca1f243da5bde0/setup.py), whose base dependency list is empty; actual inference imports were separately inspected.
- [DINOv2 official model card](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/MODEL_CARD.md).
- [DINOv2 backbone loader](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/hub/backbones.py).
- [DINOv2 evaluation preprocessing](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/data/transforms.py).

The official DINOv2 evaluation transform uses RGB tensor conversion, resize 256,
bicubic center crop 224 and ImageNet normalization. The adapter must record how an
object crop/mask is formed before this transform and retain local-feature analysis of
the full supported region. EfficientSAM's selected implementation resizes internally
to 1024x1024 and maps prompts/masks back to the input dimensions; the adapter must use
that coordinate mapping, validate output shape/type and never guess an upload-order target.

## Versions, licenses, exact assets

| Model | Pinned official source revision | Checkpoint bytes | License evidence |
| --- | --- | ---: | --- |
| EfficientSAM-Ti | `d525f622e6f640acf5a0fc37c7ca1f243da5bde0` | 40,982,470 | Repository Apache-2.0 LICENSE; no distinct restriction was identified in the inspected checkpoint distribution |
| DINOv2 ViT-S/14 | `7764ea0f912e53c92e82eb78a2a1631e92725fc8` | 88,283,115 | Apache-2.0 repository LICENSE and model card |

License files: [EfficientSAM](https://github.com/yformer/EfficientSAM/blob/d525f622e6f640acf5a0fc37c7ca1f243da5bde0/LICENSE),
[DINOv2](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/LICENSE).
Keep copyright/license notices with vendored inference modules. No training code,
new detector weights, ONNX runtime, notebooks, training dependencies or datasets are
included in the proposed download.

Both weight URLs returned HTTP 200 to HTTPS HEAD requests with the byte lengths above.
HEAD retrieved headers only, not checkpoint bodies. Source-file sizes and Git blob
identities came from official GitHub tree metadata. Proposed source subset: 24 small
Python/license files totaling 117,864 bytes. Total proposed transfer:
**129,383,449 bytes, approximately 129.4 MB / 123.4 MiB**, before HTTP overhead.

`phase-2-installation-plan.json` enumerates every URL, target, expected byte count,
source revision and available Git blob identity. Repository-wide archives are deliberately
avoided because the EfficientSAM repository also contains unneeded large weights.

## Installation changes and loading policy

Proposed Conda/pip changes: **none**. Keep the approved interpreter and all installed
packages. Download only the allowlisted official source modules/licenses and the two
checkpoints into ignored `ep/.runtime/models/`. No separate environment is proposed.

Do not call torch.hub against a moving remote branch or let a request handler fetch
weights. Instantiate audited local architectures without implicit pretrained loading,
load trusted local state dictionaries with `weights_only=True` and strict keys/shapes,
and never fall back to unrestricted pickle or arbitrary TorchScript/model executables.
Disable optional xformers paths and use installed PyTorch operations initially. Missing
optional capabilities should produce typed unavailable results, not an automatic pip install.

Validate source byte sizes and Git blob hashes, then record SHA-256 values. EfficientSAM
weights have a pinned Git blob identity. DINOv2's official URL is not commit-addressed:
no independent publisher SHA-256 was found in the inspected sources, and its multipart
ETag is not a SHA-256 signature. Record first-download SHA-256 over verified HTTPS and
require that manifest thereafter; disclose the trust-on-first-download limitation.
Do not treat response ETags as authenticity proofs or disable certificate validation.

After approval, use lazy eval/inference mode, explicit CUDA/CPU selection, one worker/GPU
job at a time, sequential stage execution, bounded inputs and cleanup/recovery after
load/OOM/timeout/cancellation. Validate and measure CPU fallback separately. No parameter
update, fine-tuning, Gemini call or financial decision is part of Phase 2.
