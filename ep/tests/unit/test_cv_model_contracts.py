import numpy as np
import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv.models import check_embedding, check_mask, preflight


def test_embedding_contract():
    result = check_embedding(np.ones(384, dtype=np.float32))
    assert result.shape == (384,)
    assert np.linalg.norm(result) == pytest.approx(1)
    for invalid in (
        np.zeros(384),
        np.ones(383),
        np.full(384, np.nan),
        np.ones((1, 384)),
        np.full(384, np.finfo(np.float32).max, np.float32),
    ):
        with pytest.raises(EPError):
            check_embedding(invalid)


def test_mask_contract():
    mask = np.zeros((16, 24), bool)
    mask[3:13, 4:20] = True
    assert check_mask(mask, (16, 24)).sum() == 160
    for invalid in (np.zeros_like(mask), np.ones_like(mask), mask.astype(float), mask[:3]):
        with pytest.raises(EPError):
            check_mask(invalid, (16, 24))


def test_memory_and_platform_fail_closed(monkeypatch):
    import psutil

    monkeypatch.setattr("ep_engine.cv.models.platform.system", lambda: "Linux")
    with pytest.raises(EPError) as caught:
        preflight("cpu")
    assert caught.value.code == "native_windows_required"
    monkeypatch.setattr("ep_engine.cv.models.platform.system", lambda: "Windows")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: type("Memory", (), {"available": 1024})())
    with pytest.raises(EPError) as caught:
        preflight("cpu")
    assert caught.value.code == "memory_reserve"
