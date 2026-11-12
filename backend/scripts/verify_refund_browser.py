"""Headless refund interactions with synthetic APIs; hosted URLs are blocked."""

import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".payment-verification/refund-debug-20261112"


def main():
    import httpx
    import websocket

    OUTPUT.mkdir(parents=True, exist_ok=True)
    processes, connection = [], None
    log = (OUTPUT / "vite.log").open("wb")
    try:
        processes.append(subprocess.Popen([
            shutil.which("node"), str(ROOT.parent / "frontend/node_modules/vite/bin/vite.js"),
            "--host", "127.0.0.1", "--port", "5187", "--strictPort",
        ], cwd=ROOT.parent / "frontend", stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        profile = OUTPUT / ("browser-" + uuid4().hex)
        processes.append(subprocess.Popen([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
            "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        with httpx.Client(timeout=1, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get("http://127.0.0.1:5187/login").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(.1)
        port = int(active.read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{port}/json/list").json()[0]
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)
        sequence, browser_errors = 0, []

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    browser_errors.append(message["params"]["exceptionDetails"].get("text"))
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(expression):
            result = cdp("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            assert "exceptionDetails" not in result, str(result.get("exceptionDetails"))
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(100):
                if evaluate(expression):
                    return
                time.sleep(.1)
            raise AssertionError("UI did not reach " + expression)

        def click(label):
            evaluate("[...document.querySelectorAll('#refund-harness button')].find(b=>b.textContent===" + json.dumps(label) + ").click()")

        cdp("Page.enable")
        cdp("Runtime.enable")
        cdp("Network.enable")
        cdp("Network.setBlockedURLs", {"urls": ["https://*", "*razorpay.com*", "*razorpay.in*", "*supabase*",
                                                    "http://127.0.0.1:5187/api/*", "*127.0.0.1:8000*", "*localhost:8000*"]})
        cdp("Page.navigate", {"url": "http://127.0.0.1:5187/login"})
        wait("document.readyState==='complete'")
        evaluate(r"""(async()=>{
          const text=await (await fetch('/src/components/PaymentModal.jsx')).text();
          const main=await (await fetch('/src/main.jsx')).text();
          const React=(await import(text.match(/from ["']([^"']*deps\/react\.js[^"']*)/)[1])).default;
          const dom=await import(main.match(/from ["']([^"']*deps\/react-dom_client\.js[^"']*)/)[1]);
          const Card=(await import('/src/components/EscrowStatusCard.jsx')).default;
          document.querySelector('#root').style.display='none';
          const target=document.createElement('main'); target.id='refund-harness'; document.body.append(target);
          const root=(dom.default?.createRoot||dom.createRoot)(target);
          window.posts=[]; window.reads=[]; window.rentalRefreshes=0; let version=0;
          const request={id:'synthetic-request',borrower_id:'borrower',lender_id:'lender',status:'fulfilled',handover_status:'return_confirmed'};
          const base={id:'synthetic-booking',provider:'razorpay_test',sandbox_only:true,test_mode:true,
            operations_enabled:true,borrower_id:'borrower',lender_id:'lender',payment_status:'captured',
            booking_status:'settling',deposit_state:'refund_pending',settlement_kind:'clean_return',
            handover_unlocked:true,rental_fee_paise:50000,security_deposit_paise:340000,total_amount_paise:390000,
            held_deposit_paise:340000,deposit_refunded_paise:0,deduction_paise:0,
            refund:{id:'synthetic-intent',kind:'clean_return',status:'created',amount_paise:340000,deduction_paise:0}};
          const api={get:async(path)=>{window.reads.push(path);
            if(path.endsWith('/receipt')||path.endsWith('/refund-acknowledgment'))
              return {data:new Blob(['<!doctype html><title>SYNTHETIC REFUND TEST</title>'])};
            return {data:structuredClone(window.savedBooking)};},
            post:async(path,body)=>{window.posts.push({path,body});
              if(path==='/payments/refunds/execute' && body.gateway_refund_approved!==true) throw Error('Approval required');
              if(!['/payments/refunds/execute','/payments/refunds/reconcile'].includes(path)) throw Error('Unexpected financial POST');
              if(body.booking_id!=='synthetic-booking') throw Error('Wrong booking');
              window.savedBooking.refund.status=path.endsWith('/reconcile')?'processed':window.outcome;
              if(window.savedBooking.refund.status==='processed'){
                window.savedBooking.booking_status='completed';window.savedBooking.deposit_state='settled';
                window.savedBooking.deposit_refunded_paise=340000;window.savedBooking.held_deposit_paise=0;}
              if(window.loseResponse) throw Error('Synthetic response lost; read saved status');
              return {data:structuredClone(window.savedBooking)};}};
          const onStatus=()=>{};
          const onRentalChange=async()=>{window.rentalRefreshes++;};
          window.show=(role='admin',outcome='pending',lose=false,status='created')=>{
            window.posts=[];window.reads=[];window.rentalRefreshes=0;
            window.savedBooking=structuredClone(base);window.savedBooking.refund.status=status;
            window.outcome=outcome;window.loseResponse=lose;
            root.render(React.createElement(Card,{key:++version,request,user:{id:role,is_admin:role==='admin'},api,onStatus,onRentalChange}));};
          window.button=(label)=>[...document.querySelectorAll('#refund-harness button')].find(b=>b.textContent===label);
          window.show();
        })()""")
        checks = {}
        for role in ("admin",):
            evaluate("window.show(" + json.dumps(role) + ")")
            wait("!!window.button('Send approved Test refund')")
            assert evaluate("window.button('Send approved Test refund').disabled && window.button('Reconcile refund status (no new refund)').disabled")
            assert evaluate("document.querySelector('#refund-harness').textContent.includes('3,400.00') && !window.button('Download refund acknowledgment')")
            evaluate("document.querySelector('#refund-harness .refund-approval input').click()")
            wait("!window.button('Send approved Test refund').disabled")
            click("Send approved Test refund")
            wait("document.querySelector('#refund-harness .refund-panel').textContent.includes('Pending provider confirmation')")
            assert evaluate("window.posts.length===1 && window.posts[0].body.gateway_refund_approved===true && !window.button('Download refund acknowledgment') && window.rentalRefreshes===1")
            click("Reconcile refund status (no new refund)")
            wait("!!window.button('Download refund acknowledgment')")
            assert evaluate("window.posts.length===2 && window.posts[1].path==='/payments/refunds/reconcile' && window.rentalRefreshes===2")
            checks[role + "_approval_payload_pending_reconciliation_refresh"] = True
        downloads = OUTPUT / ("downloads-" + uuid4().hex)
        downloads.mkdir()
        cdp("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
        for label in ("Download payment receipt", "Download refund acknowledgment"):
            click(label)
            wait("[...document.querySelectorAll('#refund-harness button')].every(b=>!b.disabled)")
        for _ in range(100):
            if len(list(downloads.glob("*.html"))) == 2:
                break
            time.sleep(.1)
        assert len(list(downloads.glob("*.html"))) == 2
        assert all("SYNTHETIC REFUND TEST" in p.read_text() for p in downloads.glob("*.html"))
        checks["receipt_and_confirmed_refund_acknowledgment_download"] = True
        evaluate("window.show('admin','processed',true)")
        wait("!!window.button('Send approved Test refund')")
        evaluate("document.querySelector('#refund-harness .refund-approval input').click()")
        wait("!window.button('Send approved Test refund').disabled")
        click("Send approved Test refund")
        wait("!!window.button('Download refund acknowledgment')")
        assert evaluate("window.posts.length===1 && window.rentalRefreshes===1 && document.querySelector('#refund-harness [role=alert]').textContent.includes('Synthetic response lost')")
        checks["lost_response_reads_saved_outcome_without_repeat_dispatch"] = True
        evaluate("window.show('borrower','pending',false,'failed')")
        wait("document.querySelector('#refund-harness').textContent.includes('Only an administrator can send or reconcile')")
        assert evaluate("!window.button('Administrator: retry confirmed failed Test refund')")
        evaluate("window.show('admin','pending',false,'failed')")
        wait("!!window.button('Administrator: retry confirmed failed Test refund')")
        assert evaluate("window.button('Administrator: retry confirmed failed Test refund').disabled")
        evaluate("document.querySelector('#refund-harness .refund-approval input').click()")
        wait("!window.button('Administrator: retry confirmed failed Test refund').disabled")
        click("Administrator: retry confirmed failed Test refund")
        wait("window.posts.length===1")
        assert evaluate("window.posts[0].body.retry_failed===true && window.posts[0].body.gateway_refund_approved===true")
        checks["failed_refund_retry_requires_admin_and_new_consent"] = True
        evaluate("window.show('outsider')")
        wait("document.querySelector('#refund-harness .refund-panel')!==null")
        assert evaluate("!window.button('Send approved Test refund') && !window.button('Reconcile refund status (no new refund)') && window.posts.length===0")
        checks["outsider_has_no_refund_controls"] = True
        assert browser_errors == [], browser_errors
        checks["no_uncaught_browser_errors"] = True
        (OUTPUT / "browser-checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps(checks, indent=2))
        cdp("Browser.close")
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    main()
