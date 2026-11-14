"""Mounted React/FastAPI regressions with generated SQLite and mock payments only.

Requires installed Chrome, httpx, websocket-client and frontend dependencies.
Never uses the application's configured DB, Storage, mail or gateway credentials.
"""
import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"


def available_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New artifact folder; must not already exist")
    args = parser.parse_args()
    output = args.output or BACKEND / ".payment-verification" / ("stabilization-browser-" + uuid4().hex)
    output = output.resolve()
    if not output.is_relative_to((BACKEND / ".payment-verification").resolve()):
        raise SystemExit("Browser artifacts must stay within backend/.payment-verification")
    output.mkdir(parents=True, exist_ok=False)
    (output / "yolo").mkdir()
    os.environ.update(UPLOAD_DIR=str(output / "uploads"), SMTP_HOST="", SMTP_USERNAME="",
                      SMTP_PASSWORD="", GOOGLE_CLIENT_ID="", YOLO_CONFIG_DIR=str(output / "yolo"),
                      PAYMENT_TEST_POSTGRES_URL="", PYTHONDONTWRITEBYTECODE="1")
    sys.path[:0] = [str(BACKEND / ".test-tools"), str(BACKEND), str(BACKEND / "tests")]
    import conftest  # Replaces DB/JWT/gateway/storage config BEFORE importing the app.
    import httpx
    import pytest
    import uvicorn
    import websocket
    from PIL import Image
    from test_listing_conversations import add_ladder
    from test_razorpay_escrow import assert_balanced, flow, fund, physical_return

    from app.main import app

    class CheckResults(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            (output / "progress.json").write_text(json.dumps(self, indent=2), encoding="utf-8")
            print("PASS: " + key, flush=True)

    checks, errors, processes, fixtures = CheckResults(), [], [], []
    patch, ws, server, log = pytest.MonkeyPatch(), None, None, None
    server_thread = None
    sequence = 0

    def forbidden(*args, **kwargs):
        raise AssertionError("External gateway transport forbidden in browser regression")

    patch.setattr("app.services.razorpay_service.build_opener", forbidden)
    original_connect = socket.socket.connect

    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "localhost", "::1"}:
            raise AssertionError("External network forbidden in browser regression")
        return original_connect(sock, address)

    patch.setattr(socket.socket, "connect", local_connect)

    def new_rental():
        folder = output / ("fixture-" + uuid4().hex)
        folder.mkdir()
        fixture = flow.__wrapped__(folder, patch, SimpleNamespace(param="mock"))
        fixtures.append(fixture)
        return next(fixture)

    state = new_rental()
    api_port, web_port = available_port(), available_port()
    origin = f"http://127.0.0.1:{web_port}"
    photo = output / "synthetic-evidence.png"
    Image.new("RGB", (16, 16), "white").save(photo)
    try:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=api_port,
                                              log_level="critical", access_log=False, lifespan="off"))
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.1)
        assert server.started, "Isolated backend did not start"
        vite_env = os.environ.copy()
        vite_env.update(VITE_API_BASE_URL="/api", VITE_GOOGLE_CLIENT_ID="",
                        BACKEND_PROXY_TARGET=f"http://127.0.0.1:{api_port}")
        log = (output / "vite.log").open("wb")
        vite = subprocess.Popen([shutil.which("node"), str(FRONTEND / "node_modules/vite/bin/vite.js"),
                                 "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                                cwd=FRONTEND, env=vite_env, stdout=log, stderr=log,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(vite)
        profile = output / "browser-profile"
        chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                   "--headless=new", "--remote-debugging-port=0",
                                   "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(profile),
                                   "--no-first-run", "--no-default-browser-check",
                                   "--disable-background-networking", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(chrome)
        with httpx.Client(timeout=1, trust_env=False) as client:
            for _ in range(150):
                try:
                    if client.get(origin + "/login").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
        assert vite.poll() is None, "Refusing to use an unrelated frontend server"
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(.1)
        debug_port = int(active.read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{debug_port}/json/list").json()[0]
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(ws.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    detail = message["params"]["exceptionDetails"]
                    errors.append(detail.get("exception", {}).get("description", detail.get("text", "")))
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(js):
            result = cdp("Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": True})
            assert "exceptionDetails" not in result, str(result.get("exceptionDetails"))
            return result.get("result", {}).get("value")

        def wait(js):
            for _ in range(200):
                if evaluate(js):
                    return
                time.sleep(.1)
            raise AssertionError("Missing browser state: " + js + "; page: " +
                                 str(evaluate("document.body.textContent.slice(0,1800)")))

        def click(label):
            wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===" + json.dumps(label) + "&&!b.disabled)")
            evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===" + json.dumps(label) + ").click()")

        def navigate(path):
            cdp("Page.navigate", {"url": origin + path})

        def login(role, path=None):
            navigate("/login")
            wait("document.querySelector('.login-form')!==null")
            token = state["headers"][role]["Authorization"][7:]
            evaluate("localStorage.setItem('nl_token'," + json.dumps(token) + ")")
            navigate(path or "/borrow-requests/" + state["request_id"])
            wait("document.querySelector('h1')!==null && !document.body.textContent.includes('Loading request')")

        def set_value(selector, value, tag="input"):
            prototype = "HTMLTextAreaElement" if tag == "textarea" else "HTMLInputElement"
            evaluate("(()=>{const element=document.querySelector(" + json.dumps(selector) + ");" +
                     "Object.getOwnPropertyDescriptor(" + prototype + ".prototype,'value').set.call(element," +
                     json.dumps(value) + ");element.dispatchEvent(new Event('input',{bubbles:true}));})()")

        def select_photo(label):
            document = cdp("DOM.getDocument")["root"]["nodeId"]
            node = cdp("DOM.querySelector", {"nodeId": document, "selector": '[aria-label="' + label + '"]'})["nodeId"]
            cdp("DOM.setFileInputFiles", {"nodeId": node, "files": [str(photo)]})

        blocked = ["https://*", "*razorpay.com*", "*supabase.co*", "*supabase.com*",
                   "*127.0.0.1:8000*", "*localhost:8000*"]
        cdp("Page.enable")
        cdp("Runtime.enable")
        cdp("Network.enable")
        cdp("Network.setBlockedURLs", {"urls": blocked})
        cdp("Page.addScriptToEvaluateOnNewDocument", {"source":
            "window.auditErrors=[];addEventListener('unhandledrejection',e=>auditErrors.push(String(e.reason)));"})

        navigate("/admin/payments")
        wait("location.pathname==='/login' && document.querySelector('.login-form')!==null")
        checks["anonymous_admin_route_requires_login"] = True
        login("borrower", "/admin/payments")
        wait("location.pathname==='/browse'")
        assert not evaluate("document.body.textContent.includes('Test payment platform review')")
        checks["nonadmin_route_denied"] = True

        status_block = origin + "/api/payments/by-request/*"
        cdp("Network.setBlockedURLs", {"urls": blocked + [status_block]})
        login("borrower")
        wait("document.querySelector('.payment-card [role=alert]')!==null")
        assert not evaluate("document.querySelector('.payment-checkout')!==null")
        cdp("Network.setBlockedURLs", {"urls": blocked})
        click("Refresh payment status")
        wait("document.querySelector('.payment-checkout')!==null")
        assert evaluate("window.auditErrors.length===0")
        checks["mounted_initial_status_failure_and_recovery"] = True
        assert evaluate("document.body.textContent.includes('No security deposit is held until payment is captured')")
        evaluate("document.querySelector('.payment-checkout input[type=checkbox]').click()")
        click("Pay test rental + deposit")
        wait("document.querySelector('.demo-checkout')!==null")
        click("Simulate success")
        wait("document.body.textContent.includes('Payment captured')")
        checks["mounted_checkout_success_no_callback_error"] = True

        rental = state["client"].get(f"/api/payments/requests/{state['request_id']}/rental", headers=state["headers"]["borrower"]).json()
        login("borrower", "/listing/" + rental["listing_id"])
        click("Chat with owner")
        wait("location.pathname==='/messages/" + rental["conversation_id"] + "' && document.body.textContent.includes('Agreement confirmed!')")
        assert evaluate("document.querySelector('.active-offer-card').textContent.includes('₹200')")
        ladder = add_ladder(state)
        navigate("/listing/" + ladder)
        wait("document.body.textContent.includes('Ladder')")
        click("Chat with owner")
        wait("document.body.textContent.includes('No negotiation offer has been made yet.')")
        assert evaluate("location.pathname!=='/messages/" + rental["conversation_id"] + "'")
        click("Make an offer")
        assert evaluate("document.querySelector('#offer-listing').value===" + json.dumps(ladder) + "&&document.querySelector('#offer-listing').disabled")
        navigate("/listing/" + rental["listing_id"])
        wait("document.body.textContent.includes('Synthetic drill')")
        click("Chat with owner")
        wait("location.pathname==='/messages/" + rental["conversation_id"] + "' && document.body.textContent.includes('Agreement confirmed!')")
        checks["listing_chat_preserves_thread_offer_and_listing_selection"] = True

        login("lender")
        wait("document.querySelector('[aria-label=\"Product handover photos\"]')!==null")
        cdp("Network.setBlockedURLs", {"urls": blocked + [status_block]})
        click("Refresh payment status")
        wait("document.querySelector('[aria-label=\"Product handover photos\"]')===null")
        assert evaluate("document.body.textContent.includes('Handover stays locked') && window.auditErrors.length===0")
        cdp("Network.setBlockedURLs", {"urls": blocked})
        click("Refresh payment status")
        wait("document.querySelector('[aria-label=\"Product handover photos\"]')!==null")
        checks["mounted_refresh_failure_locks_controls_and_recovers"] = True
        select_photo("Product handover photos")
        click("Upload 1 photo(s)")
        wait("document.body.textContent.includes('Photos uploaded')")
        login("borrower")
        click("I received this item")
        wait("document.body.textContent.includes('Borrower confirmed')")
        login("lender")
        click("Confirm handover complete")
        wait("document.body.textContent.includes('Borrowing is active.')")
        assert not evaluate("document.querySelector('[aria-label=\"Submit return evidence\"]')!==null")
        login("borrower")
        wait("document.querySelector('[aria-label=\"Return photos\"]')!==null")
        select_photo("Return photos")
        click("Submit 1 return photo(s)")
        wait("document.querySelector('[aria-label=\"Return photos\"]')===null")
        checks["mounted_handover_and_borrower_only_return_upload"] = True
        login("lender")
        click("Approve return")
        wait("document.body.textContent.includes('Return approved.')")
        assert not evaluate("document.body.textContent.includes('Rate the borrower')")
        assert not evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Approve return')")
        checks["approved_return_waits_for_financial_rating_eligibility"] = True

        login("admin", "/admin/payments")
        wait("document.querySelector('a[href=\"/borrow-requests/" + state["request_id"] + "\"]')!==null")
        evaluate("document.querySelector('a[href=\"/borrow-requests/" + state["request_id"] + "\"]').click()")
        wait("document.body.textContent.includes('Private rental evidence') && document.body.textContent.includes('Simulate / reconcile authorized refund')")
        wait("document.querySelectorAll('[aria-label=\"Rental evidence for administrator review\"] img').length>=2")
        shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
        (output / "independent-admin-review.png").write_bytes(base64.b64decode(shot))
        click("Simulate / reconcile authorized refund")
        wait("document.body.textContent.includes('Settlement completed')")
        assert_balanced(state)
        checks["independent_admin_queue_evidence_and_mock_refund"] = True
        login("borrower")
        wait("document.body.textContent.includes('Rate the lender')")
        evaluate("document.querySelector('[aria-label=\"5 of 5\"]').click()")
        click("Submit rating")
        wait("document.body.textContent.includes('Lender rating:')")
        checks["mounted_rating_uses_backend_completed_settlement"] = True

        # A second isolated rental exercises rejection/claim/admin deduction.
        cdp("Page.navigate", {"url": "about:blank"})
        state = new_rental()
        fund(state)
        physical_return(state)
        login("lender")
        click("Reject and start dispute review")
        wait("document.body.textContent.includes('independent human review pending')")
        assert not evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Approve return')")
        wait("document.body.textContent.includes('Return condition rejected.')")
        set_value('.payment-dispute textarea', 'Synthetic casing damage', 'textarea')
        set_value('.payment-dispute input[inputmode=decimal]', '100')
        click("Submit or revise human claim")
        wait("document.body.textContent.includes('Claim saved:')")
        checks["mounted_rejected_return_freezes_and_preserves_claim_review"] = True
        login("admin")
        wait("document.body.textContent.includes('Administrator resolution reason')")
        set_value('.payment-dispute textarea', 'Independent synthetic evidence review', 'textarea')
        click("Record administrator settlement decision")
        wait("document.body.textContent.includes('Simulate / reconcile authorized refund')")
        click("Simulate / reconcile authorized refund")
        wait("document.body.textContent.includes('Settlement completed')")
        saved = state["client"].get(f"/api/payments/by-request/{state['request_id']}", headers=state["headers"]["admin"]).json()
        assert saved["deduction_paise"] == 10000 and saved["deposit_refunded_paise"] == 40000
        assert_balanced(state)
        login("borrower")
        wait("document.body.textContent.includes('Rate the lender')")
        checks["independent_admin_dispute_deduction_refund_and_resolved_rating"] = True

        cdp("Page.navigate", {"url": "about:blank"})
        state = new_rental()
        fund(state)
        login("borrower")
        click("Cancel before receipt")
        wait("document.body.textContent.includes('Authorized') && document.querySelector('.refund-panel')!==null")
        assert evaluate("document.querySelector('.payment-card')!==null && !document.body.textContent.includes('Request not found')")
        login("admin")
        click("Simulate / reconcile authorized refund")
        wait("document.body.textContent.includes('Booking cancelled')")
        saved = state["client"].get(f"/api/payments/by-request/{state['request_id']}", headers=state["headers"]["admin"]).json()
        assert saved["refund"]["amount_paise"] == 90000
        assert saved["reconciliation"]["processed_deposit_refund_paise"] == 50000
        assert_balanced(state)
        checks["cancelled_rental_private_review_and_full_mock_refund"] = True
        assert evaluate("window.auditErrors.length===0")
        assert not errors, errors
        checks["unhandled_browser_exceptions"] = 0
        (output / "results.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output), "checks": checks}, indent=2), flush=True)
        cdp("Browser.close")
    except BaseException:
        (output / "partial-results.json").write_text(json.dumps({"checks": checks, "errors": errors}, indent=2), encoding="utf-8")
        raise
    finally:
        if ws:
            ws.close()
        cleanup_errors = []
        for process in reversed(processes):
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
            except (OSError, subprocess.TimeoutExpired) as exc:
                cleanup_errors.append({"pid": process.pid, "error": type(exc).__name__})
        if log:
            log.close()
        if server:
            server.should_exit = True
        if server_thread:
            server_thread.join(timeout=15)
        for fixture in reversed(fixtures):
            fixture.close()
        patch.undo()
        from app.database import engine
        engine.dispose()
        conftest._TEST_DATABASE.unlink(missing_ok=True)
        (output / "cleanup.json").write_text(json.dumps({"process_errors": cleanup_errors}, indent=2), encoding="utf-8")
        if cleanup_errors:
            raise RuntimeError("Browser regression left processes requiring cleanup; see cleanup.json")


if __name__ == "__main__":
    main()
