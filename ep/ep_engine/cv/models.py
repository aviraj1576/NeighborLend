import gc
import importlib
import os
import platform
import sys
import time

import numpy as np
import psutil

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.cv import assets
from ep_engine.cv.targeting import embedding_canvas, select_target_mask

GIB = 1024**3


def preflight(device: str) -> dict:
    if platform.system() != "Windows":
        raise EPError(503, "native_windows_required", "Native Windows execution is required")
    available = psutil.virtual_memory().available
    if available < 1.5 * GIB:
        raise EPError(503, "memory_reserve", "Insufficient free host memory for safe inference")
    return {"available_ram_bytes": available, "requested_device": device}


def cache_environment():
    base = EP_ROOT / ".runtime" / "cv-cache"
    for name in (
        "TORCH_HOME",
        "HF_HOME",
        "XDG_CACHE_HOME",
        "CUDA_CACHE_PATH",
        "TORCH_EXTENSIONS_DIR",
        "TORCHINDUCTOR_CACHE_DIR",
        "TRITON_CACHE_DIR",
        "TMP",
        "TEMP",
        "TMPDIR",
    ):
        path = base / name.lower()
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ["XFORMERS_DISABLED"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True


def check_embedding(value: np.ndarray) -> np.ndarray:
    if value.shape != (384,) or not np.isfinite(value).all():
        raise EPError(503, "invalid_embedding", "Invalid DINOv2 embedding")
    with np.errstate(over="ignore", invalid="ignore"):
        norm = np.linalg.norm(value)
    if not np.isfinite(norm) or norm < 1e-8:
        raise EPError(503, "invalid_embedding", "Invalid DINOv2 embedding norm")
    return (value / norm).astype(np.float32)


def check_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if mask.dtype != np.bool_ or mask.shape != shape or not 0.001 < mask.mean() < 0.98:
        raise EPError(503, "invalid_mask", "Empty, ambiguous or invalid object mask")
    return mask


class NativeModels:
    """Audited local modules only; one resident pretrained model, no dynamic downloads."""

    def __init__(self, device="cuda"):
        if device not in ("cuda", "cpu", "auto"):
            raise EPError(422, "invalid_device", "Unsupported inference device")
        self.resources = preflight(device)
        cache_environment()
        import torch

        self.torch = torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        if device == "cuda" and not torch.cuda.is_available():
            raise EPError(503, "cuda_unavailable", "CUDA is not available")
        self.device = "cuda" if device != "cpu" and torch.cuda.is_available() else "cpu"
        self.model = None
        self.kind = None
        self.loads = {}
        self.weight_hashes = {}
        self.forward_seconds = {}
        self.forward_calls = {}
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()

    def close(self):
        self.model = None
        self.kind = None
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()

    def _load(self, kind):
        preflight(self.device)
        if self.device == "cuda" and self.torch.cuda.mem_get_info()[0] < 2 * GIB:
            raise EPError(503, "memory_reserve", "Insufficient free GPU memory")
        if self.kind == kind:
            return self.model
        self.close()
        started = time.perf_counter()
        receipt = assets.verify_store()
        plan = assets.read_plan()
        source = next(
            item
            for item in plan
            if item.get("repository")
            == ("yformer/EfficientSAM" if kind == "segment" else "facebookresearch/dinov2")
        )
        root = assets.destination(source).parent
        package = "efficient_sam" if kind == "segment" else "dinov2"
        existing = sys.modules.get(package)
        if existing and not __import__("pathlib").Path(existing.__file__).resolve().is_relative_to(
            root
        ):
            raise EPError(409, "unsafe_model_code", "Model module came from an unapproved path")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            if kind == "segment":
                module = importlib.import_module("efficient_sam.efficient_sam")
                model = module.build_efficient_sam(192, 3, checkpoint=None)
                weight = plan[-2]
            else:
                module = importlib.import_module("dinov2.hub.backbones")
                model = module.dinov2_vits14(pretrained=False)
                weight = plan[-1]
            if not __import__("pathlib").Path(module.__file__).resolve().is_relative_to(root):
                raise EPError(409, "unsafe_model_code", "Unapproved model module")
            state = self.torch.load(
                assets.destination(weight), map_location="cpu", weights_only=True
            )
            self.weight_hashes[kind] = receipt["files"][weight["relative_target"]]
            state = state["model"] if kind == "segment" else state
            if not isinstance(state, dict) or any(
                not isinstance(value, self.torch.Tensor) or not self.torch.isfinite(value).all()
                for value in state.values()
            ):
                raise EPError(409, "unsafe_checkpoint", "Checkpoint tensor validation failed")
            model.load_state_dict(state, strict=True)
            self.model = model.eval().requires_grad_(False).to(self.device)
            self.kind = kind
            if self.device == "cuda":
                self.torch.cuda.synchronize()
            self.loads[kind] = time.perf_counter() - started
            return self.model
        except self.torch.cuda.OutOfMemoryError as exc:
            self.close()
            raise EPError(503, "model_oom", "Model memory allocation failed") from exc
        except EPError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise EPError(
                503, "model_load_failed", "Pretrained model could not be loaded safely"
            ) from exc

    def _forward(self, model, *args):
        kind = self.kind or "unknown"
        if self.device == "cuda":
            self.torch.cuda.synchronize()
        started = time.perf_counter()
        try:
            with self.torch.inference_mode():
                return model(*args)
        except self.torch.cuda.OutOfMemoryError as exc:
            self.close()
            raise EPError(503, "model_oom", "Inference memory allocation failed") from exc
        finally:
            if self.device == "cuda":
                self.torch.cuda.synchronize()
            self.forward_seconds[kind] = (
                self.forward_seconds.get(kind, 0) + time.perf_counter() - started
            )
            self.forward_calls[kind] = self.forward_calls.get(kind, 0) + 1

    def segment(self, rgb: np.ndarray, box) -> np.ndarray:
        height, width = rgb.shape[:2]
        if rgb.dtype != np.uint8 or rgb.shape != (height, width, 3) or max(height, width) > 1024:
            raise EPError(413, "processing_limit", "Invalid or oversized inference image")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise EPError(422, "invalid_target", "Invalid target box")
        model = self._load("segment")
        image = (
            self.torch.from_numpy(rgb.copy())
            .permute(2, 0, 1)
            .float()
            .div(255)[None]
            .to(self.device)
        )
        points = self.torch.tensor(
            [[[[x1 * width, y1 * height], [x2 * width, y2 * height]]]], device=self.device
        )
        labels = self.torch.tensor([[[2, 3]]], device=self.device)
        masks, scores = self._forward(model, image, points, labels)
        if (
            masks.shape != (1, 1, 3, height, width)
            or scores.shape != (1, 1, 3)
            or not (self.torch.isfinite(masks).all() and self.torch.isfinite(scores).all())
        ):
            raise EPError(503, "invalid_mask", "Segmentation returned invalid values")
        chosen = select_target_mask(
            masks[0, 0].gt(0).cpu().numpy(), scores[0, 0].cpu().numpy(), box
        )
        return check_mask(chosen, (height, width))

    def embedding(self, rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or max(rgb.shape[:2]) > 1024:
            raise EPError(413, "processing_limit", "Invalid or oversized embedding image")
        check_mask(mask, rgb.shape[:2])
        array = embedding_canvas(rgb, mask)
        array = (array - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
            [0.229, 0.224, 0.225], np.float32
        )
        model = self._load("embedding")
        return self._embedding_views(array, model)

    def _embedding_views(self, array, model):
        views = []
        # Sequential forwards bound VRAM; rotation pooling never replaces local geometry checks.
        for rotation in range(4):
            rotated = np.rot90(array, rotation).copy()
            tensor = self.torch.from_numpy(rotated).permute(2, 0, 1)[None].to(self.device)
            result = self._forward(model, tensor)
            if tuple(result.shape) != (1, 384):
                raise EPError(503, "invalid_embedding", "DINOv2 returned an invalid shape")
            views.append(check_embedding(result[0].cpu().numpy()))
        return check_embedding(np.mean(views, axis=0))

    def metrics(self):
        memory = psutil.Process().memory_info()
        return {
            "device": self.device,
            "model_load_seconds": dict(self.loads),
            "model_weight_sha256": dict(self.weight_hashes),
            "neural_forward_seconds": dict(self.forward_seconds),
            "neural_forward_calls": dict(self.forward_calls),
            "process_rss_bytes": memory.rss,
            "process_peak_working_set_bytes": getattr(memory, "peak_wset", memory.rss),
            "peak_cuda_allocated_bytes": self.torch.cuda.max_memory_allocated()
            if self.device == "cuda"
            else 0,
            "peak_cuda_reserved_bytes": self.torch.cuda.max_memory_reserved()
            if self.device == "cuda"
            else 0,
            **self.resources,
        }
