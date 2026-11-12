"""Start/stop only a generated disposable loopback PostgreSQL cluster."""

import argparse
import json
import socket
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".payment-verification" / "master-20261111"
TOOLS = ROOT / ".payment-verification" / "postgres-tools" / "extracted" / "pgsql" / "bin"
STATE = ARTIFACTS / "postgres-state.json"


def command(*args):
    # pg_ctl's detached Windows child can inherit pipe handles; a regular
    # temporary file avoids waiting forever for EOF from the server process.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        result = subprocess.run(
            [str(arg) for arg in args],
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output.seek(0)
        content = output.read()
    if result.returncode:
        raise RuntimeError(content)
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "resume"])
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if args.action in {"stop", "resume"}:
        state = json.loads(STATE.read_text("utf-8"))
        cluster = Path(state["cluster"]).resolve()
        if not cluster.is_relative_to(ARTIFACTS.resolve()) or not cluster.name.startswith(
            "cluster-"
        ):
            raise RuntimeError("Only this task's generated cluster may be stopped")
        if args.action == "stop":
            print(command(TOOLS / "pg_ctl.exe", "-D", cluster, "-m", "fast", "-w", "stop"))
            return
        port = state["port"]
    elif STATE.exists():
        raise RuntimeError("A cluster is already recorded; inspect/stop it before creating another")
    else:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        cluster = ARTIFACTS / ("cluster-" + uuid4().hex)
        command(
            TOOLS / "initdb.exe",
            "-D",
            cluster,
            "-U",
            "postgres",
            "-E",
            "UTF8",
            "--no-locale",
            "--auth=trust",
        )
    command(
        TOOLS / "pg_ctl.exe",
        "-D",
        cluster,
        "-l",
        ARTIFACTS / "postgres-server.log",
        "-o",
        f"-h 127.0.0.1 -p {port}",
        "-w",
        "start",
    )
    STATE.write_text(
        json.dumps(
            {
                "cluster": str(cluster),
                "port": port,
                "loopback_only": True,
                "version": command(TOOLS / "postgres.exe", "--version").strip(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for name in (
        "neighborlend_test_catalog",
        "neighborlend_test_regressions",
        "neighborlend_test_sql",
    ):
        exists = command(
            TOOLS / "psql.exe",
            "-h",
            "127.0.0.1",
            "-p",
            port,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{name}'",
        ).strip()
        if not exists:
            command(TOOLS / "createdb.exe", "-h", "127.0.0.1", "-p", port, "-U", "postgres", name)
    print(STATE.read_text("utf-8"))


if __name__ == "__main__":
    main()
