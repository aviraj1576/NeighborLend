# Environment audit

Audited 2026-11-08 before installing dependencies. Requested exact environment
`neighborklend-yolo` was not registered and its expected interpreter was absent.
Conda listed `D:/Anaconda_Install/envs/neighbourlend_yolo`; the user explicitly approved
this actual environment for EP work. No environment was renamed or created.

Interpreter: `D:/Anaconda_Install/envs/neighbourlend_yolo/python.exe`.
Python: **3.11.16**, Anaconda, MSC v.1942, 64 bit, build Aug 27 2026.
The terminal default `D:/Python_Install/python.exe` was not used for validation.

| Package | Audited installed version |
| --- | --- |
| torch | 2.11.0+cu128 |
| torchvision | 0.26.0+cu128 |
| ultralytics | 8.4.132 |
| opencv-python | 5.0.0.93 |
| Pillow | 12.3.0 |
| fastapi | 0.162.0 |
| pydantic | 2.14.1 |
| numpy | 2.4.6 |
| pytest | 9.1.1 |
| httpx | 0.28.1 |
| python-multipart | 0.0.32 |
| ruff | 0.17.2 |
| uvicorn | 0.54.0 |
| pytest-cov | Missing initially; 7.1.0 installed with approval |
| coverage | 7.17.2 added as pytest-cov dependency with approval |
| scikit-image, transformers | Not installed; not required in Phase 1 |

PyTorch import and CUDA query succeeded: CUDA available **True**, PyTorch CUDA runtime
**12.8**, GPU **NVIDIA GeForce RTX 4060 Laptop GPU**, total VRAM **8,585,216,000 bytes**,
free VRAM **7,440,695,296 bytes** at audit time. This is a point-in-time resource query,
not an inference benchmark. TorchVision was audited by distribution metadata; its operators
and ABI were not inference-tested. No pretrained models were instantiated or downloaded.

Initial sandbox execution of Conda/Python was denied. Authorized execution outside the
sandbox enabled the read-only audit and subsequent tests. `conda env list --json` and
`importlib.metadata` provided environment/package evidence; GPU data came from `torch.cuda`.
No secret files, API keys or token values were read.

The user approved this minimal Conda addition:

```powershell
# Executed from ep/, with TMP and TEMP set to ep/.test-artifacts/pip-tmp
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B -m pip install --no-cache-dir --no-compile 'pytest-cov>=5,<8'
```

Pip installed only pytest-cov 7.1.0 and coverage 7.17.2; existing pytest/pluggy dependencies
were already satisfied. No existing application/ML package was upgraded, downgraded,
removed or reinstalled. No additional dependencies are required for Phase 1 validation.
Conda package installation is the expressly authorized change outside the repository;
all repository edits and test/runtime artifacts stay under `ep/`.

The installed FastAPI/Starlette emits a deprecation warning for HTTPX TestClient and
suggests `httpx2`. Tests execute successfully using the user's available HTTPX. No
dependency change was made to suppress this warning. Review it before future upgrades.

Phase 2 must evaluate pretrained model API/ABI and resource compatibility in isolation;
8 GB VRAM does not establish capacity for simultaneous segmentation/embedding/LLM work.
Prefer lazy worker loading, inference mode, bounded batches, explicit device selection,
timeouts, and serialized GPU scheduling. Consider a separately approved `neighborlend-ep`
environment only if concrete conflicts are demonstrated. No such conflict was established
for this foundation, so none was created.
