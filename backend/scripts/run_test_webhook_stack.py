"""Start loopback API + webhook ingress with a new or explicitly reused isolated DB.

The existing backend and .env files are never modified. No tunnel is started.
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".payment-verification" / "webhook-ingress-20261110-01"
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-isolated-state",
        action="store_true",
        help="Restart against the exact existing isolated DB without schema creation/migration",
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from app.config import Settings
    from app.services.razorpay_service import configured_provider

    initial = Settings()
    if (
        initial.deployment_exposure != "local"
        or initial.app_env.lower() in {"prod", "production"}
        or configured_provider(initial).kind != "razorpay_test"
    ):
        raise RuntimeError("Local Razorpay Test configuration is required")
    for port in (8001, 8010):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if args.reuse_isolated_state:
        previous = json.loads((ARTIFACTS / "stack-state.json").read_text("utf-8"))
        directory, database = (
            Path(previous["directory"]).resolve(),
            Path(previous["database"]).resolve(),
        )
        if (
            not previous.get("isolated")
            or not directory.is_relative_to(ARTIFACTS.resolve())
            or database.parent != directory
            or database.name != "isolated.sqlite3"
            or not database.is_file()
            or previous.get("backend_port") != 8001
            or previous.get("webhook_proxy_port") != 8010
        ):
            raise RuntimeError("Only the existing isolated webhook database may be reused")
    else:
        directory = ARTIFACTS / ("stack-" + uuid4().hex)
        directory.mkdir()
        database = directory / "isolated.sqlite3"
        if database.exists() or not database.resolve().is_relative_to(ARTIFACTS.resolve()):
            raise RuntimeError("A new isolated database is required")
    os.environ.update(
        {
            "DATABASE_URL": "sqlite:///" + database.as_posix(),
            "APP_ENV": "test",
            "AUTO_MIGRATE": "false",
            "UPLOAD_DIR": str(directory / "uploads"),
            "RENTAL_EVIDENCE_DIR": str(directory / "evidence"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join((str(ROOT / ".test-tools"), str(ROOT))),
        }
    )
    from app import models, payment_models  # noqa: F401
    from app.database import Base, engine

    if Path(engine.url.database).resolve() != database.resolve():
        raise RuntimeError("Database isolation validation failed")
    if not args.reuse_isolated_state:
        Base.metadata.create_all(engine)
    engine.dispose()
    children, logs = [], []
    state = {
        "controller_pid": os.getpid(),
        "database": str(database),
        "isolated": True,
        "backend_port": 8001,
        "webhook_proxy_port": 8010,
        "tunnel_started": False,
        "reused_database": args.reuse_isolated_state,
        "directory": str(directory),
        "children": [],
    }
    try:
        for module, port in (("app.main:app", 8001), ("app.webhook_ingress:create_app", 8010)):
            stream = (directory / f"server-{port}.log").open(
                "ab" if args.reuse_isolated_state else "wb"
            )
            logs.append(stream)
            command = [
                sys.executable,
                "-B",
                "-m",
                "uvicorn",
                module,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-proxy-headers",
                "--no-access-log",
                "--no-server-header",
                "--log-level",
                "warning",
            ]
            if port == 8010:
                command.append("--factory")
            child = subprocess.Popen(
                command,
                cwd=ROOT,
                env=os.environ.copy(),
                stdout=stream,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            children.append(child)
            state["children"].append({"pid": child.pid, "port": port})
        for _ in range(150):
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A local server failed to start; logs remain private")
            ready = []
            for port in (8001, 8010):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        ready.append(port)
                except OSError:
                    pass
            if len(ready) == 2:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Local server startup timeout")
        state["ready"] = True
        (ARTIFACTS / "stack-state.json").write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "Webhook-only proxy ready on 127.0.0.1:8010; isolated API on 127.0.0.1:8001.",
            flush=True,
        )
        while all(p.poll() is None for p in children):
            time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for stream in logs:
            stream.close()
        state["ready"] = False
        (directory / "stopped.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # Do not print exceptions that might contain environment values.
        print("Test webhook stack failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
