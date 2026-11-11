"""Run standalone v3 from a hashed private evidence manifest with a hard worker deadline."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.config import EP_ROOT
from ep_engine.cv.concurrency import worker_guard
from ep_engine.v3.config import V3Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, destination = args.manifest.resolve(), args.output.resolve()
    if (
        not source.is_relative_to(EP_ROOT)
        or source.stat().st_size > 1_000_000
        or not destination.is_relative_to(EP_ROOT)
        or destination == EP_ROOT
        or args.output.is_symlink()
    ):
        raise ValueError("Use dedicated private paths within ep/")
    config = V3Config.model_validate(json.loads(source.read_text("utf-8"))["config"])
    with worker_guard():
        destination.mkdir(parents=True, exist_ok=False)
        with (destination / "worker.log").open("wb") as log:
            try:
                result = subprocess.run(  # noqa: S603 - fixed interpreter/module, no shell
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "ep_engine.v3.worker",
                        str(source),
                        str(destination),
                    ],
                    cwd=EP_ROOT,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=config.timeout_seconds,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return result.returncode
            except subprocess.TimeoutExpired:
                (destination / "result.json").write_text(
                    json.dumps(
                        {
                            "outcome": "failed",
                            "error_code": "inference_timeout",
                            "payment_action": "none",
                            "human_review_required": True,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return 3


if __name__ == "__main__":
    raise SystemExit(main())
