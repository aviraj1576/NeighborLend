"""Real browser checks with synthetic APIs; all hosted API/provider URLs blocked."""
import base64
import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "frontend"
OUTPUT = ROOT / ".payment-verification/frontend-integration-20261112"


def main():
    import httpx
    import websocket

    OUTPUT.mkdir(parents=True, exist_ok=True)
    baseline = OUTPUT / "upstream/frontend"
    junction = baseline / "node_modules"
    if not junction.exists():
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(FRONTEND / "node_modules")],
                       check=True, capture_output=True)
    # The baseline's dependency junction must not share Vite's optimization cache
    # with the real frontend or the developer's existing Vite process.
    original_config = subprocess.run(
        ["git", "show", "upstream/main:frontend/vite.config.js"], cwd=ROOT.parent,
        capture_output=True, check=True, text=True,
    ).stdout
    (baseline / "vite.config.js").write_text(original_config.replace(
        "export default defineConfig({", "export default defineConfig({\n  cacheDir: "
        + json.dumps(str(OUTPUT / "cache-baseline")) + ","
    ), encoding="utf-8")
    processes, logs = [], []
    connection = None
    checks = {}
    try:
        for folder, port in ((FRONTEND, 5187), (baseline, 5188)):
            log = (OUTPUT / f"vite-{port}.log").open("wb")
            logs.append(log)
            processes.append(subprocess.Popen([
                shutil.which("node"), str(FRONTEND / "node_modules/vite/bin/vite.js"),
                str(folder), "--host", "127.0.0.1", "--port", str(port), "--strictPort",
            ], cwd=folder, stdout=log, stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        profile = OUTPUT / ("browser-" + uuid4().hex)
        chrome = subprocess.Popen([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
            "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(chrome)
        with httpx.Client(timeout=1, trust_env=False) as client:
            for port in (5187, 5188):
                for _ in range(100):
                    try:
                        if client.get(f"http://127.0.0.1:{port}/login").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
        if any(process.poll() is not None for process in processes[:2]):
            raise RuntimeError("Test Vite server failed to start; refusing to use another server")
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            time.sleep(.1)
        port = int(active.read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{port}/json/list").json()[0]
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        sequence = 0
        browser_errors = []

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    details = message["params"]["exceptionDetails"]
                    browser_errors.append(details.get("exception", {}).get("description", details.get("text")))
                if message.get("method") == "Log.entryAdded":
                    entry = message["params"]["entry"]
                    if entry.get("level") == "error":
                        browser_errors.append(entry.get("text"))
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(expression):
            result = cdp("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise AssertionError(str(result["exceptionDetails"]))
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(300):
                if evaluate(expression):
                    return
                time.sleep(.1)
            raise AssertionError("UI did not reach: " + expression + "; browser errors: " + str(browser_errors[-3:])
                                 + "; page: " + str(evaluate("location.href+' '+document.body.textContent.slice(0,500)")))

        def click(label):
            evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===" + json.dumps(label) + ").click()")

        cdp("Page.enable")
        cdp("Runtime.enable")
        cdp("Log.enable")
        cdp("Network.enable")
        # Block API endpoints, not /src/api/client.js (a frontend source module).
        cdp("Network.setBlockedURLs", {"urls": ["http://127.0.0.1:5187/api/*", "http://127.0.0.1:5188/api/*",
                                                    "*127.0.0.1:8000*", "*localhost:8000*", "*/uploads/*", "https://*",
                                                    "*razorpay.com*", "*razorpay.in*", "*supabase*"]})
        cdp("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        styles = {}
        for name, port in (("upstream", 5188), ("integrated", 5187)):
            cdp("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
            cdp("Page.navigate", {"url": f"http://127.0.0.1:{port}/login"})
            wait("document.body.textContent.includes('Welcome back.')")
            evaluate("document.documentElement.style.scrollBehavior='auto'")
            styles[name] = evaluate("""(()=>{const input=document.querySelector('.login-form .input');
                const card=document.querySelector('.login-card'); const button=document.querySelector('.login-form .btn');
                return {body:getComputedStyle(document.body).backgroundColor,font:getComputedStyle(input).fontFamily,
                inputColor:getComputedStyle(input).color,inputRadius:getComputedStyle(input).borderRadius,
                card:getComputedStyle(card).backgroundColor,button:getComputedStyle(button).backgroundColor,
                navbar:getComputedStyle(document.querySelector('.navbar')).height};})()""")
            for width, size in ((1280, "desktop"), (390, "mobile")):
                cdp("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": width < 600})
                time.sleep(.3)
                shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
                (OUTPUT / f"{name}-login-{size}.png").write_bytes(base64.b64decode(shot))
                assert evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"), name + size
        assert styles["upstream"] == styles["integrated"], styles
        checks["upstream_login_typography_palette_forms_navbar_preserved"] = True
        checks["desktop_mobile_no_horizontal_overflow"] = True
        cdp("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        evaluate(r"""(async()=>{
          const pageText=await (await fetch('/src/pages/BorrowRequestDetail.jsx')).text();
          const mainText=await (await fetch('/src/main.jsx')).text();
          const reactUrl=pageText.match(/from ["']([^"']*deps\/react\.js[^"']*)/)[1];
          const routerUrl=pageText.match(/from ["']([^"']*deps\/react-router-dom\.js[^"']*)/)[1];
          const domUrl=mainText.match(/from ["']([^"']*deps\/react-dom_client\.js[^"']*)/)[1];
          const React=(await import(reactUrl)).default; const dom=await import(domUrl);
          const {MemoryRouter,Routes,Route}=await import(routerUrl);
          const {AuthProvider,useAuth}=await import('/src/context/AuthContext.jsx');
          const Rental=(await import('/src/pages/BorrowRequestDetail.jsx')).default;
          const Login=(await import('/src/pages/Login.jsx')).default;
          const CreateListing=(await import('/src/pages/CreateListing.jsx')).default;
          const ReviewQueue=(await import('/src/components/PaymentReviewQueue.jsx')).default;
          const api=(await import('/src/api/client.js')).default;
          window.sessionApi=api;
          document.querySelector('#root').style.display='none';
          const target=document.createElement('main');target.id='integration-harness';document.body.append(target);
          const root=(dom.default?.createRoot||dom.createRoot)(target);
          window.calls=[];window.user={id:'borrower',name:'Synthetic Borrower',is_admin:false};
          window.rental={id:'synthetic-request',borrower_id:'borrower',lender_id:'owner',lender_username:'priya_sharma',
            borrower_name:'Synthetic Borrower',listing_id:'listing',category:'Tools',title:'Synthetic integration rental',
            handover_status:'pending',status:'open',handover_photos:[],handover_confirmed_photos:[],return_photos:[],
            needed_from:'2026-11-12',needed_until:'2026-11-13',max_price_per_day:500};
          window.booking={id:'synthetic-booking',borrow_request_id:rental.id,borrower_id:'borrower',lender_id:'owner',
            provider:'razorpay_test',sandbox_only:true,test_mode:true,operations_enabled:true,
            rental_fee_paise:50000,security_deposit_paise:340000,total_amount_paise:390000,
            held_deposit_paise:340000,deposit_refunded_paise:0,deduction_paise:0,
            payment_status:'captured',booking_status:'funded',handover_unlocked:true,rating_eligible:false,
            transactions:[],journal:[],audit:[],refund:null,dispute:null};
          const png=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII='),c=>c.charCodeAt(0));
          api.get=async(path)=>{
            if(path==='/auth/me')return {data:{...window.user}};
            if(path==='/disputes'){
              if(window.queueUnavailable)throw {response:{status:503,data:{detail:'Synthetic queue unavailable'}}};
              return {data:[{booking_id:booking.id,borrow_request_id:rental.id,refund:{...booking.refund}}]};
            }
            if(path.includes('/payments/evidence/'))return {data:new Blob([png],{type:'image/png'})};
            if(path.startsWith('/payments/by-request/')){
              if(window.paymentUnavailable)throw {response:{status:503,data:{detail:'Synthetic payment service unavailable'}}};
              return {data:{...booking}};
            }
            if(path.startsWith('/payments/requests/')||path.startsWith('/borrow-requests/'))return {data:{...rental}};
            if(path==='/listings/detect-location')return {data:{latitude:12,longitude:77}};
            return {data:[]};
          };
          api.post=async(path,body)=>{
            calls.push({path,body:body instanceof FormData?'FormData':body});
            if(path==='/auth/login')return {data:{access_token:'synthetic-only',user:{...window.user}}};
            if(path==='/upload')return {data:{url:'/uploads/synthetic.png',ai_label:'Drill',ai_confidence:.98}};
            if(path.includes('/evidence?stage='))return {data:{url:'/api/payments/evidence/'+crypto.randomUUID()}};
            if(path.endsWith('/handover/upload-photos')){rental.handover_status='photos_uploaded';rental.handover_photos=body.photo_urls;}
            else if(path.endsWith('/handover/borrower-confirm'))rental.handover_status='borrower_confirmed';
            else if(path.endsWith('/handover/lender-confirm')){rental.handover_status='lender_confirmed';booking.booking_status='active';}
            else if(path.endsWith('/return/upload-photos')){rental.handover_status='return_photos_uploaded';rental.return_photos=body.photo_urls;}
            else if(path.endsWith('/return/confirm')){rental.handover_status='return_confirmed';booking.refund={status:'created'};}
            else if(path==='/payments/refunds/execute'){
              if(body.gateway_refund_approved!==true||body.booking_id!==booking.id)throw Error('Missing refund approval');
              booking.refund.status='pending';
            }
            else throw Error('Unexpected synthetic operation');
            return {data:{...rental}};
          };
          window.confirm=()=>true;let generation=0;
          window.showRental=(id,admin=false)=>{window.user={id,name:'Synthetic '+id,is_admin:admin};localStorage.setItem('nl_token','synthetic-only');
            root.render(React.createElement(AuthProvider,{key:++generation},React.createElement(MemoryRouter,
              {initialEntries:['/borrow-requests/synthetic-request']},React.createElement(Routes,null,
              React.createElement(Route,{path:'/borrow-requests/:id',element:React.createElement(Rental)})))));};
          window.upload=(selector)=>{const input=document.querySelector(selector),transfer=new DataTransfer();
            transfer.items.add(new File([png],'synthetic.png',{type:'image/png'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));};
          window.showCreate=()=>{root.render(React.createElement(AuthProvider,{key:++generation},React.createElement(MemoryRouter,null,React.createElement(CreateListing))));};
          window.showLogin=()=>{localStorage.removeItem('nl_token');root.render(
            React.createElement(MemoryRouter,{initialEntries:['/login']},React.createElement(AuthProvider,{key:++generation},React.createElement(Routes,null,
              React.createElement(Route,{path:'/login',element:React.createElement(Login)}),
              React.createElement(Route,{path:'/browse',element:React.createElement('h1',null,'Synthetic login succeeded')})))));};
          const Probe=()=>{window.auth=useAuth();const [draft,setDraft]=React.useState('empty');
            window.setAccountDraft=setDraft;return React.createElement('p',{id:'auth-probe'},
              (auth.loading?'loading':auth.user?.id||'anonymous')+':'+draft);};
          window.showAuth=()=>{window.user={id:'owner',name:'Synthetic Owner',is_admin:false};
            localStorage.setItem('nl_token','session-one');root.render(React.createElement(AuthProvider,
              {key:++generation},React.createElement(Probe)));};
          window.showQueue=()=>{window.user={id:'admin',name:'Synthetic Admin',is_admin:true};
            localStorage.setItem('nl_token','synthetic-only');root.render(React.createElement(AuthProvider,{key:++generation},
              React.createElement(MemoryRouter,{initialEntries:['/payment-review']},React.createElement(Routes,null,
                React.createElement(Route,{path:'/payment-review',element:React.createElement(ReviewQueue)}),
                React.createElement(Route,{path:'/borrow-requests/:id',element:React.createElement(Rental)})))));};
          window.showRental('borrower');
        })()""")
        wait("document.body.textContent.includes('Waiting for priya_sharma to upload')")
        assert not evaluate("!!document.querySelector('#handover-photos')")
        checks["borrower_waits_for_actual_listing_owner"] = True
        evaluate("window.showRental('owner',true)")
        wait("!!document.querySelector('#handover-photos')")
        evaluate("window.upload('#handover-photos')")
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Upload 1 photo')&&!b.disabled)")
        click("Upload 1 photo(s)")
        wait("document.body.textContent.includes('Waiting for the borrower to review')")
        assert evaluate("calls.some(c=>c.path.endsWith('/evidence?stage=handover'))&&!calls.some(c=>c.path==='/upload')")
        checks["admin_listing_owner_uploads_private_evidence"] = True
        evaluate("window.showRental('borrower')")
        wait("document.body.textContent.includes('I received this item')")
        assert not evaluate("!!document.querySelector('#confirm-photos')")
        assert not evaluate("document.querySelector('.handover-step input[type=file]') !== null")
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='I received this item'&&!b.disabled)")
        click("I received this item")
        wait("document.body.textContent.includes('Waiting for priya_sharma to confirm')")
        assert evaluate("calls.some(c=>c.path.endsWith('/handover/borrower-confirm')&&Array.isArray(c.body.photo_urls)&&c.body.photo_urls.length===0)")
        assert not evaluate("calls.some(c=>c.path.includes('/evidence?stage=receipt'))")
        checks["receipt_confirmation_without_upload_preserves_lender_confirmation"] = True
        evaluate("window.showRental('owner',true)")
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='Confirm handover complete')")
        click("Confirm handover complete")
        wait("document.body.textContent.includes('Borrowing is active.')")
        checks["both_confirmation_handlers_and_activation_connected"] = True
        evaluate("window.showRental('borrower')")
        wait("!!document.querySelector('#return-photos')")
        assert evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Upload 0 return')).disabled")
        evaluate("window.upload('#return-photos')")
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Upload 1 return')&&!b.disabled)")
        click("Upload 1 return photo(s)")
        wait("window.rental.handover_status==='return_photos_uploaded'")
        evaluate("window.showRental('owner',true)")
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='Confirm return — item OK')")
        click("Confirm return — item OK")
        wait("window.rental.handover_status==='return_confirmed'")
        checks["private_return_upload_and_confirmation_connected"] = True
        evaluate("window.showRental('borrower')")
        wait("document.body.textContent.includes('Return confirmed')")
        assert not evaluate("document.body.textContent.includes('Rate the lender')")
        evaluate("window.booking.rating_eligible=true;window.booking.booking_status='completed';window.showRental('borrower')")
        wait("document.body.textContent.includes('Rate the lender')")
        checks["ratings_require_server_settlement_eligibility"] = True
        evaluate("window.rental.handover_status='pending';window.booking.handover_unlocked=false;window.booking.payment_status='authorized';window.showRental('owner',true)")
        wait("document.body.textContent.includes('Handover stays locked')")
        assert not evaluate("!!document.querySelector('#handover-photos')")
        checks["unverified_payment_never_exposes_handover_upload"] = True
        evaluate("window.booking.handover_unlocked=true;window.booking.payment_status='captured';window.paymentUnavailable=true;window.showRental('owner',true)")
        wait("document.body.textContent.includes('Synthetic payment service unavailable')")
        assert not evaluate("!!document.querySelector('#handover-photos')")
        evaluate("window.paymentUnavailable=false")
        click("Refresh payment status")
        wait("!!document.querySelector('#handover-photos')")
        checks["payment_read_failure_locks_and_explicit_refresh_recovers"] = True
        evaluate("window.showRental('other')")
        wait("document.body.textContent.includes('Only this rental')")
        assert not evaluate("!!document.querySelector('#handover-photos')")
        checks["other_account_does_not_gain_lender_controls"] = True
        evaluate("window.showCreate()")
        wait("!!document.querySelector('input[type=file]')")
        evaluate("window.upload('input[type=file]')")
        wait("window.calls.some(c=>c.path==='/upload')")
        wait("document.body.textContent.includes('Drill')")
        checks["listing_wizard_upload_reuses_existing_ai_response"] = True
        evaluate("window.showLogin()")
        wait("!!document.querySelector('#integration-harness #identifier')")
        evaluate("""(()=>{for(const [selector,value] of [['#identifier','synthetic-user'],['#password','synthetic-password']]){
          const element=document.querySelector('#integration-harness '+selector);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(element,value);
          element.dispatchEvent(new Event('input',{bubbles:true}));}})()""")
        evaluate("document.querySelector('#integration-harness .login-form').requestSubmit()")
        wait("document.body.textContent.includes('Synthetic login succeeded')")
        checks["new_login_form_uses_existing_auth_and_navigates"] = True
        evaluate("window.rental.handover_status='return_confirmed';window.booking.booking_status='settling';window.booking.deposit_state='refund_pending';window.booking.refund={id:'synthetic-refund',kind:'clean_return',status:'created',amount_paise:340000,deduction_paise:0};window.showQueue()")
        wait("document.querySelector('#integration-harness').textContent.includes('Refund authorized — awaiting dispatch approval')")
        assert not evaluate("document.querySelector('#integration-harness').textContent.includes('No unresolved cases')")
        evaluate("[...document.querySelectorAll('#integration-harness a')].find(a=>a.textContent.includes('awaiting dispatch approval')).click()")
        wait("document.querySelector('#integration-harness .refund-approval input')!==null")
        assert evaluate("[...document.querySelectorAll('#integration-harness button')].find(b=>b.textContent==='Send approved Test refund').disabled")
        evaluate("document.querySelector('#integration-harness .refund-approval input').click()")
        wait("[...document.querySelectorAll('#integration-harness button')].some(b=>b.textContent==='Send approved Test refund'&&!b.disabled)")
        click("Send approved Test refund")
        wait("document.querySelector('#integration-harness .refund-panel').textContent.includes('Pending provider confirmation')")
        assert evaluate("window.calls.filter(c=>c.path==='/payments/refunds/execute').length===1")
        checks["admin_queue_to_security_deposit_approval_and_synthetic_dispatch"] = True
        evaluate("window.queueUnavailable=true;window.showQueue()")
        wait("document.querySelector('#integration-harness').textContent.includes('Synthetic queue unavailable')")
        assert not evaluate("document.querySelector('#integration-harness').textContent.includes('No unresolved cases')")
        evaluate("window.queueUnavailable=false")
        checks["queue_failure_never_reports_no_unresolved_cases"] = True
        evaluate("window.showAuth()")
        wait("document.querySelector('#auth-probe')?.textContent==='owner:empty'")
        evaluate("window.setAccountDraft('private-owner-draft')")
        wait("document.querySelector('#auth-probe').textContent.includes('private-owner-draft')")
        evaluate("window.user={id:'borrower',name:'Synthetic Borrower'};window.auth.login('synthetic','synthetic')")
        wait("document.querySelector('#auth-probe').textContent==='borrower:empty'")
        checks["account_change_discards_previous_private_component_state"] = True
        assert evaluate(r"""(async()=>{
          localStorage.setItem('nl_token','session-old');
          const pending=sessionApi.request({url:'/synthetic-only',adapter:config=>new Promise((resolve,reject)=>{
            window.finishOld=()=>reject({config,response:{status:401}});
          })}).then(()=>false,()=>true);
          await new Promise(resolve=>setTimeout(resolve,0));
          localStorage.setItem('nl_token','session-new');finishOld();await pending;
          return localStorage.getItem('nl_token')==='session-new'&&auth.user.id==='borrower';
        })()""")
        checks["previous_session_401_cannot_clear_new_login"] = True
        assert evaluate(r"""(async()=>{
          const pending=sessionApi.request({url:'/synthetic-only',adapter:config=>new Promise(resolve=>{
            window.finishOld=()=>resolve({config,data:{id:'old-account'},status:200,headers:{}});
          })}).then(()=>false,()=>true);
          await new Promise(resolve=>setTimeout(resolve,0));
          localStorage.setItem('nl_token','session-latest');finishOld();return await pending;
        })()""")
        checks["previous_session_success_cannot_repopulate_private_data"] = True
        # The visible path is /login, so invalidation is checked without navigation.
        evaluate(r"""sessionApi.request({url:'/synthetic-only',adapter:config=>
          Promise.reject({config,response:{status:401}})}).catch(()=>{});""")
        wait("document.querySelector('#auth-probe').textContent==='anonymous:empty'")
        assert evaluate("localStorage.getItem('nl_token')===null")
        checks["current_session_401_clears_displayed_identity_on_public_page"] = True
        evaluate("window.showAuth()")
        wait("document.querySelector('#auth-probe').textContent==='owner:empty'")
        evaluate(r"""window.savedPost=sessionApi.post;sessionApi.post=()=>new Promise(resolve=>{
          window.finishLogin=()=>resolve({data:{access_token:'superseded',user:{id:'old-login'}}});
        });window.pendingLogin=auth.login('synthetic','synthetic').then(()=>false,()=>true);auth.logout();""")
        evaluate("window.finishLogin()")
        assert evaluate("window.pendingLogin")
        assert evaluate("localStorage.getItem('nl_token')===null")
        evaluate("sessionApi.post=window.savedPost")
        checks["logout_fences_inflight_login_completion"] = True
        assert evaluate("window.calls.every(c=>!['/payments/create-order','/payments/verify'].includes(c.path))")
        checks["no_provider_or_real_backend_requests"] = True
        (OUTPUT / "browser-checks.json").write_text(json.dumps({"checks": checks, "style_comparison": styles}, indent=2), encoding="utf-8")
        print(json.dumps(checks, indent=2))
        cdp("Browser.close")
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Chrome can retain child processes during headless shutdown.
                # Scope cleanup to the exact process tree launched by this run.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=10,
                    check=False,
                )
                process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
