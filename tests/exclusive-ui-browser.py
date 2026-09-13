"""Production Svelte components with synthetic IPC: not OS-notification acceptance."""
from __future__ import annotations
import functools, http.server, json, os, pathlib, subprocess, threading, time
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(os.environ.get('EXCLUSIVE_UI_DIR', str(ROOT / '.exclusive-ui')))
EVIDENCE = pathlib.Path(os.environ.get('EXCLUSIVE_EVIDENCE_DIR', str(ROOT / '.exclusive-evidence')))
EVIDENCE.mkdir(parents=True, exist_ok=True)
subprocess.run(['node', 'scripts/exclusive-ui-harness.mjs'], cwd=ROOT, env={**os.environ, 'EXCLUSIVE_UI_DIR': str(OUT)}, check=True)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(OUT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
results = []
failure = None
try:
    with sync_playwright() as p:
        executable = os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium')
        browser = p.chromium.launch(executable_path=executable if pathlib.Path(executable).exists() else None, headless=True)
        page = browser.new_page(viewport={'width': 1160, 'height': 930})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def fresh():
            page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            page.wait_for_function('window.app && window.handlers.size === 3')
            page.bring_to_front()
        def candidate(i='A', workspace='one', lifetime=90):
            return {'workspaceId': workspace, 'workspaceName': 'Synthetic Research Workspace', 'exclusive': True,
                    'grant': {'id': i, 'fingerprint': '91bf83e7a21c1234', 'status': 'pending', 'scopes': ['files.read','exec.run'],
                              'created_at': time.time(), 'expires_at': time.time()+lifetime, 'idle_expires_at': time.time()+lifetime}}
        def publish(row):
            page.evaluate('(rows)=>window.publish(rows)', [row])
            page.wait_for_selector('dialog[open]')
        def done(name):
            assert not errors, errors
            results.append({'test': name, 'status': 'passed'})
        fresh(); publish(candidate())
        assert page.get_by_role('button', name='批准并独占', exact=True).is_disabled(), 'fingerprint must start unconfirmed'
        assert page.locator('dialog').inner_text().count('91bf83e7a21c1234') == 1
        page.evaluate("()=>{for(let i=0;i<100;i++)window.emit('chat-authorization-changed');}")
        page.wait_for_timeout(150); assert page.evaluate('window.modalOpens') == 1
        page.screenshot(path=str(EVIDENCE/'approval-modal.png'), full_page=True)
        page.get_by_role('button', name='定位工作区', exact=True).click()
        assert page.evaluate('window.navigation') == ['/workspace/one']
        page.locator('dialog input[value="exec.run"]').uncheck()
        page.locator('dialog .verify input').check()
        page.get_by_role('button', name='批准并独占', exact=True).click()
        page.wait_for_function("window.calls.some(c=>c.name==='chat_authorization_control')")
        call=page.evaluate("window.calls.find(c=>c.name==='chat_authorization_control')")
        assert call['args']['id']=='one' and call['args']['requestId']=='A' and call['args']['scopes']==['files.read'], call
        page.wait_for_function("!document.querySelector('dialog').open")
        done('one modal for 100 invalidations; explicit fingerprint and reduced scopes target correct workspace')

        fresh();publish(candidate('dismiss'))
        page.keyboard.press('Escape');page.evaluate("()=>window.emit('chat-authorization-changed')")
        page.wait_for_timeout(150)
        assert not page.locator('dialog').evaluate('(d)=>d.open')
        assert page.evaluate('window.modalOpens')==1
        assert not page.evaluate("window.calls.some(c=>c.name==='chat_authorization_control')")
        page.get_by_role('button', name='待审批聊天 · 1', exact=True).click()
        page.wait_for_selector('dialog[open]'); assert page.evaluate('window.modalOpens')==2
        done('Escape never approves; a dismissed candidate reopens only on explicit local action')

        fresh();publish(candidate('expires',lifetime=1))
        page.locator('dialog .verify input').check();page.wait_for_timeout(1300)
        assert page.get_by_role('button',name='批准并独占',exact=True).is_disabled()
        done('countdown expires without allowing a stale approval')

        fresh(); page.evaluate("()=>{window.realFocus=document.hasFocus;document.hasFocus=()=>false;}")
        page.evaluate('(rows)=>window.publish(rows)',[candidate('background')]);page.wait_for_timeout(200)
        assert not page.locator('dialog').evaluate('(d)=>d.open')
        page.evaluate("()=>window.emit('chat-authorization-open')");page.wait_for_selector('dialog[open]')
        done('background invalidation does not steal focus; trusted tray event opens inbox')

        fresh(); page.get_by_label('访问令牌有效期（分钟）',exact=True).fill('4')
        page.get_by_role('button',name='保存远程会话策略',exact=True).click()
        assert page.locator('.remote-session-settings [role=alert]').count()==1
        assert page.evaluate('window.saved.length')==0
        page.get_by_label('访问令牌有效期（分钟）',exact=True).fill('120')
        page.get_by_label('刷新会话有效期（天）',exact=True).fill('45')
        page.get_by_label('独占聊天授权有效期（小时）',exact=True).fill('168')
        page.get_by_role('button',name='保存远程会话策略',exact=True).click()
        page.wait_for_function('window.saved.length===1')
        saved=page.evaluate('window.saved[0]');assert saved['id']=='one'
        assert saved['value']['session_policy']=={'exclusive':True,'access_token_ttl_seconds':7200,'refresh_session_ttl_seconds':3888000,'chat_lease_ttl_seconds':604800,'chat_idle_timeout_seconds':0},saved
        page.screenshot(path=str(EVIDENCE/'session-settings.png'),full_page=True)
        done('settings reject invalid bounds and convert user-selected units to backend seconds')

        fresh();page.evaluate('()=>{window.mockConfirm=()=>new Promise(r=>window.releaseConfirm=r);}')
        page.get_by_role('button',name='保存远程会话策略',exact=True).click();page.wait_for_function('window.releaseConfirm')
        page.evaluate("()=>window.setWorkspace('two')");page.wait_for_timeout(50)
        page.evaluate('()=>window.releaseConfirm(true)');page.wait_for_timeout(100)
        assert page.evaluate('window.saved.length')==0
        done('switching workspace during confirmation cannot save stale policy')

        fresh(); page.evaluate("()=>{window.mockSave=(id,value)=>{window.saved.push({id,value});return new Promise(r=>window.releaseSave=r);};}")
        page.get_by_role('button',name='保存远程会话策略',exact=True).click();page.wait_for_function('window.releaseSave')
        page.evaluate("()=>window.setWorkspace('two')");page.wait_for_timeout(50)
        page.evaluate("()=>window.setWorkspace('one')");page.wait_for_timeout(50)
        page.evaluate('()=>window.releaseSave()');page.wait_for_timeout(100)
        assert not page.locator('.remote-session-settings').inner_text().count('策略已保存')
        done('A-to-B-to-A navigation discards stale save completion')

        fresh();publish(candidate('old','two'));page.evaluate('(rows)=>window.publish(rows)',[candidate('replacement','one')])
        page.wait_for_function("document.querySelector('dialog').textContent.includes('91bf') && window.modalOpens>=2")
        page.locator('dialog .verify input').check();page.get_by_role('button',name='拒绝',exact=True).click()
        page.wait_for_function("window.calls.some(c=>c.name==='chat_authorization_control')")
        last=page.evaluate("window.calls.filter(c=>c.name==='chat_authorization_control').at(-1).args")
        assert last['id']=='one' and last['requestId']=='replacement' and last['action']=='deny',last
        done('authoritative replacement dismisses obsolete candidate and never approves an old request')

        fresh();publish(candidate('ipc-error'))
        page.evaluate("()=>{const original=window.mockInvoke;window.mockInvoke=(name,args)=>{if(name==='chat_authorization_control')throw Error('synthetic IPC rejection');return original(name,args);};}")
        page.locator('dialog .verify input').check();page.get_by_role('button',name='批准并独占',exact=True).click()
        page.wait_for_selector('dialog [role=alert]')
        assert page.locator('dialog').evaluate('(d)=>d.open')
        assert page.locator('dialog [role=alert]').inner_text()=='Error: synthetic IPC rejection'
        done('failed local IPC is not reported as approved')

        fresh(); page.evaluate('()=>window.dispose()');page.wait_for_timeout(100)
        assert page.evaluate('[...window.handlers.values()].every(s=>s.size===0)')
        before=page.evaluate('window.calls.length');page.evaluate("()=>window.emit('chat-authorization-changed')");page.wait_for_timeout(100)
        assert page.evaluate('window.calls.length')==before
        done('WebView unmount removes listeners and pending component side effects')
        browser.close()
except Exception as exc:
    failure = str(exc)
    raise
finally:
    server.shutdown()
    (EVIDENCE/'browser-results.json').write_text(json.dumps({'tests':results,'passed':len(results),'transport':'synthetic IPC; real production Svelte components','native_notifications_verified':False,'failure':failure,'status':'failed' if failure else 'passed'},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(results),'evidence':str(EVIDENCE)},ensure_ascii=False))
