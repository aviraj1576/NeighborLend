"""Sequential fresh-process native regression checks with lightweight RAM monitoring."""

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/openrouter-finalization-20261111/native-isolated"
FILES = (
    "tests/integration/test_controlled_native.py",
    "tests/integration/test_cv_real.py",
    "tests/integration/test_release_native.py",
    "tests/integration/test_v31_native.py",
    "tests/integration/test_v3_cuda.py",
)


def process_tree(pid):
    try:
        process = psutil.Process(pid)
        return [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign", choices=("initial", "recovered", "complete"), default="initial"
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    destination = OUT if args.campaign == "initial" else OUT.with_name("native-" + args.campaign)
    destination.mkdir(parents=True, exist_ok=True)
    prior = ROOT / ".test-artifacts/openrouter-v31-20261111/native.xml"
    cases = [
        t
        for t in ET.parse(prior).getroot().iter("testcase")  # noqa: S314 - local test XML
        if args.all or t.find("failure") is not None
    ]
    records = []
    if args.resume:
        if args.campaign != "complete":
            raise ValueError("Resume is restricted to the complete isolated campaign")
        records = json.loads((destination / "measurements.json").read_bytes())
    env = os.environ.copy()
    env.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        EP_RUN_REAL_CV="1",
        EP_RUN_CONTROLLED_CV="1",
        EP_RUN_V3_CUDA="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for index, case in enumerate(cases):
        testfile = case.get("classname").replace(".", "/") + ".py"
        if testfile not in FILES:
            raise ValueError("Unexpected native test identity")
        node = testfile + "::" + case.get("name")
        if index < len(records):
            if records[index]["node"] != node or records[index]["exit_code"] != 0:
                raise ValueError("Cannot resume mismatched or failed measurement records")
            continue
        folder = destination / str(index)
        folder.mkdir(exist_ok=True)
        env["EP_NATIVE_MEMORY_LOG"] = str(folder / "preflight.jsonl")
        command = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            node,
            "-q",
            "-p",
            "scripts.native_memory_probe",
            f"--basetemp={folder / 'tmp'}",
            f"--junitxml={folder / 'tests.xml'}",
        ]
        row = dict(
            node=node,
            available_before=psutil.virtual_memory().available,
            controller_rss=psutil.Process().memory_info().rss,
            peak_child_rss=0,
            minimum_available=psutil.virtual_memory().available,
        )
        started = time.monotonic()
        with (folder / "output.log").open("wb") as log:
            child = subprocess.Popen(  # noqa: S603 - fixed local test identities, no shell
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                while child.poll() is None:
                    processes = process_tree(child.pid)
                    if not processes:
                        break
                    working_set = 0
                    for process in processes:
                        try:
                            working_set += process.memory_info().rss
                        except psutil.NoSuchProcess:
                            pass
                    row["peak_child_rss"] = max(row["peak_child_rss"], working_set)
                    row["minimum_available"] = min(
                        row["minimum_available"], psutil.virtual_memory().available
                    )
                    if time.monotonic() - started > 240:
                        for process in reversed(processes):
                            try:
                                process.kill()
                            except psutil.NoSuchProcess:
                                pass
                        row["timeout"] = True
                        break
                    time.sleep(0.25)
            finally:
                child.wait(timeout=15)
        row.update(
            exit_code=child.returncode,
            seconds=time.monotonic() - started,
            available_after=psutil.virtual_memory().available,
        )
        records.append(row)
        (destination / "measurements.json").write_text(json.dumps(records, indent=2), "utf-8")
        print(json.dumps(row), flush=True)
    return 0 if all(r["exit_code"] == 0 for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
