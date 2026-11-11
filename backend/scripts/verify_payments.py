"""Native offline backend verification; no dependency install or production database access."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    artifacts = ROOT / ".payment-verification"
    temporary = artifacts / "process-tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        APP_ENV="test",
        PAYMENT_PROVIDER="mock",
        PAYMENT_DEMO_MODE="true",
        YOLO_CONFIG_DIR=str(artifacts),
        TMP=str(temporary),
        TEMP=str(temporary),
        TMPDIR=str(temporary),
        PYTHONPATH=os.pathsep.join([str(ROOT / ".test-tools"), str(ROOT)]),
    )
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "tests",
        "-q",
        "--tb=short",
        "-o",
        "cache_dir=.payment-verification/pytest-cache",
        "--basetemp=.payment-verification/tmp",
        "--junitxml=.payment-verification/backend.xml",
    ]
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
