"""Full App browser hit-testing: live GETs only, financial clicks isolated in memory."""

import argparse
import base64
import copy
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]
OUTPUT = ROOT / ".payment-verification/refund-controls-20261112"
REQUEST_ID = "0d2d9947-bc15-43cb-87e5-ca7c4b3042c4"


def main():
    import httpx
    import websocket

    from scripts.provision_fictional_accounts import inputs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-blocked", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Replay the saved live GET snapshot")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=45, trust_env=False,
                         follow_redirects=False)
    booking_path = "/api/payments/by-request/" + REQUEST_ID
    rental_path = "/api/payments/requests/" + REQUEST_ID + "/rental"
    fixture = OUTPUT / "live-get-snapshot.json"
    headers = {}
    if args.offline:
        cache = json.loads(fixture.read_text(encoding="utf-8"))
    else:
        account = next(row for row in inputs() if row["username"] == "priya_sharma")
        login = client.post("/api/auth/login", json={"username_or_email": account["username"],
                                                    "password": account["password"]})
        assert login.status_code == 200, "Local admin authentication failed"
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        cache = {"/api/auth/me": me.json()}
        for path in (booking_path, rental_path):
            print("Read-only API check: " + path, flush=True)
            response = client.get(path, headers=headers)
            assert response.status_code == 200, "Authenticated live GET denied: " + path
            cache[path] = response.json()
        fixture.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    identity = cache["/api/auth/me"]
    assert identity["username"] == "priya_sharma" and identity["is_admin"] is True
    booking = cache[booking_path]
    assert booking["refund"]["status"] == "created"
    assert booking["refund"]["amount_paise"] == 200000
    assert booking["rental_fee_paise"] == 50000 and booking["operations_enabled"] is True
    assert identity["id"] not in {booking["borrower_id"], booking["lender_id"]}
    # The bridge forwards only authenticated GETs. It never forwards a financial POST.
    state = {"live": not args.offline, "booking": copy.deepcopy(booking), "posts": [], "reads": []}

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def send(self, status, data, media="application/json"):
            body = json.dumps(data).encode() if media == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path
            state["reads"].append(path)
            if path in cache and path != booking_path:
                self.send(200, cache[path])
            elif state["live"]:
                result = client.get(path, headers=headers)
                media = result.headers.get("content-type", "application/json").split(";")[0]
                data = result.json() if media == "application/json" else result.content
                if media == "application/json" and result.status_code == 200:
                    cache[path] = data
                self.send(result.status_code, data, media)
            elif path == booking_path:
                self.send(200, state["booking"])
            elif path == "/api/notifications/unread-count":
                self.send(200, {"unread_count": 0})
            elif path in cache:
                self.send(200, cache[path])
            elif path.startswith("/api/payments/evidence/"):
                self.send(200, base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="
                ), "image/png")
            else:
                self.send(404, {"detail": "No isolated fixture for this route"})

        def do_POST(self):
            if state["live"]:
                self.send(405, {"detail": "Live mutations are forbidden"})
                return
            if self.headers.get("Authorization") != "Bearer isolated-browser-session":
                self.send(401, {"detail": "Isolated session required"})
                return
            if cache["/api/auth/me"].get("is_admin") is not True:
                self.send(403, {"detail": "Administrator access required"})
                return
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path not in {"/api/payments/refunds/execute", "/api/payments/refunds/reconcile"}:
                self.send(405, {"detail": "Only isolated refund fixtures are permitted"})
                return
            current = state["booking"]
            if data.get("booking_id") != current["id"]:
                self.send(403, {"detail": "Wrong booking"})
                return
            if self.path.endswith("/execute") and data.get("gateway_refund_approved") is not True:
                self.send(403, {"detail": "Explicit gateway refund approval is required"})
                return
            state["posts"].append({"path": self.path, "body": data})
            current["refund"]["status"] = "pending" if self.path.endswith("/execute") else "processed"
            if current["refund"]["status"] == "processed":
                current.update(booking_status="completed", deposit_state="settled",
                               deposit_refunded_paise=200000, held_deposit_paise=0)
            self.send(200, current)

    bridge = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        vite_port = probe.getsockname()[1]
    processes, connection = [], None
    log = (OUTPUT / "full-app-vite.log").open("wb")
    report = {"api_source": "saved authenticated GET snapshot" if args.offline else "live read-only GETs",
              "admin_identity": {"username": identity["username"], "is_admin": True,
                                  "is_participant": False}, "checks": {}}
    try:
        env = {**os.environ, "VITE_API_BASE_URL": "/api",
               "BACKEND_PROXY_TARGET": f"http://127.0.0.1:{bridge.server_port}"}
        # Separate optimizer state from the developer's Vite process and other tests.
        vite_options = {"cacheDir": str(OUTPUT / "vite-cache"),
                        "server": {"host": "127.0.0.1", "port": vite_port, "strictPort": True}}
        vite = subprocess.Popen([
            shutil.which("node"), "--input-type=module", "-e",
            "import {createServer} from 'vite'; const server=await createServer("
            + json.dumps(vite_options) + "); await server.listen(); server.printUrls();",
        ], cwd=ROOT.parent / "frontend", env=env, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(vite)
        base = f"http://127.0.0.1:{vite_port}"
        for _ in range(100):
            try:
                if httpx.get(base, timeout=1, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        assert vite.poll() is None, "Isolated Vite server failed to start"
        profile = OUTPUT / ("browser-" + uuid4().hex)
        chrome = subprocess.Popen([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
            "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(chrome)
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(.1)
        port = int(active.read_text().splitlines()[0])
        page = httpx.get(f"http://127.0.0.1:{port}/json/list", trust_env=False).json()[0]
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30,
                                                 suppress_origin=True)
        sequence, browser_errors = 0, []

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    browser_errors.append(message["params"]["exceptionDetails"]["text"])
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(expression):
            value = cdp("Runtime.evaluate", {"expression": expression, "awaitPromise": True,
                                             "returnByValue": True})
            assert "exceptionDetails" not in value, str(value.get("exceptionDetails"))
            return value.get("result", {}).get("value")

        def wait(expression):
            for _ in range(100):
                if evaluate(expression):
                    return
                time.sleep(.1)
            debug = evaluate("({text:document.body.textContent.slice(0,1600),url:location.pathname,ready:document.readyState,origin:performance.timeOrigin})")
            raise AssertionError("Browser did not reach: " + expression + "; " + json.dumps(debug)
                                 + "; errors=" + str(browser_errors))

        def click(selector):
            point = evaluate("""(()=>{const el=document.querySelector(%s);
              el.scrollIntoView({block:'center',behavior:'instant'}); const r=el.getBoundingClientRect();
              return {x:r.x+r.width/2,y:r.y+r.height/2};})()""" % json.dumps(selector))
            cdp("Input.dispatchMouseEvent", {"type": "mousePressed", **point,
                                             "button": "left", "clickCount": 1})
            cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", **point,
                                             "button": "left", "clickCount": 1})

        def key(name, code, virtual):
            for kind in ("keyDown", "keyUp"):
                event = {"type": kind, "key": name, "code": code,
                         "windowsVirtualKeyCode": virtual}
                if name == "Enter" and kind == "keyDown":
                    event.update(text="\r", unmodifiedText="\r")
                cdp("Input.dispatchKeyEvent", event)

        def inspect():
            return evaluate("""(()=>{const el=document.querySelector('.refund-approval input');
              el.scrollIntoView({block:'center',behavior:'instant'});const r=el.getBoundingClientRect();
              const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
              const describe=e=>{const s=getComputedStyle(e),b=e.getBoundingClientRect();return {
                tag:e.tagName,classes:e.className,position:s.position,zIndex:s.zIndex,
                pointerEvents:s.pointerEvents,height:s.height,minHeight:s.minHeight,overflow:s.overflow,
                transform:s.transform,isolation:s.isolation,backgroundColor:s.backgroundColor,
                fontFamily:s.fontFamily,top:b.top,bottom:b.bottom};};
              const chain=[];for(let e=el;e;e=e.parentElement)chain.push(describe(e));
              const card=document.querySelector('.rental-detail-card'),footer=document.querySelector('footer');
              return {checkboxDisabled:el.disabled,checkboxChecked:el.checked,
                hitIsCheckbox:hit===el,hit:describe(hit),ancestors:chain,footer:describe(footer),
                card:describe(card),footerOverlapsCard:footer.getBoundingClientRect().top<card.getBoundingClientRect().bottom,
                fixedOrAbsoluteOverlays:[...document.querySelectorAll('body *')].filter(e=>{
                  const b=e.getBoundingClientRect();return ['fixed','absolute'].includes(getComputedStyle(e).position)
                    && b.left<=r.x+r.width/2 && b.right>=r.x+r.width/2 && b.top<=r.y+r.height/2 && b.bottom>=r.y+r.height/2;
                }).map(describe),
                buttons:[...document.querySelectorAll('.refund-panel button')].map(b=>({text:b.textContent,
                  disabled:b.disabled,pointerEvents:getComputedStyle(b).pointerEvents}))};})()""")

        cdp("Page.enable")
        cdp("Runtime.enable")
        cdp("Network.enable")
        cdp("Network.setBlockedURLs", {"urls": ["https://*", "*razorpay.com*", "*supabase*",
                                                     "http://127.0.0.1:8000/*"]})
        cdp("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('nl_token','isolated-browser-session');"})
        cdp("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        cdp("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900,
                                                   "deviceScaleFactor": 1, "mobile": False})
        cdp("Page.navigate", {"url": base + "/borrow-requests/" + REQUEST_ID})
        wait("document.querySelector('.refund-approval input')!==null")
        report["live_dom"] = inspect()
        (OUTPUT / ("before.json" if args.expect_blocked else "after.json")).write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        capture = cdp("Page.captureScreenshot", {"format": "png"})
        (OUTPUT / ("before.png" if args.expect_blocked else "after.png")).write_bytes(
            base64.b64decode(capture["data"]))
        # Record capture/bubble targets without cancelling any native or React event.
        evaluate("window.pointerTrace=[];for(const capture of [true,false])document.addEventListener('click',e=>pointerTrace.push({capture,target:e.target.tagName,classes:e.target.className}),capture)")
        click(".refund-approval input")
        selected = evaluate("document.querySelector('.refund-approval input').checked")
        report["live_click"] = {"selected": selected, "events": evaluate("pointerTrace")}
        report["live_send"] = evaluate("""(()=>{const el=[...document.querySelectorAll('.refund-panel button')]
          .find(b=>b.textContent==='Send approved Test refund');el.dataset.send='true';
          el.scrollIntoView({block:'center',behavior:'instant'});const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return {disabled:el.disabled,hitIsButton:hit===el,hitTag:hit.tagName,hitClasses:hit.className,
            pointerEvents:getComputedStyle(el).pointerEvents};})()""")
        assert state["posts"] == [], "No live financial operation is permitted"
        if args.expect_blocked:
            assert report["live_dom"]["footerOverlapsCard"]
            assert not report["live_dom"]["checkboxDisabled"]
            assert not selected or not report["live_send"]["hitIsButton"]
            if selected:
                assert not report["live_send"]["disabled"]
                click("[data-send]")
                assert state["posts"] == []
                report["live_send"]["events"] = evaluate("pointerTrace")
            report["checks"]["reproduced_enabled_refund_control_physically_blocked"] = True
        else:
            assert selected and report["live_dom"]["hitIsCheckbox"]
            assert not report["live_send"]["disabled"] and report["live_send"]["hitIsButton"]
            assert not report["live_dom"]["footerOverlapsCard"]
            report["checks"]["full_app_checkbox_receives_real_pointer_click"] = True
            # From here all APIs are local memory fixtures; no request reaches the live backend.
            state["live"] = False
            for width, height in ((1440, 900), (1280, 720), (1024, 768), (768, 1024), (390, 844)):
                cdp("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                                                           "deviceScaleFactor": 1, "mobile": width < 640})
                previous_document = evaluate("performance.timeOrigin")
                cdp("Page.reload")
                wait(f"performance.timeOrigin!=={previous_document} && document.readyState==='complete' && document.querySelector('.refund-approval input')!==null")
                info = inspect()
                assert info["hitIsCheckbox"] and not info["footerOverlapsCard"], str(info)
                assert all(row["disabled"] for row in info["buttons"])
                assert evaluate("document.documentElement.scrollWidth<=innerWidth")
                click(".financial-timeline summary")
                assert evaluate("document.querySelector('.financial-timeline').open")
                expanded = inspect()
                assert expanded["hitIsCheckbox"] and not expanded["footerOverlapsCard"]
                assert evaluate("document.querySelector('footer').getBoundingClientRect().bottom>=document.querySelector('.footer-credit').getBoundingClientRect().bottom")
                click(".financial-timeline summary")
                click(".refund-approval input")
                wait("document.querySelector('.refund-approval input').checked")
                assert evaluate("[...document.querySelectorAll('.refund-panel button')].some(b=>b.textContent==='Send approved Test refund'&&!b.disabled)")
                # Native keyboard activation and tab order must reach the same control.
                evaluate("document.querySelector('.refund-approval input').focus()")
                key(" ", "Space", 32)
                wait("!document.querySelector('.refund-approval input').checked")
                key(" ", "Space", 32)
                wait("document.querySelector('.refund-approval input').checked")
                key("Tab", "Tab", 9)
                assert evaluate("document.activeElement.textContent==='Send approved Test refund'")
                report["checks"][f"pointer_keyboard_and_no_overlap_{width}"] = True
            key("Enter", "Enter", 13)
            try:
                wait("document.querySelector('.refund-panel').textContent.includes('Pending provider confirmation')")
            except AssertionError:
                print(json.dumps({"isolated_posts": state["posts"], "browser_state": evaluate("({active:document.activeElement.outerHTML,panel:document.querySelector('.refund-panel').textContent,alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.textContent)})")}), flush=True)
                raise
            assert len(state["posts"]) == 1
            assert state["posts"][0]["body"]["gateway_refund_approved"] is True
            report["checks"]["keyboard_send_calls_isolated_execute_once_and_refreshes_pending"] = True
            evaluate("[...document.querySelectorAll('.refund-panel button')].find(b=>b.textContent==='Reconcile refund status (no new refund)').setAttribute('data-reconcile','true')")
            click("[data-reconcile]")
            wait("document.querySelector('.refund-panel').textContent.includes('Processed — confirmed settlement')")
            assert len(state["posts"]) == 2 and state["posts"][1]["path"].endswith("/reconcile")
            report["checks"]["pointer_reconcile_refreshes_confirmed_state"] = True
            # A fresh synthetic booking verifies native Send clicks as well as Enter.
            state["booking"] = copy.deepcopy(booking)
            state["booking"]["id"] = str(uuid4())
            previous_document = evaluate("performance.timeOrigin")
            cdp("Page.reload")
            wait(f"performance.timeOrigin!=={previous_document} && document.readyState==='complete' && document.querySelector('.refund-approval input')!==null")
            click(".refund-approval input")
            wait("document.querySelector('.refund-approval input').checked")
            evaluate("[...document.querySelectorAll('.refund-panel button')].find(b=>b.textContent==='Send approved Test refund').setAttribute('data-send','true')")
            click("[data-send]")
            wait("document.querySelector('.refund-panel').textContent.includes('Pending provider confirmation')")
            assert len(state["posts"]) == 3
            assert state["posts"][-1]["body"]["booking_id"] == state["booking"]["id"]
            assert state["posts"][-1]["body"]["gateway_refund_approved"] is True
            report["checks"]["pointer_send_executes_fresh_isolated_booking_once"] = True
            cache["/api/borrow-requests/" + REQUEST_ID + "/handover"] = cache[rental_path]
            for role, username in (("borrower", "aarav_mehta"), ("lender", "rohan_kapoor")):
                cache["/api/auth/me"] = {**identity, "id": booking[role + "_id"],
                                         "username": username, "is_admin": False}
                previous_document = evaluate("performance.timeOrigin")
                cdp("Page.reload")
                wait(f"performance.timeOrigin!=={previous_document} && document.readyState==='complete' && document.querySelector('.refund-panel')!==null")
                assert evaluate("document.querySelector('.refund-panel').textContent.includes('Only an administrator can send or reconcile')")
                assert evaluate("document.querySelectorAll('.refund-panel button,.refund-panel input[type=checkbox]').length===0")
                assert len(state["posts"]) == 3
                report["checks"][role + "_can_view_status_but_has_no_refund_controls"] = True
            assert not browser_errors, browser_errors
            report["checks"]["no_uncaught_browser_errors"] = True
        report["isolated_actions"] = state["posts"]
        (OUTPUT / ("before.json" if args.expect_blocked else "after.json")).write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"api_source": report["api_source"], "admin_identity": report["admin_identity"], "checks": report["checks"],
                          "layout": {"footerOverlapsCard": report["live_dom"]["footerOverlapsCard"],
                                     "checkboxHit": report["live_dom"]["hit"]["tag"]},
                          "live_click": report["live_click"],
                          "live_send": report["live_send"]}, indent=2))
        cdp("Browser.close")
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            if process.poll() is None:
                # Stop each owned tree before its parent exits, so Chrome children
                # cannot keep making reads after the isolated bridge shuts down.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            process.wait(timeout=10)
        bridge.shutdown()
        bridge.server_close()
        client.close()
        log.close()


if __name__ == "__main__":
    main()
