"""Exercise the real built SvelteKit routes with explicitly synthetic Tauri IPC.
Not an installed desktop, OAuth server or real ChatGPT acceptance substitute.
"""
from __future__ import annotations
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import threading
import traceback
from playwright.sync_api import sync_playwright, expect
from ui_refactor_states import check_states

ROOT = Path(os.environ.get('UI_TARGET_ROOT', Path(__file__).resolve().parents[1])).resolve()
EVIDENCE = Path(os.environ.get('UI_EVIDENCE_DIR', ROOT / 'ui-evidence')).resolve()
EVIDENCE.mkdir(parents=True, exist_ok=True)
MODE = os.environ.get('UI_MODE', 'candidate')
FIXTURE = Path(__file__).resolve().parent / 'fixtures/ui-refactor-ipc.js'
BUILD = ROOT / 'build'
if not (BUILD / 'index.html').is_file():
    raise RuntimeError('Build the actual application with npm run build first')
class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file() and not self.path.startswith('/_app/'):
            self.path = '/index.html'
        super().do_GET()
    def log_message(self, *args):
        pass
server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(SPAHandler,directory=str(BUILD)))
threading.Thread(target=server.serve_forever,daemon=True).start()
origin=f'http://127.0.0.1:{server.server_port}'
report={'mode':MODE,'transport':'mocked Tauri IPC; actual production build/routes','native_verified':False,
        'real_chatgpt_verified':False,'screens':[],'scenarios':[],'browser_errors':[],'ok':False}
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (ROOT/'src').rglob('*') if p.is_file()}
(EVIDENCE/'source-manifest.json').write_text(json.dumps({'files':sources,'fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest()},indent=2))
PAGES=[('workspace-overview','/workspace/fixture-workspace'),('general-settings','/settings/general'),
       ('credentials-and-keys','/settings/keys'),('frp-configuration','/settings/frp'),('software-management','/settings/software')]
VIEWPORTS=[(1586,992),(1280,800),(960,640),(1920,1080)]
page=None
try:
    with sync_playwright() as p:
        executable=os.environ.get('CHROMIUM_PATH','playwright-managed')
        kwargs={'headless':True,'chromium_sandbox':True}
        if executable!='playwright-managed':kwargs['executable_path']=executable
        browser=p.chromium.launch(**kwargs)
        for theme in ['light','dark']:
            for width,height in VIEWPORTS:
                context=browser.new_context(viewport={'width':width,'height':height},color_scheme=theme,locale='zh-CN')
                context.add_init_script(f"localStorage.setItem('theme',{json.dumps(theme)});")
                context.add_init_script(path=str(FIXTURE))
                page=context.new_page();page.on('pageerror',lambda e:report['browser_errors'].append(str(e)))
                for name,route in PAGES:
                    page.goto(origin+route,wait_until='networkidle',timeout=30000)
                    expect(page.locator('main')).to_be_visible()
                    page.wait_for_function("document.querySelector('main h2') !== null")
                    page.evaluate('()=>document.fonts.ready')
                    expect(page.locator('html')).to_have_attribute('data-theme',theme)
                    overflow=page.evaluate('''() => [...document.querySelectorAll('.app-layout,.tx-main,.page-scroll,.page-body')].map(e=>({name:e.className,overflow:e.scrollWidth-e.clientWidth})).filter(e=>e.overflow>2)''')
                    # The original product may have known small-window overflow. Record,
                    # but do not weaken the candidate gate or assert old visuals were fixed.
                    if MODE=='candidate':assert not overflow,f'{name} {width} {theme}: {overflow}'
                    unknown=page.evaluate('window.__UI_FIXTURE__.state.unknown')
                    assert not unknown,f'Incomplete IPC fixture: {unknown}'
                    path=EVIDENCE/f'{name}-{width}x{height}-{theme}.png'
                    page.screenshot(path=str(path),animations='disabled')
                    report['screens'].append({'page':name,'width':width,'height':height,'theme':theme,'file':path.name,'overflow':overflow})
                context.close()
        if MODE=='candidate':
            context=browser.new_context(viewport={'width':1280,'height':800},locale='zh-CN')
            context.add_init_script(path=str(FIXTURE));page=context.new_page()
            page.on('pageerror',lambda e:report['browser_errors'].append(str(e)))
            def fresh(route='/workspace/fixture-workspace'):
                page.goto(origin+route,wait_until='networkidle')
                page.wait_for_function("document.querySelector('main h2') !== null")
            def done(text):report['scenarios'].append({'name':text,'ok':True})
            fresh('/settings/general')
            themes=page.get_by_role('group',name='外观主题')
            themes.get_by_role('button',name='深色',exact=True).click()
            expect(page.locator('html')).to_have_attribute('data-theme','dark')
            expect(themes.get_by_role('button',name='深色',exact=True)).to_have_attribute('aria-pressed','true')
            page.get_by_role('button',name='切换主题',exact=True).click()
            expect(themes.get_by_role('button',name='浅色',exact=True)).to_have_attribute('aria-pressed','true')
            page.reload(wait_until='networkidle');expect(page.locator('html')).to_have_attribute('data-theme','light')
            done('real settings and sidebar theme controls share persisted state')
            page.get_by_role('button',name='FRP 配置',exact=True).click()
            expect(page).to_have_url(origin+'/settings/frp')
            expect(page.get_by_role('button',name='FRP 配置',exact=True)).to_have_attribute('aria-current','page')
            page.get_by_role('button',name='编辑',exact=True).click()
            expect(page.get_by_label('名称',exact=True)).to_have_value('默认配置')
            expect(page.get_by_text('Token （留空则保持不变）')).to_be_visible()
            page.get_by_role('button',name='更新',exact=True).click()
            page.wait_for_function("window.__UI_FIXTURE__.state.calls.some(c=>c.command==='save_frp_profile')")
            assert page.evaluate("window.__UI_FIXTURE__.state.calls.find(c=>c.command==='save_frp_profile').args.token") is None
            done('global profile editing preserves blank-token keep semantics and route identity')
            fresh('/settings/keys')
            inputs=page.locator('input[type="password"]')
            expect(inputs).to_have_count(9)
            assert 'SYNTHETIC_SECRET' not in page.inner_text('body')
            assert not page.locator('input[type="text"]').evaluate_all("els=>els.some(e=>e.value.includes('SYNTHETIC_SECRET'))")
            done('all shared credentials masked, no plaintext synthetic secret rendered')
            fresh()
            config=page.get_by_role('tab',name='配置',exact=True)
            config.focus();page.keyboard.press('ArrowRight')
            expect(page.get_by_role('tab',name='日志',exact=True)).to_be_focused()
            expect(config).to_have_attribute('aria-selected','true')
            page.keyboard.press('Enter');expect(page.get_by_role('tabpanel')).to_have_attribute('aria-labelledby','workspace-operations-logs')
            expect(page.get_by_text('Synthetic log — no real process was started.',exact=True)).to_be_visible()
            done('manual keyboard tab activation and actual log component render the typed result')
            page.get_by_role('tab',name='健康',exact=True).click()
            expect(page.get_by_text('尚未运行检查。',exact=True)).to_be_visible()
            page.evaluate('window.__UI_FIXTURE__.state.healthFailure=true')
            page.get_by_role('button',name='运行健康检查',exact=True).click()
            expect(page.get_by_text('健康检查未完成。请核对服务状态后重试；未将本次检查计为通过。')).to_be_visible()
            done('health starts unchecked and failed requests never render a passing state')
            fresh()
            # Draft ownership is exercised on a configuration field, not a port that
            # the existing ServicePanel intentionally saves on blur.
            client=page.get_by_role('textbox',name='OAuth 客户端 ID',exact=True)
            expect(client).to_be_visible();client.fill('synthetic-unsaved-client')
            page.get_by_role('button',name='Actions 服务',exact=False).click()
            page.wait_for_function("window.__UI_FIXTURE__.state.calls.some(c=>c.command==='plugin:dialog|message'&&c.args.title==='确认切换面板')")
            expect(client).to_have_value('synthetic-unsaved-client')
            expect(page.get_by_role('button',name='MCP 服务',exact=False)).to_have_attribute('aria-pressed','true')
            page.evaluate('window.__UI_FIXTURE__.state.confirmation=true')
            page.get_by_role('button',name='Actions 服务',exact=False).click()
            expect(page.get_by_role('button',name='Actions 服务',exact=False)).to_have_attribute('aria-pressed','true')
            done('cancel keeps actual unsaved config; explicit confirmation alone switches service')
            fresh('/settings/software')
            expect(page.get_by_role('table')).to_be_visible()
            expect(page.get_by_text('Cloudflare Tunnel',exact=True)).to_be_visible()
            assert '当前版本' not in page.get_by_role('table').inner_text()
            assert '最新版本' not in page.get_by_role('table').inner_text()
            done('software table exposes only supported installation facts, not invented versions')
            fresh('/settings/general')
            page.evaluate('window.__UI_FIXTURE__.pending()')
            dialog=page.get_by_role('dialog',name='ChatGPT 请求访问工作区')
            expect(dialog).to_be_visible()
            approve=dialog.get_by_role('button',name='批准并独占',exact=True)
            expect(approve).to_be_disabled()
            dialog.get_by_role('checkbox',name='执行命令（可访问共享文件）',exact=True).uncheck()
            dialog.get_by_role('checkbox',name='我已核对当前聊天返回的会话指纹和上述权限',exact=True).check()
            expect(approve).to_be_enabled()
            page.screenshot(path=str(EVIDENCE/'approval-fingerprint-light.png'),animations='disabled')
            approve.click();expect(dialog).not_to_be_visible()
            decisions=page.evaluate("window.__UI_FIXTURE__.state.calls.filter(c=>c.command==='chat_authorization_control'&&c.args.action==='approve')")
            assert len(decisions)==1 and decisions[0]['args']['scopes']==['files.read']
            done('unchanged global approval host works across routes and requires fingerprint/scope subset')
            assert not page.evaluate('window.__UI_FIXTURE__.state.unknown')
            context.close()
            report["state_scenarios"] = check_states(browser, origin, FIXTURE, EVIDENCE)
        assert not report['browser_errors'],report['browser_errors']
        report['ok']=True
        browser.close()
except Exception as error:
    report['error']=str(error)
    report['traceback']=traceback.format_exc()
    if page:
        try:
            page.screenshot(path=str(EVIDENCE/'failure.png'),animations='disabled')
            (EVIDENCE/'failure.html').write_text(page.content(),encoding='utf-8')
        except Exception:
            pass
    raise
finally:
    server.shutdown();server.server_close()
    (EVIDENCE/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
