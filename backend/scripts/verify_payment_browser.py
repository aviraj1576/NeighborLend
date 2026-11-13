"""Headless Chrome UI checks with an isolated profile and no checkout completion.

Requires existing httpx and websocket-client. Refund interactions render explicitly
labelled synthetic UI state with an in-memory callback; they never call an API.
"""

import base64
import json
import logging
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from prepare_sandbox_scenarios import OUTPUT, fingerprints, require, save


def main():
    import httpx
    import websocket

    logging.disable(logging.CRITICAL)
    state = json.loads((OUTPUT / "scenarios.json").read_text("utf-8"))
    accounts = json.loads((OUTPUT / "scenario-accounts.json").read_text("utf-8"))
    database = Path(state["database"])
    before = fingerprints(database)
    profile = OUTPUT / ("browser-profile-" + uuid4().hex)
    browser = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    require(browser.is_file(), "Chrome required")
    process = subprocess.Popen(
        [
            str(browser),
            "--headless=new",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile),
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    connection = None
    checks, sequence = {}, 0
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(0.1)
        require(active.exists(), "Chrome debug port unavailable")
        port = int(active.read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{port}/json/list").json()[0]
            connection = websocket.create_connection(
                page["webSocketDebuggerUrl"], timeout=20, suppress_origin=True
            )

            def cdp(method, params=None):
                nonlocal sequence
                sequence += 1
                request_id = sequence
                connection.send(
                    json.dumps({"id": request_id, "method": method, "params": params or {}})
                )
                while True:
                    message = json.loads(connection.recv())
                    if message.get("id") == request_id:
                        require("error" not in message, "Browser protocol error: " + method)
                        return message.get("result", {})

            def evaluate(expression):
                result = cdp(
                    "Runtime.evaluate",
                    {"expression": expression, "awaitPromise": True, "returnByValue": True},
                )
                require("exceptionDetails" not in result, "Browser expression failed")
                return result.get("result", {}).get("value")

            def wait_for(expression):
                for _ in range(100):
                    if evaluate(expression):
                        return
                    time.sleep(0.1)
                raise RuntimeError("Browser UI did not become ready")

            cdp("Page.enable")
            cdp("Runtime.enable")
            cdp("Network.enable")
            cdp("Network.setBlockedURLs", {"urls": ["*razorpay.com*", "*razorpay.in*"]})
            ui = "http://127.0.0.1:5175"
            cdp("Page.navigate", {"url": ui + "/login"})
            wait_for("document.readyState === 'complete'")
            account = accounts["borrower"]
            response = client.post(
                ui + "/api/auth/login",
                json={"username_or_email": account["username"], "password": account["password"]},
            )
            require(response.status_code == 200, "Fixture login failed")
            # Token stays only in this disposable browser profile and never appears in output.
            evaluate(
                "localStorage.setItem('nl_token', "
                + json.dumps(response.json()["access_token"])
                + ")"
            )
            for width, label in ((1280, "desktop"), (390, "mobile")):
                cdp(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": width < 600},
                )
                cdp("Page.navigate", {"url": state["scenarios"]["A"]["checkout_url"]})
                wait_for("document.querySelector('.payment-checkout button') !== null")
                evaluate("""(async () => {await document.fonts.ready;
                  await Promise.all(document.getAnimations().filter(a=>
                    a.effect.getComputedTiming().endTime!==Infinity).map(a=>a.finished.catch(()=>{})));
                  await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
                })()""")
                facts = evaluate("""(() => {const p=document.querySelector('.payment-card');
                  const b=p.querySelector('button'); const s=getComputedStyle(b); return {
                  testWarning:p.textContent.includes('RAZORPAY TEST MODE'),
                  amount:p.textContent.includes('₹2,500.00'),
                  locked:p.textContent.includes('Handover locked'),
                  noOverflow:p.scrollWidth<=p.clientWidth+1,
                  foreground:s.color, background:s.backgroundColor,
                  minimumTouch:[...p.querySelectorAll('button')].every(x=>x.getBoundingClientRect().height>=44),
                  accessible:!!p.getAttribute('aria-label')};})()""")
                save(OUTPUT / f"browser-{label}-observations.json", facts)
                require(
                    all(
                        facts[k]
                        for k in (
                            "testWarning",
                            "amount",
                            "locked",
                            "noOverflow",
                            "minimumTouch",
                            "accessible",
                        )
                    ),
                    "Payment UI layout or semantics failed: " + label,
                )
                require(
                    facts["foreground"] == "rgb(255, 255, 255)"
                    and facts["background"] == "rgb(48, 68, 197)",
                    "Payment button contrast styling failed",
                )
                checks[label] = facts
                evaluate("document.querySelector('.payment-card').scrollIntoView()")
                shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
                (OUTPUT / f"checkout-{label}.png").write_bytes(base64.b64decode(shot))
            # Render the real RefundPanel with labelled synthetic props. onAction
            # records only local values; no HTTP mutation function is provided.
            cdp("Page.navigate", {"url": ui + "/login"})
            wait_for("document.readyState === 'complete'")
            evaluate("""(async () => {
              const panelText=await (await fetch('/src/components/RefundPanel.jsx')).text();
              const mainText=await (await fetch('/src/main.jsx')).text();
              const reactUrl=panelText.match(/from ["']([^"']*deps\\/react\\.js[^"']*)/)[1];
              const domUrl=mainText.match(/from ["']([^"']*deps\\/react-dom_client\\.js[^"']*)/)[1];
              const React=(await import(reactUrl)).default;
              const dom=await import(domUrl); const createRoot=dom.default?.createRoot || dom.createRoot;
              const Panel=(await import('/src/components/RefundPanel.jsx')).default;
              document.querySelector('#root').style.display='none';
              const target=document.createElement('main'); target.className='payment-card';
              document.body.append(target); const root=createRoot(target);
              window.uiActions=[];
              window.renderRefund=(status='created')=>root.render(React.createElement('div',null,
                React.createElement('h2',null,'SYNTHETIC UI STATE — NO PROVIDER REQUEST'),
                React.createElement(Panel,{booking:{provider:'razorpay_test',rental_fee_paise:50000,
                  refund:{id:'synthetic',status,amount_paise:140000,deduction_paise:60000,kind:'dispute'}},
                  allowed:true,user:{id:'synthetic-borrower'},busy:false,
                  onAction:(path,body)=>window.uiActions.push({path,body})})));
              window.renderRefund();
            })()""")
            wait_for("document.querySelector('.refund-approval input') !== null")
            require(
                evaluate(
                    "[...document.querySelectorAll('button')].find(b=>b.textContent==='Send approved Test refund').disabled"
                ),
                "Refund dispatch was not disabled before approval",
            )
            evaluate("document.querySelector('.refund-approval input').click()")
            wait_for(
                "[...document.querySelectorAll('button')].some(b=>b.textContent==='Send approved Test refund'&&!b.disabled)"
            )
            evaluate(
                "[...document.querySelectorAll('button')].find(b=>b.textContent==='Send approved Test refund').click()"
            )
            actions = evaluate("window.uiActions")
            require(
                actions
                == [
                    {"path": "/payments/refunds/execute", "body": {"gateway_refund_approved": True}}
                ],
                "Refund UI authorization contract failed",
            )
            checks["synthetic_refund_explicit_approval_interaction"] = True
            for status in ("pending", "failed", "processed", "unknown"):
                evaluate("window.renderRefund(" + json.dumps(status) + ")")
                time.sleep(0.1)
                require(
                    evaluate(
                        "document.querySelector('.refund-panel').textContent.includes('₹1,400.00')"
                    ),
                    "Refund amount missing",
                )
                if status == "processed":
                    require(
                        evaluate("document.querySelector('.refund-panel button') === null"),
                        "Processed refund permits repeat dispatch",
                    )
            checks["synthetic_refund_pending_failed_processed_unknown_rendering"] = True
            shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
            (OUTPUT / "refund-synthetic-mobile.png").write_bytes(base64.b64decode(shot))
            cdp("Browser.close")
    finally:
        if connection:
            connection.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    require(before == fingerprints(database), "Browser check changed database rows")
    checks["all_rows_and_credentials_preserved"] = True
    report = {
        "checks": checks,
        "genuine_checkout_completed": False,
        "gateway_refund_posts": 0,
        "refund_ui_evidence": "Explicitly synthetic props with an in-memory action callback",
    }
    save(OUTPUT / "browser-verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "Browser verification stopped: "
            + (str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        )
        raise SystemExit(1) from None
