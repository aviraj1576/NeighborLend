import hashlib
import io
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from uuid import UUID

import numpy as np
from PIL import Image

from ep_engine.config import EP_ROOT
from ep_engine.core.data_policy import enforce_data_policy
from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import CVConfig, CVPackage
from ep_engine.cv.models import cache_environment
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


def load_inputs(payload, *, preserve_original=False):
    inputs = []
    total_pixels = 0
    for row in payload["evidence"]:
        key = UUID(row["id"])
        path = Path(row["path"])
        enforce_data_policy(path)
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(EP_ROOT)
            or path.name != f"{key}.png"
        ):
            raise EPError(409, "evidence_path", "Invalid private derivative path")
        if path.stat().st_size > 64_000_000:
            raise EPError(413, "processing_limit", "Derivative byte limit exceeded")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != row["normalized_sha256"]:
            raise EPError(409, "integrity_failure", "Derivative integrity failed")
        with Image.open(io.BytesIO(content), formats=("PNG",)) as image:
            if image.width * image.height > 16_000_000:
                raise EPError(413, "processing_limit", "Derivative pixel limit exceeded")
            total_pixels += image.width * image.height
            if preserve_original and total_pixels > 64_000_000:
                raise EPError(
                    413, "processing_limit", "Original image collection exceeds memory budget"
                )
            size = image.size
            image = image.convert("RGB")
            original = np.asarray(image).copy() if preserve_original else None
            image.thumbnail((payload["config"]["max_side"],) * 2)
            inputs.append(
                InputImage(
                    key,
                    row["stage"],
                    np.asarray(image),
                    row["sha256"],
                    Box.model_validate(row["target"]) if row["target"] else None,
                    size,
                    row.get("view"),
                    original,
                )
            )
    return inputs


class ProcessRunner:
    """Native Windows process boundary permits hard timeout/cancellation without GPU threads."""

    def __call__(self, payload, output, cancelled):
        cache_environment()
        directory = output.parent
        request = directory / "input.json"
        request.write_text(json.dumps(payload), encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(EP_ROOT)
        started = time.monotonic()
        with (directory / "worker.log").open("wb") as log:
            command = [sys.executable, "-B", "-m", "ep_engine.cv.worker", str(request)]
            process = subprocess.Popen(  # noqa: S603
                command,
                cwd=EP_ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                while True:
                    if cancelled():
                        raise EPError(409, "cancelled", "CV execution cancelled")
                    if time.monotonic() - started > payload["config"]["timeout_seconds"]:
                        raise EPError(
                            503, "inference_timeout", "CV execution exceeded its deadline"
                        )
                    try:
                        process.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        result = directory / "result.json"
        if not result.is_file() or result.stat().st_size > 2_000_000:
            raise EPError(503, "worker_failure", "CV worker produced no valid result")
        content = json.loads(result.read_text("utf-8"))
        if process.returncode != 0:
            (directory / "diagnostics.json").write_text(json.dumps(content), encoding="utf-8")
            # Only public typed codes cross this boundary; exception text remains private.
            code = content.get("error_code", "worker_failure")
            raise EPError(
                503,
                code
                if code
                in {
                    "memory_reserve",
                    "model_oom",
                    "model_load_failed",
                    "models_unavailable",
                    "integrity_failure",
                    "cuda_unavailable",
                }
                else "worker_failure",
                "CV worker failed",
            )
        return CVPackage.model_validate(content)


def main(input_path):
    path = Path(input_path).resolve()
    if (
        not path.is_relative_to(EP_ROOT)
        or path.name != "input.json"
        or path.stat().st_size > 1_000_000
    ):
        raise ValueError("Invalid worker input")
    target = path.parent / "result.json"
    try:
        payload = json.loads(path.read_text("utf-8"))
        config = CVConfig.model_validate(payload["config"])
        inputs = load_inputs(payload)
        result = CVPipeline(config).run(
            UUID(payload["inspection_id"]), inputs, path.parent / "output"
        )
        content, code = result.model_dump_json(), 0
    except Exception as exc:
        cause = exc.__cause__ or exc
        content, code = (
            json.dumps(
                {
                    "error_code": exc.code if isinstance(exc, EPError) else "worker_failure",
                    "exception_type": type(cause).__name__,
                    "frames": [
                        {
                            "module": Path(frame.filename).name,
                            "function": frame.name,
                            "line": frame.lineno,
                        }
                        for frame in traceback.extract_tb(cause.__traceback__)
                    ],
                }
            ),
            3,
        )
    temporary = path.parent / "result.part"
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, target)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
