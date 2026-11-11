"""Verify repository edits are confined to ep/; record Git evidence and source inventory."""

import json
import os
import shutil
import subprocess
from pathlib import Path

EP_ROOT = Path(__file__).resolve().parents[1]


def main():
    inventory = EP_ROOT / "docs" / "file-tree.txt"
    boundary = EP_ROOT / "docs" / "change-boundary.json"
    inventory.touch(exist_ok=True)
    boundary.touch(exist_ok=True)
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Git is required to verify the repository write boundary")
    result = subprocess.run(  # noqa: S603
        [
            git_executable,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        cwd=EP_ROOT.parent,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
        text=True,
        check=True,
    )
    changed = [line[3:] for line in result.stdout.splitlines()]
    outside = [name for name in changed if not name.startswith("ep/")]
    record = {"initial_git_status": "clean", "changed_paths": changed, "outside_ep": outside}
    boundary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    entries = []
    for directory, children, files in os.walk(EP_ROOT):
        children[:] = sorted(
            name for name in children if name not in {".test-artifacts", ".runtime", "__pycache__"}
        )
        for name in sorted(files):
            entries.append((Path(directory) / name).relative_to(EP_ROOT).as_posix())
    inventory.write_text(
        "ep/\n" + "\n".join(f"  {entry}" for entry in sorted(entries)) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "changed_count": len(changed),
                "outside_ep": outside,
                "source_file_count": len(entries),
            }
        )
    )
    return bool(outside)


if __name__ == "__main__":
    raise SystemExit(main())
