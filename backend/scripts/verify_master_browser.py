"""Headless interactions using real React components and synthetic in-memory APIs.

Starts a disposable loopback Vite server on 5187. All API/provider URLs are
blocked. No application login or payment request is performed.
"""

import base64
import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".payment-verification/master-20261111"


def main():
    import httpx
    import websocket

    log = (OUTPUT / "browser-vite.log").open("wb")
    vite = subprocess.Popen(
        [
            shutil.which("node"),
            str(ROOT.parent / "frontend/node_modules/vite/bin/vite.js"),
            "--host",
            "127.0.0.1",
            "--port",
            "5187",
            "--strictPort",
        ],
        cwd=ROOT.parent / "frontend",
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    profile = OUTPUT / ("browser-" + uuid4().hex)
    process = subprocess.Popen(
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
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
    sequence = 0
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get("http://127.0.0.1:5187/login").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(0.1)
        port = int(active.read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{port}/json/list").json()[0]
        connection = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=20, suppress_origin=True
        )

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(expression):
            result = cdp(
                "Runtime.evaluate",
                {"expression": expression, "awaitPromise": True, "returnByValue": True},
            )
            assert "exceptionDetails" not in result, str(result.get("exceptionDetails"))
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(100):
                if evaluate(expression):
                    return
                time.sleep(0.1)
            raise AssertionError("UI did not reach expected state: " + expression)

        cdp("Page.enable")
        cdp("Network.enable")
        cdp("Network.setBlockedURLs", {"urls": ["*razorpay.com*", "*razorpay.in*", "https://*",
                                                   "http://127.0.0.1:5187/api/*", "*127.0.0.1:8000*", "*localhost:8000*"]})
        cdp("Page.navigate", {"url": "http://127.0.0.1:5187/login"})
        wait("document.readyState==='complete'")
        evaluate(r"""(async()=>{
          const panelText=await (await fetch('/src/components/PaymentModal.jsx')).text();
          const mainText=await (await fetch('/src/main.jsx')).text();
          const reactUrl=panelText.match(/from ["']([^"']*deps\/react\.js[^"']*)/)[1];
          const domUrl=mainText.match(/from ["']([^"']*deps\/react-dom_client\.js[^"']*)/)[1];
          const React=(await import(reactUrl)).default;
          const dom=await import(domUrl); const createRoot=dom.default?.createRoot||dom.createRoot;
          const Modal=(await import('/src/components/PaymentModal.jsx')).default;
          const Docs=(await import('/src/components/PaymentDocuments.jsx')).default;
          const Dispute=(await import('/src/components/DisputeResolutionModal.jsx')).default;
          document.querySelector('#root').style.display='none';
          const target=document.createElement('main'); target.className='payment-card'; document.body.append(target);
          const root=createRoot(target); window.calls=[];
          const booking={id:'synthetic-booking',provider:'mock',sandbox_only:true,test_mode:true,
            operations_enabled:true,borrower_id:'borrower',lender_id:'lender',
            rental_fee_paise:50000,security_deposit_paise:200000,total_amount_paise:250000};
          const api={post:async(path,body)=>{window.calls.push({path,body});return {data:{
            provider:'mock',sandbox_only:true,test_mode:true,booking_id:booking.id,key_id:null,
            order_id:'order_mock_synthetic',amount_paise:250000,currency:'INR'}}},
            get:async()=>({data:new Blob(['<!doctype html><title>SYNTHETIC TEST RECEIPT</title>'])})};
          window.show=(mode,version=1)=>root.render(React.createElement('section',null,
            React.createElement('h1',null,'SYNTHETIC UI VERIFICATION — NO PROVIDER REQUEST'),
            mode==='checkout'?React.createElement(Modal,{booking,api,onChange:async()=>{}}):
            mode==='docs'?React.createElement(Docs,{booking:{...booking,payment_status:'captured',refund:{status:'processed'}},api}):
            React.createElement(Dispute,{booking:{...booking,dispute:{id:'synthetic-claim',status:'raised',
              claim_version:version,claimed_deduction_paise:60000}},user:{id:'admin',is_admin:true},
              returnReady:true,request:{handover_status:'return_photos_uploaded'},api,onChange:async()=>{}})));
          window.show('checkout');
        })()""")
        wait("document.querySelector('.payment-checkout button')!==null")
        assert evaluate("document.querySelector('.payment-checkout button').disabled")
        evaluate("document.querySelector('.payment-checkout input[type=checkbox]').click()")
        wait("!document.querySelector('.payment-checkout button').disabled")
        evaluate("document.querySelector('.payment-checkout button').click()")
        wait("document.querySelector('.demo-checkout')!==null")
        assert evaluate("window.calls.length===1&&window.calls[0].body.accepted_terms===true")
        checks = {"terms_gate_and_explicit_consent": True}
        evaluate("window.show('dispute',1)")
        wait("document.body.textContent.includes('Record administrator settlement decision')")
        evaluate("window.show('dispute',2)")
        wait("document.body.textContent.includes('The claim changed.')")
        assert evaluate(
            "[...document.querySelectorAll('button')].find(b=>b.textContent==='Record administrator settlement decision').disabled"
        )
        evaluate(
            "[...document.querySelectorAll('button')].find(b=>b.textContent==='Review updated claim').click()"
        )
        wait("!document.body.textContent.includes('The claim changed.')")
        assert evaluate("document.querySelector('textarea').value===''")
        checks["revised_claim_requires_review_and_new_reason"] = True
        evaluate("""(()=>{const t=document.querySelector('textarea');
          Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'Independent synthetic review');
          t.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        wait(
            "[...document.querySelectorAll('button')].some(b=>b.textContent==='Reject damage claim (full deposit refund)'&&!b.disabled)"
        )
        evaluate(
            "[...document.querySelectorAll('button')].find(b=>b.textContent==='Reject damage claim (full deposit refund)').click()"
        )
        wait("window.calls.length===2")
        assert evaluate(
            "window.calls[1].path==='/disputes/settle'&&window.calls[1].body.approved_deduction_paise===0&&window.calls[1].body.claim_version===2"
        )
        checks["admin_rejection_uses_current_version_and_zero_deduction"] = True
        downloads = OUTPUT / ("downloads-" + uuid4().hex)
        downloads.mkdir()
        cdp("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
        evaluate("window.show('docs')")
        wait("document.body.textContent.includes('Download payment receipt')")
        for label in ("Download payment receipt", "Download refund acknowledgment"):
            evaluate(
                "[...document.querySelectorAll('button')].find(b=>b.textContent==="
                + json.dumps(label)
                + ").click()"
            )
            wait("[...document.querySelectorAll('button')].every(b=>!b.disabled)")
        for _ in range(100):
            if len(list(downloads.glob("*.html"))) == 2:
                break
            time.sleep(0.1)
        files = list(downloads.glob("*.html"))
        assert len(files) == 2 and all("SYNTHETIC TEST RECEIPT" in p.read_text() for p in files)
        checks["both_document_buttons_download_html"] = True
        for width, name in ((1280, "desktop"), (390, "mobile")):
            cdp(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": width < 600},
            )
            shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
            (OUTPUT / f"new-payment-ui-{name}.png").write_bytes(base64.b64decode(shot))
        (OUTPUT / "browser-checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps(checks))
        cdp("Browser.close")
    finally:
        if connection:
            connection.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        vite.terminate()
        vite.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    main()
