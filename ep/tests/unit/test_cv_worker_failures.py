import hashlib
import json
import subprocess
from uuid import uuid4

import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.worker import ProcessRunner, load_inputs, main


@pytest.mark.parametrize("cancel", [True, False])
def test_hard_timeout_and_cancellation_terminate_child(tmp_path, monkeypatch, cancel):
    observed = []

    class Child:
        returncode = None

        def __init__(self, *args, **kwargs):
            observed.append(self)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            if self.returncode is None:
                raise subprocess.TimeoutExpired("fixed-worker", timeout)
            return self.returncode

    monkeypatch.setattr("ep_engine.cv.worker.cache_environment", lambda: None)
    monkeypatch.setattr("ep_engine.cv.worker.subprocess.Popen", Child)
    times = iter([0, 3])
    monkeypatch.setattr("ep_engine.cv.worker.time.monotonic", lambda: next(times))
    with pytest.raises(EPError) as caught:
        ProcessRunner()({"config": {"timeout_seconds": 1}}, tmp_path / "output", lambda: cancel)
    assert caught.value.code == ("cancelled" if cancel else "inference_timeout")
    assert observed[0].returncode == -15


def test_worker_rejects_forged_derivative_and_reports_errors(tmp_path, image_bytes):
    keys = [uuid4(), uuid4()]
    data = image_bytes()
    rows = []
    for key, stage in zip(keys, ("before", "after"), strict=True):
        path = tmp_path / f"{key}.png"
        path.write_bytes(data)
        rows.append(
            {
                "id": str(key),
                "path": str(path),
                "stage": stage,
                "target": None,
                "normalized_sha256": hashlib.sha256(data).hexdigest(),
                "sha256": "a" * 64,
            }
        )
    payload = {"evidence": rows, "config": CVConfig().model_dump(), "inspection_id": str(uuid4())}
    request = tmp_path / "input.json"
    request.write_text(json.dumps(payload))
    assert main(str(request)) == 0
    assert json.loads((tmp_path / "result.json").read_text())["outcome"] == "inconclusive"
    payload["evidence"][0]["normalized_sha256"] = "0" * 64
    request.write_text(json.dumps(payload))
    assert main(str(request)) == 3
    assert json.loads((tmp_path / "result.json").read_text())["error_code"] == "integrity_failure"
    payload["evidence"][0]["path"] = str(tmp_path / "forged.png")
    with pytest.raises(EPError):
        load_inputs(payload)


def test_native_subprocess_returns_valid_low_quality_result(tmp_path, image_bytes):
    data = image_bytes()
    evidence = []
    for stage in ("before", "after"):
        key = uuid4()
        path = tmp_path / f"{key}.png"
        path.write_bytes(data)
        evidence.append(
            {
                "id": str(key),
                "stage": stage,
                "path": str(path),
                "target": None,
                "sha256": "a" * 64,
                "normalized_sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    result = ProcessRunner()(
        {"inspection_id": str(uuid4()), "config": CVConfig().model_dump(), "evidence": evidence},
        tmp_path / "output",
        lambda: False,
    )
    assert result.outcome == "inconclusive" and result.metrics["device"] == "not_loaded"
    assert len(result.quality) == 2 and not result.candidates


@pytest.mark.parametrize("content", [None, {"error_code": "untrusted_code"}])
def test_missing_or_failed_child_result_is_sanitized(tmp_path, monkeypatch, content):
    class Child:
        returncode = 3

        def __init__(self, *args, **kwargs):
            if content:
                (tmp_path / "result.json").write_text(json.dumps(content))

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr("ep_engine.cv.worker.subprocess.Popen", Child)
    with pytest.raises(EPError) as caught:
        ProcessRunner()({"config": {"timeout_seconds": 10}}, tmp_path / "output", lambda: False)
    assert caught.value.code == "worker_failure"
