"""Run from any directory with the approved Conda Python; all artifacts stay in ep/."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "category",
        choices=(
            "unit",
            "integration",
            "security",
            "regression",
            "all",
            "coverage",
            "lint",
            "format",
            "real",
        ),
    )
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    artifacts = ROOT / ".test-artifacts"
    artifacts.mkdir(exist_ok=True)
    temporary = artifacts / "process-tmp"
    temporary.mkdir(exist_ok=True)
    environment = os.environ.copy()
    if args.synthetic_only:
        environment["EP_SYNTHETIC_ONLY"] = "1"
        environment["EP_RUN_CONTROLLED_CV"] = "1"
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        TMP=str(temporary),
        TEMP=str(temporary),
        TMPDIR=str(temporary),
    )
    command = [sys.executable, "-B", "-m"]
    if args.category in ("lint", "format"):
        command += (
            ["ruff", "check", "ep_engine", "scripts", "tests", "pyproject.toml"]
            if args.category == "lint"
            else ["ruff", "format", "--check", "ep_engine", "scripts", "tests"]
        )
    else:
        command += ["pytest"]
        if args.category == "coverage":
            command += [
                "-p",
                "pytest_cov",
                "--cov=ep_engine",
                "--cov-report=term-missing",
                "--cov-report=json",
                "--cov-report=html",
            ]
        elif args.category == "real":
            environment["EP_RUN_REAL_CV"] = "1"
            command += ["-m", "real_inference"]
        elif args.category != "all":
            command += [f"tests/{args.category}"]
        command += [f"--junitxml=.test-artifacts/{args.category}.xml"]
    # Fixed executables/subcommands and argparse choices; no shell or untrusted command strings.
    result = subprocess.run(command, cwd=ROOT, env=environment, check=False)  # noqa: S603
    (artifacts / f"{args.category}-execution.json").write_text(
        json.dumps({"command": command, "cwd": str(ROOT), "exit_code": result.returncode}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
