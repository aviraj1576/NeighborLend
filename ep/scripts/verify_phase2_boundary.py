"""Read-only comparison with the saved Phase 2 baseline; writes its report only in EP."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ep_engine.cv.assets import verify_store  # noqa: E402


def main():
    baseline = ROOT / ".test-artifacts/phase-2-baseline"
    original = json.loads((baseline / "source-hashes.json").read_text("utf-8-sig"))
    changed = [
        row["path"]
        for row in original
        if hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() != row["sha256"]
    ]
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git required")
    status = subprocess.run(  # noqa: S603
        [git, "-c", "core.quotepath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT.parent,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    outside = [line[3:] for line in status.splitlines() if not line[3:].startswith("ep/")]
    packages = json.loads((baseline / "environment.json").read_text("utf-8"))["packages"]
    versions = {}
    for name in packages:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    environment_changes = {
        name: [old, versions[name]] for name, old in packages.items() if old != versions[name]
    }
    # Fixed local pytest-generated report, never an uploaded XML document.
    tests = ET.parse(ROOT / ".test-artifacts/coverage.xml").getroot().find("testsuite")  # noqa: S314
    coverage = json.loads((ROOT / ".test-artifacts/coverage.json").read_text("utf-8"))["totals"]
    receipt = verify_store()
    files = []
    for directory, children, entries in os.walk(ROOT):
        children[:] = [
            name for name in children if name not in {".runtime", ".test-artifacts", "__pycache__"}
        ]
        files.extend((Path(directory) / name).relative_to(ROOT).as_posix() for name in entries)
    files = sorted(set(files) | {"docs/phase-2-inventory.md", "docs/phase-2-verification.json"})
    original_names = {row["path"].replace("\\", "/") for row in original}
    new_files = [name for name in files if name not in original_names]
    record = {
        "date": "2026-11-08",
        "platform": "native Windows",
        "initial_status": "Existing ep/ untracked; preserved",
        "outside_ep_changes": outside,
        "original_files_changed": changed,
        "new_source_and_documentation_files": new_files,
        "original_test_files_changed": [
            name for name in changed if name.replace("\\", "/").startswith("tests/")
        ],
        "audited_environment_version_changes": environment_changes,
        "verified_model_files": len(receipt["files"]),
        "manifest_sha256": receipt["manifest_sha256"],
        "tests": {
            name: int(tests.attrib[name]) for name in ("tests", "failures", "errors", "skipped")
        },
        "coverage": coverage,
    }
    (ROOT / "docs/phase-2-verification.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    inventory = (
        "# Phase 2 implementation inventory\n\n"
        "Paths below are relative to `ep/`. Original baseline work was untracked and preserved.\n\n"
        "## Modified original files\n\n"
        + "\n".join(f"- `{name}`" for name in sorted(name.replace("\\", "/") for name in changed))
        + "\n\n## New source and documentation files\n\n"
        + "\n".join(f"- `{name}`" for name in new_files)
        + "\n\n## Approved runtime downloads\n\n"
        + "\n".join(f"- `{name}`" for name in sorted(receipt["files"]))
        + "\n\nAll downloaded hashes are in `.runtime/models/integrity.json`. "
        "Generated test reports/caches and isolated databases are under `.test-artifacts/`. "
        "Benchmark PNG UUIDs and hashes are enumerated in its individual package JSONs. "
        "Runtime worker locks/model caches stay under `.runtime/`. These generated data "
        "directories are excluded from the authored-source inventory and Git.\n"
    )
    (ROOT / "docs/phase-2-inventory.md").write_text(inventory, encoding="utf-8")
    print(json.dumps(record, indent=2))
    changed_tests = [
        name
        for name in record["original_test_files_changed"]
        if name.replace("\\", "/") != "tests/conftest.py"
    ]
    return bool(outside or environment_changes or changed_tests)


if __name__ == "__main__":
    raise SystemExit(main())
