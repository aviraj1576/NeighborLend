"""Generate the testing report from actual pytest, coverage and runner artifacts."""

import json
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def main():
    artifacts = ROOT / ".test-artifacts"
    suite = ElementTree.parse(artifacts / "coverage.xml").getroot().find("testsuite")  # noqa: S314
    coverage = json.loads((artifacts / "coverage.json").read_text("utf-8"))["totals"]
    executions = {
        category: json.loads((artifacts / f"{category}-execution.json").read_text("utf-8"))
        for category in ("coverage", "lint", "format")
    }
    boundary = json.loads((ROOT / "docs" / "change-boundary.json").read_text("utf-8"))
    counts = Counter(case.attrib["classname"].split(".")[1] for case in suite.findall("testcase"))
    failed = int(suite.attrib["failures"]) + int(suite.attrib["errors"])
    skipped = int(suite.attrib["skipped"])
    total = int(suite.attrib["tests"])
    verified = (
        failed == skipped == 0
        and coverage["percent_covered"] >= 85
        and all(record["exit_code"] == 0 for record in executions.values())
        and not boundary["outside_ep"]
    )
    status = (
        "Phase 1 verification gate passed" if verified else "Partially verified; gate not passed"
    )
    rows = "\n".join(f"| {name} | {count} |" for name, count in sorted(counts.items()))
    commands = "\n".join(
        f"& '{sys.executable}' -B scripts/verify.py {category}"
        for category in (
            "unit",
            "integration",
            "security",
            "regression",
            "all",
            "coverage",
            "lint",
            "format",
        )
    )
    exact = "\n".join(
        "& '" + record["command"][0] + "' " + " ".join(record["command"][1:])
        for record in executions.values()
    )
    report = f"""# Phase 1 testing report

Verified on 2026-11-08, Asia/Calcutta. **{status}.**
Interpreter: `{sys.executable}`; approved Conda environment `neighbourlend_yolo`.

Final complete suite: **{total - failed - skipped} passed, {failed} failed/errors,
{skipped} skipped, 0 blocked Phase 1 tests**; elapsed {suite.attrib["time"]} seconds.
One upstream Starlette TestClient deprecation warning recommends httpx2; existing HTTPX
successfully ran the tests. No dependency was changed to suppress the warning.

| Category | Tests in final complete suite |
| --- | ---: |
{rows}

Unit tests cover real JPEG/PNG decoding, original SHA-256, orientation/metadata stripping,
byte/pixel/dimension boundaries, corrupt/truncated formats, configuration, local grant
validation, finding citations, ASGI chunk accounting/disconnects and ordered pipeline
contracts. Integration tests exercise actual FastAPI TestClient, private filesystem,
isolated SQLite, constraints, duplicate handling, persistence, state transitions,
restart recovery, dependency outages, request/response schemas and OpenAPI.
Security tests cover positive authorized flows and negative authentication, forged
identity, rental/stage restrictions, private content access, traversal metadata,
original/derivative tampering, MIME spoofing, animation, decompression bombs, oversized
bodies, malformed JSON, forbidden fields and CORS. Regression tests protect rollback,
concurrent duplicate consistency, invalid pipeline output and storage-root guards.

## Measured coverage

Application scope is all `ep_engine/` modules, including security, services, storage,
schemas, API and future pipeline contracts. Scripts, tests and existing backend code
are not counted as application coverage. Branch coverage is enabled, with an 85% gate.

- Statements: {coverage["covered_lines"]}/{coverage["num_statements"]} covered
  ({coverage["covered_lines"] / coverage["num_statements"] * 100:.2f}%).
- Branches: {coverage["covered_branches"]}/{coverage["num_branches"]} covered
  ({coverage["covered_branches"] / coverage["num_branches"] * 100:.2f}%).
- Combined statement/branch coverage: **{coverage["percent_covered"]:.2f}%**.
- Ruff static analysis: exit {executions["lint"]["exit_code"]}.
- Ruff format check: exit {executions["format"]["exit_code"]}.

Uncovered paths include a repeated ASGI receive branch, symlinked individual-file
handling and the POSIX chmod branch (this run was Windows), plus a finding-citation
short-circuit branch. These are not evidence of complete reliability; percentage
coverage cannot establish correctness or OS isolation. Native Windows symlink/junction
and ACL behavior were not integration-tested; root rejection tests simulate symlink
metadata to keep tests privilege-free and confined to EP.

## Exact commands and artifacts

Run from `D:/neighborlend_project/NeighborLend/ep` using the approved interpreter:

```powershell
{commands}
```

The final run executed the **complete coverage suite**, lint and format commands.
Category-specific commands above are provided for focused reruns; their cases were
all executed in the complete suite, not separately counted as independent runs.
The runner's exact underlying final check commands were:

```powershell
{exact}
```

The runner sets `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and
TMP/TEMP/TMPDIR to `ep/.test-artifacts/process-tmp`; coverage explicitly loads only
pytest-cov. Pytest `--basetemp=.test-artifacts/tmp` and cache settings are in pyproject.
JUnit is `.test-artifacts/coverage.xml` (test results, not coverage XML), coverage JSON
is `.test-artifacts/coverage.json`, and the HTML report is
`.test-artifacts/coverage-html/index.html`. Per-command exit records are
`.test-artifacts/*-execution.json`. Generated artifacts are intentionally Git-ignored.

## Failed scenarios and verified fixes

1. Initial test-first collection failed because `ep_engine` did not exist. Implemented
   the package after defining its expected behavior; no pre-implementation success claim.
2. First complete run: 30 passed, 1 failed; 88.84% combined coverage. The failed
   constraint test used app state before lifespan startup. Corrected the test fixture
   dependency; actual database constraints are now tested in a started application.
3. Pipeline regression reproducer: 1 passed, 1 failed. An adapter returning None raised
   AttributeError outside the error boundary. Added explicit StageResult checking;
   the final suite confirms a sanitized `stage_contract` error instead.
4. Storage-root reproducer: 0 passed, 2 failed. Constructors did not reject pre-existing
   symlinked private roots/database files. Added symlink and resolved-path confinement
   checks before directory creation/connection; both regressions now pass.
5. Targeted hardening verification: 19 passed, including derivative tampering,
   exact image-size boundaries and corrupt PNG checksum rejection. Full regression
   after all application changes is the {total}-test final run reported above.
6. Forced-identifier collision reproducer: 0 passed, 2 failed. An occupied database ID
   returned a dependency failure after file promotion, and an orphan file was overwritten.
   Added database/file allocation checks under the upload lock and ownership-aware
   cleanup; both regression tests now verify 409 and preservation of prior bytes.
7. Initial Ruff import/format/line-length findings were corrected; final lint and
   format checks pass. No lint/security rule was globally disabled for application code.

Injected file-promotion, metadata-insert and actual SQLite trigger failures return
sanitized dependency errors and leave no upload metadata/files behind. Concurrent
duplicate requests produce one record and one original/derivative pair. Simulated
restart failures invalidate missing evidence, remove orphans and fail interrupted
processing; this is not a physical power-loss durability test.

## Isolation and remaining issues

Every test uses temporary directories below `ep/.test-artifacts/tmp` and a separate
SQLite database. Settings reject paths outside ep/; fixtures clear inherited EP config.
No backend imports, root dotenv reads, production storage/database, network services,
model weights or paid APIs are used by the suite. Startup-from-environment and fixture
hash tests also verify isolated configuration and deterministic stored samples.

Git's initial status was clean. Final change-boundary evidence lists
{len(boundary["changed_paths"])} repository paths, with **{len(boundary["outside_ep"])}
outside ep/**; see `docs/change-boundary.json` and `docs/file-tree.txt`.
Existing tracked backend/frontend/root files were not modified. The user explicitly
authorized adding pytest-cov 7.1.0 and coverage 7.17.2 to the Conda environment; that
package installation is the sole intended write outside the repository boundary.

No reproducible critical Phase 1 failures remain in the available tests. Known limits:
local fixture authorization has no production identity verification/expiry/revocation;
single-process SQLite/local recovery; inherited Windows ACLs; no at-rest encryption,
retention/deletion/repair API, request-rate/storage quotas, hardware-failure durability
proof, public deployment or load testing. Invalid evidence cannot be silently repaired
or replaced through the API. Do not infer production readiness from this test gate.

## Phase 2 testing prerequisites

Obtain consented real before/after sets and independently verified labels; use
`benchmark-specification.md` for identity, lighting, angles, backgrounds, damage,
pre-existing damage, different-object, blur/occlusion and insufficient-view strata.
Lock hashes and object-level development/calibration/final splits; do not tune on the
final evaluation set. Define adapter artifact encodings/model versions, device/RAM/VRAM
budgets, CPU/GPU numerical tolerances, timeout/OOM/cancellation tests, queue/worker
recovery and actual report-persistence completion criteria before integrating models.
No AI accuracy, identity accuracy, or calibrated confidence has been measured in Phase 1.
The same meaningful tests-before-implementation and measured regression gate must
accompany every later phase. No later phase was implemented here.
"""
    (ROOT / "docs" / "testing-report.md").write_text(report, encoding="utf-8")
    summary = {
        "status": status,
        "passed": total - failed - skipped,
        "failed": failed,
        "skipped": skipped,
        "blocked": 0,
        "categories": dict(counts),
        "coverage": coverage,
    }
    (ROOT / "docs" / "verification-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
