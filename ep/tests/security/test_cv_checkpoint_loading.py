from types import SimpleNamespace

import numpy as np
import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv import models


@pytest.fixture
def native(monkeypatch):
    # Failure injection uses installed Torch, with no checkpoint download or loading.
    monkeypatch.setattr(models, "preflight", lambda device: {"available_ram_bytes": 8 * models.GIB})
    instance = models.NativeModels("cpu")
    yield instance
    instance.close()


@pytest.mark.parametrize("failure", ["non_tensor", "nan", "keys", "oom"])
def test_safe_checkpoint_failure_and_cleanup(native, tmp_path, monkeypatch, failure):
    import torch

    plan = models.assets.read_plan()
    root = models.assets.destination(plan[0]).parent
    model = torch.nn.Linear(1, 1)
    module = SimpleNamespace(
        __file__=str(root / "efficient_sam/efficient_sam.py"),
        build_efficient_sam=lambda *args, **kwargs: model,
    )
    monkeypatch.setattr(
        models.assets, "verify_store", lambda: {"files": {plan[-2]["relative_target"]: "a" * 64}}
    )
    monkeypatch.setattr(models.importlib, "import_module", lambda name: module)
    observed = []

    def checkpoint(path, *, map_location, weights_only):
        observed.append((map_location, weights_only))
        if failure == "oom":
            raise torch.cuda.OutOfMemoryError("injected")
        state = (
            {"weight": "executable strings are rejected"}
            if failure == "non_tensor"
            else {"weight": torch.tensor([[float("nan") if failure == "nan" else 1.0]])}
        )
        return {"model": state}

    monkeypatch.setattr(torch, "load", checkpoint)
    with pytest.raises(EPError) as caught:
        native._load("segment")
    assert observed == [("cpu", True)]
    assert (
        caught.value.code
        == {
            "non_tensor": "unsafe_checkpoint",
            "nan": "unsafe_checkpoint",
            "keys": "model_load_failed",
            "oom": "model_oom",
        }[failure]
    )
    assert native.model is None and native.kind is None


def test_gpu_reserve_and_forward_oom_cleanup(native, monkeypatch):
    import torch

    native.device = "cuda"
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda: (1024, 8 * models.GIB))
    with pytest.raises(EPError) as caught:
        native._load("segment")
    assert caught.value.code == "memory_reserve"
    native.device = "cpu"

    def failing(*args):
        raise torch.cuda.OutOfMemoryError("injected")

    with pytest.raises(EPError) as caught:
        native._forward(failing, None)
    assert caught.value.code == "model_oom" and native.model is None


def test_unsupported_device_and_invalid_inference_inputs(native):
    with pytest.raises(EPError):
        models.NativeModels("invalid")
    with pytest.raises(EPError):
        native.segment(np.zeros((1025, 2, 3), np.uint8), (0, 0, 1, 1))
    with pytest.raises(EPError):
        native.segment(np.zeros((16, 16, 3), np.uint8), (0.9, 0, 0.1, 1))
    with pytest.raises(EPError):
        native.embedding(np.zeros((10, 10, 3), float), np.zeros((10, 10), bool))


def test_cuda_unavailable_is_explicit(monkeypatch):
    import torch

    monkeypatch.setattr(models, "preflight", lambda device: {})
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(EPError) as caught:
        models.NativeModels("cuda")
    assert caught.value.code == "cuda_unavailable"
    instance = models.NativeModels("auto")
    assert instance.device == "cpu"
    instance.close()


def test_model_forward_outputs_must_be_finite_and_correct_shape(native, monkeypatch):
    import torch

    image = np.zeros((16, 16, 3), np.uint8)
    monkeypatch.setattr(native, "_load", lambda kind: None)
    monkeypatch.setattr(
        native, "_forward", lambda *a: (torch.zeros(1, 1, 2, 16, 16), torch.ones(1, 1, 2))
    )
    with pytest.raises(EPError) as caught:
        native.segment(image, (0, 0, 1, 1))
    assert caught.value.code == "invalid_mask"
    mask = np.zeros((16, 16), bool)
    mask[2:14, 2:14] = True
    monkeypatch.setattr(native, "_forward", lambda *a: torch.ones(1, 383))
    with pytest.raises(EPError) as caught:
        native.embedding(image, mask)
    assert caught.value.code == "invalid_embedding"


def test_extreme_crop_rejected_before_resize(native):
    image = np.zeros((1024, 64, 3), np.uint8)
    mask = np.zeros((1024, 64), bool)
    mask[:, 30:32] = True
    with pytest.raises(EPError) as caught:
        native.embedding(image, mask)
    assert caught.value.code == "invalid_embedding"
