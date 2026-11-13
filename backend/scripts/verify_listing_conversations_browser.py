"""Real React routing/state checks with synthetic APIs and all external APIs blocked."""

import base64
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "frontend"
OUTPUT = ROOT / ".payment-verification/listing-conversations/browser"


def main():
    import httpx
    import websocket

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        vite_port = probe.getsockname()[1]
    processes, connection = [], None
    log = (OUTPUT / "vite.log").open("wb")
    checks, errors = {}, []
    try:
        processes.append(subprocess.Popen([
            shutil.which("node"), str(FRONTEND / "node_modules/vite/bin/vite.js"),
            "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort",
        ], cwd=FRONTEND, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        profile = OUTPUT / ("chrome-" + uuid4().hex)
        processes.append(subprocess.Popen([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
            "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + str(profile), "--disable-background-networking",
            "--no-first-run", "--no-default-browser-check", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        with httpx.Client(timeout=1, trust_env=False) as client:
            for _ in range(150):
                try:
                    if client.get(f"http://127.0.0.1:{vite_port}/login").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Disposable Vite server did not start")
        assert processes[0].poll() is None, "Refusing to use another Vite server"
        for _ in range(150):
            if (profile / "DevToolsActivePort").exists():
                break
            time.sleep(.1)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with httpx.Client(timeout=10, trust_env=False) as client:
            page = client.get(f"http://127.0.0.1:{port}/json/list").json()[0]
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        sequence = 0

        def cdp(method, params=None):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    errors.append(message["params"]["exceptionDetails"].get("text"))
                if message.get("id") == sequence:
                    assert "error" not in message, method
                    return message.get("result", {})

        def evaluate(expression):
            result = cdp("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            assert "exceptionDetails" not in result, result
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(150):
                if evaluate(expression):
                    return
                time.sleep(.1)
            raise AssertionError("UI did not reach: " + expression + "; exceptions=" + str(errors))

        def click(label):
            evaluate("[...document.querySelectorAll('#chat-harness button')].find(b=>b.textContent.trim()==="
                     + json.dumps(label) + ").click()")

        cdp("Page.enable")
        cdp("Runtime.enable")
        cdp("Network.enable")
        cdp("Network.setBlockedURLs", {"urls": ["https://*", "*razorpay*", "*supabase*",
            "*127.0.0.1:8000*", "*localhost:8000*", f"http://127.0.0.1:{vite_port}/api/*", "*/uploads/*"]})
        cdp("Page.navigate", {"url": f"http://127.0.0.1:{vite_port}/login"})
        wait("document.body.textContent.includes('Welcome back.')")
        evaluate(r"""(async()=>{
          const source=await(await fetch('/src/pages/Chat.jsx')).text();
          const main=await(await fetch('/src/main.jsx')).text();
          const React=(await import(source.match(/from ["']([^"']*deps\/react\.js[^"']*)/)[1])).default;
          const dom=await import(main.match(/from ["']([^"']*deps\/react-dom_client\.js[^"']*)/)[1]);
          const {MemoryRouter,Routes,Route,useNavigate}=await import(source.match(/from ["']([^"']*deps\/react-router-dom\.js[^"']*)/)[1]);
          const {AuthProvider,useAuth}=await import('/src/context/AuthContext.jsx');
          const Chat=(await import('/src/pages/Chat.jsx')).default;
          const Listing=(await import('/src/pages/ListingDetail.jsx')).default;
          const api=(await import('/src/api/client.js')).default;
          const borrower={id:'aarav',name:'Aarav Mehta',username:'aarav_mehta'};
          const lender={id:'rohan',name:'Rohan Kapoor',username:'rohan_kapoor'};
          const now=new Date().toISOString();
          const camera={id:'camera',name:'Camera',title:'Camera',owner_id:'rohan',owner:lender,
            price_per_day:600,security_deposit:2000,description:'Synthetic camera',photos:[]};
          const ladder={...camera,id:'ladder',name:'Ladder',title:'Ladder',price_per_day:125,security_deposit:400};
          const message=(id,content)=>({id,conversation_id:id,sender_id:'aarav',content,created_at:now});
          const cameraOffer={id:'camera-offer',conversation_id:'camera-chat',listing_id:'camera',
            sender_id:'aarav',sender_name:'Aarav Mehta',daily_price:500,total_cost:500,
            security_deposit_paise:200000,total_amount_paise:250000,start_date:now,end_date:now,
            status:'accepted',borrow_request_id:'camera-rental',created_at:now,updated_at:now};
          const common={borrower,lender,other_participant:lender,is_borrower:true,created_at:now,updated_at:now};
          window.chats={
            'camera-chat':{...common,id:'camera-chat',listing_id:'camera',listing:camera,
              messages:[message('camera-message','Camera agreement message')],offers:[cameraOffer],active_offer:cameraOffer},
            'ladder-chat':{...common,id:'ladder-chat',listing_id:'ladder',listing:ladder,
              messages:[message('ladder-message','Ladder question')],offers:[],active_offer:null}};
          window.calls=[];
          api.get=async(path)=>{
            calls.push({method:'get',path});
            if(path==='/auth/me')return {data:borrower};
            if(path==='/listings/ladder')return {data:ladder};
            if(path==='/conversations')return {data:Object.values(chats)};
            if(path.startsWith('/conversations/')){
              const id=path.split('/')[2];
              if(!chats[id])throw {response:{status:403}};
              const data=structuredClone(chats[id]);
              if(id==='camera-chat'&&window.holdCamera)await new Promise(resolve=>window.releaseCamera=resolve);
              return {data};
            }
            if(path.startsWith('/listings/search'))throw Error('Bound chat must use its listing, not broad search');
            return {data:[]};
          };
          api.post=async(path,body)=>{
            calls.push({method:'post',path,body});
            if(path==='/conversations'){
              if(body.listing_id!=='ladder'||body.lender_id!=='rohan')throw Error('Lost listing context');
              return {data:structuredClone(chats['ladder-chat'])};
            }
            if(path==='/conversations/ladder-chat/offers'){
              if(body.listing_id!=='ladder')throw Error('Wrong offer listing');
              if(window.holdOffer)await new Promise(resolve=>window.releaseOffer=resolve);
              const offer={...cameraOffer,...body,id:'ladder-offer',conversation_id:'ladder-chat',status:'pending',
                security_deposit_paise:40000,total_amount_paise:65000,total_cost:250,borrow_request_id:null};
              chats['ladder-chat'].offers=[offer];chats['ladder-chat'].active_offer=offer;
              return {data:offer};
            }
            throw Error('Unexpected synthetic POST: '+path);
          };
          document.querySelector('#root').style.display='none';
          const target=document.createElement('main');target.id='chat-harness';document.body.append(target);
          const root=(dom.default?.createRoot||dom.createRoot)(target);
          const Bridge=()=>{window.go=useNavigate();window.auth=useAuth();return null;};
          localStorage.setItem('nl_token','synthetic-browser-only');
          root.render(React.createElement(AuthProvider,null,React.createElement(MemoryRouter,
            {initialEntries:['/listings/ladder']},React.createElement(Bridge),React.createElement(Routes,null,
              React.createElement(Route,{path:'/listings/:id',element:React.createElement(Listing)}),
              React.createElement(Route,{path:'/messages/:conversationId',element:React.createElement(Chat)})))));
          window.setField=(selector,value)=>{const el=document.querySelector(selector);
            Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);
            el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));};
        })()""")
        wait("window.auth?.user?.id==='aarav' && !!document.querySelector('#chat-harness .listing-detail-page')")
        click("Chat with owner")
        wait("document.querySelector('.chat-listing-pricing')?.textContent==='Ladder'")
        assert evaluate("calls.some(c=>c.path==='/conversations'&&c.body?.listing_id==='ladder')")
        assert not evaluate("document.querySelector('#chat-harness').textContent.includes('Agreement confirmed!')")
        checks["listing_button_passes_owner_and_listing"] = True
        click("Make an offer")
        wait("document.querySelector('#offer-listing')?.value==='ladder'")
        assert evaluate("document.querySelector('#offer-listing').disabled && document.querySelector('#offer-daily-price').value==='125'")
        evaluate("setField('#offer-note','Ladder draft');window.go('/messages/camera-chat')")
        wait("document.querySelector('.accepted-banner')?.textContent.includes('Agreement confirmed!')")
        assert evaluate("document.querySelector('.offer-rate-large').textContent.includes('500')")
        assert not evaluate("document.querySelector('.offer-form-card') || document.querySelector('.messages-container').textContent.includes('Ladder question')")
        checks["switching_restores_camera_offer_and_clears_ladder_draft"] = True
        evaluate("window.go('/messages/ladder-chat')")
        wait("document.querySelector('.chat-listing-pricing')?.textContent==='Ladder'")
        click("Make an offer")
        wait("document.querySelector('#offer-note')?.value===''")
        assert evaluate("document.querySelector('#offer-daily-price').value==='125'")
        checks["reopen_ladder_restores_correct_listing_and_defaults"] = True
        evaluate("window.holdCamera=true;window.go('/messages/camera-chat')")
        wait("typeof window.releaseCamera==='function'")
        evaluate("window.go('/messages/ladder-chat')")
        wait("document.querySelector('.chat-listing-pricing')?.textContent==='Ladder'")
        evaluate("window.holdCamera=false;window.releaseCamera()")
        wait("document.querySelector('.messages-container')?.textContent.includes('Ladder question')")
        assert not evaluate("document.querySelector('#chat-harness').textContent.includes('Agreement confirmed!')")
        checks["late_camera_response_cannot_overwrite_ladder"] = True
        click("Make an offer")
        evaluate("window.holdOffer=true;document.querySelector('.offer-form-card').requestSubmit()")
        wait("typeof window.releaseOffer==='function'")
        evaluate("window.go('/messages/camera-chat')")
        wait("document.querySelector('.accepted-banner')?.textContent.includes('Agreement confirmed!')")
        evaluate("window.releaseOffer()")
        wait("window.chats['ladder-chat'].active_offer?.id==='ladder-offer'")
        assert evaluate("document.querySelector('.offer-rate-large').textContent.includes('500')")
        checks["late_ladder_submission_cannot_overwrite_camera"] = True
        evaluate("window.go('/messages/ladder-chat')")
        wait("document.querySelector('.offer-status-tag')?.textContent==='pending'")
        assert evaluate("document.querySelector('.offer-rate-large').textContent.includes('125')")
        for width in (1280, 390):
            cdp("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": width < 600})
            shot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
            (OUTPUT / f"ladder-{width}.png").write_bytes(base64.b64decode(shot))
        evaluate("window.go('/messages/unrelated-private-chat')")
        wait("document.querySelector('.messages-container')?.textContent.includes('lack access')")
        assert not evaluate("document.querySelector('.negotiation-panel')")
        checks["private_chat_error_clears_previous_terms"] = True
        assert not evaluate("calls.some(c=>c.path.startsWith('/listings/search'))")
        assert not errors, errors
        (OUTPUT / "results.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps({"passed": len(checks), "checks": checks, "artifacts": str(OUTPUT)}))
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()


if __name__ == "__main__":
    main()
