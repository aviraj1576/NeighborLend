"""Verify private sandbox services; optionally reload only the recorded owned stack."""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from prepare_sandbox_scenarios import OUTPUT, ROOT, STACK, fingerprints, require, save


def restart_owned():
    import psutil

    state = json.loads((STACK / "stack-state.json").read_text("utf-8"))
    require(
        state["isolated"] and state["backend_port"] == 8001 and state["webhook_proxy_port"] == 8010,
        "Unexpected stack",
    )
    database = Path(state["database"]).resolve()
    require(database.is_relative_to(STACK.resolve()), "Unexpected database")
    before = fingerprints(database)
    processes = []
    for pid, module in [(state["controller_pid"], "scripts/run_test_webhook_stack.py")] + [
        (
            child["pid"],
            "app.main:app" if child["port"] == 8001 else "app.webhook_ingress:create_app",
        )
        for child in state["children"]
    ]:
        process = psutil.Process(pid)
        require(
            Path(process.exe()).resolve() == Path(sys.executable).resolve()
            and Path(process.cwd()).resolve() == ROOT,
            "Unexpected process identity",
        )
        arguments = process.cmdline()
        require(
            any(arg.replace("\\", "/").endswith(module) for arg in arguments),
            "Unexpected process module",
        )
        if module != "scripts/run_test_webhook_stack.py":
            require(
                "--host" in arguments and arguments[arguments.index("--host") + 1] == "127.0.0.1",
                "Non-loopback process",
            )
        processes.append(process)
    require(len(processes) == 3 and len({p.pid for p in processes}) == 3, "Unexpected process set")
    save(OUTPUT / "stack-before-reload.json", state)
    for process in processes:
        try:
            process.terminate()
            process.wait(timeout=10)
        except psutil.NoSuchProcess:
            pass
    with (OUTPUT / "reloaded-stack.log").open("ab") as stream:
        child = subprocess.Popen(
            [sys.executable, "-B", "scripts/run_test_webhook_stack.py", "--reuse-isolated-state"],
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    for _ in range(160):
        require(child.poll() is None, "Reloaded stack failed")
        current = json.loads((STACK / "stack-state.json").read_text("utf-8"))
        if current.get("controller_pid") == child.pid and current.get("ready"):
            require(
                current["database"] == str(database) and current["reused_database"],
                "Reloaded database changed",
            )
            require(fingerprints(database) == before, "Rows changed during reload")
            return
        time.sleep(0.25)
    raise RuntimeError("Reloaded stack timeout")


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reload-owned-stack", action="store_true")
    parser.add_argument(
        "--public-proxy-url", help="Optional existing HTTPS tunnel URL; GET denials only"
    )
    args = parser.parse_args()
    require(OUTPUT.is_dir(), "Prepare scenarios first")
    if args.reload_owned_stack:
        restart_owned()
    import httpx

    state = json.loads((OUTPUT / "scenarios.json").read_text("utf-8"))
    accounts = json.loads((OUTPUT / "scenario-accounts.json").read_text("utf-8"))
    database = Path(state["database"])
    before = fingerprints(database)
    checks = {}
    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
        api, ui, proxy = "http://127.0.0.1:8001", "http://127.0.0.1:5175", "http://127.0.0.1:8010"
        require(client.get(api + "/api/health").status_code == 200, "Private health unavailable")
        schema = client.get(api + "/openapi.json").json()
        require("/api/payments/refunds/execute" in schema["paths"], "Backend needs reload")
        checks["current_refund_approval_api_loaded"] = True
        require(client.get(ui + "/login").status_code == 200, "React unavailable")
        account = accounts["borrower"]
        login = client.post(
            ui + "/api/auth/login",
            json={"username_or_email": account["username"], "password": account["password"]},
        )
        require(login.status_code == 200, "Normal login failed")
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        for name, row in state["scenarios"].items():
            booking = client.get(
                ui + "/api/payments/bookings/" + row["booking_id"], headers=headers
            ).json()
            require(
                booking["total_amount_paise"] == 250000
                and booking["sandbox_only"] is True
                and booking["test_mode"] is True
                and booking["provider"] == "razorpay_test"
                and booking["payment_status"] == "order_created"
                and not booking["handover_unlocked"],
                "Scenario changed or handover unlocked",
            )
            require(
                client.get(row["checkout_url"]).status_code == 200, "Checkout route unavailable"
            )
            checks["scenario_" + name + "_unpaid_locked_and_reachable"] = True
        original = client.get(
            api + "/api/payments/bookings/a9274a7e-2bce-421d-8f43-f62d4c34b769", headers=headers
        )
        require(original.status_code == 403, "Original booking leaked to new fixture user")
        checks["new_fixtures_cannot_access_original_booking"] = True
        for path in (
            "/docs",
            "/api/health",
            "/api/auth/login",
            "/api/payments/create-order",
            "/api/admin",
        ):
            require(client.get(proxy + path).status_code == 404, "Proxy exposes private API")
        invalid = client.post(
            proxy + "/api/payments/webhook",
            content=b"{}",
            headers={
                "x-razorpay-event-id": "evt_FinalizationInvalid",
                "x-razorpay-signature": "0" * 64,
            },
        )
        require(invalid.status_code == 400, "Invalid HMAC accepted")
        checks["proxy_isolation_and_invalid_hmac_rejection"] = True
        require(
            client.get(api + "/api/health", headers={"Host": "public.example.test"}).status_code
            == 403,
            "Public Host accepted by private backend",
        )
        checks["private_backend_rejects_public_host"] = True
        require(
            "RefundPanel" in client.get(ui + "/src/components/EscrowStatusCard.jsx").text,
            "Frontend missing updated refund component",
        )
        for path in (ROOT / ".env", OUTPUT / "scenario-accounts.json"):
            require(
                client.get(ui + "/@fs/" + path.as_posix()).status_code in {403, 404},
                "Frontend serves private credential files",
            )
        checks["current_ui_loaded_and_private_files_denied"] = True
        if args.public_proxy_url:
            from urllib.parse import urlparse

            parsed = urlparse(args.public_proxy_url)
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.hostname.endswith(".trycloudflare.com")
                and not parsed.username
                and not parsed.password
                and parsed.path in {"", "/"},
                "Unexpected tunnel URL",
            )
            for path in ("/docs", "/api/health", "/api/payments/create-order", "/api/admin"):
                require(
                    client.get(args.public_proxy_url.rstrip("/") + path).status_code == 404,
                    "Public tunnel exposes private route or is unavailable",
                )
            checks["public_private_route_denials"] = True
    require(before == fingerprints(database), "Runtime verification mutated stored rows")
    checks["runtime_check_preserved_all_rows_and_credentials"] = True
    report = {
        "checks": checks,
        "owned_stack_reloaded": args.reload_owned_stack,
        "public_tunnel_checked": bool(args.public_proxy_url),
        "genuine_webhook_origin_verified": False,
        "gateway_mutations": 0,
    }
    save(OUTPUT / "runtime-verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "Runtime verification stopped: "
            + (str(exc) if type(exc) is RuntimeError else type(exc).__name__),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
