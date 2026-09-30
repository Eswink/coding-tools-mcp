"""Actual Svelte UI with synthetic local IPC; not native approval acceptance."""
import functools, http.server, json, os, threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('UI_EVIDENCE_DIR', ROOT / 'hooks-ui-evidence'))
OUT.mkdir(parents=True, exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file() and not self.path.startswith('/_app/'):
            self.path = '/index.html'
        super().do_GET()
    def log_message(self, *args):
        pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT / 'build')))
threading.Thread(target=server.serve_forever, daemon=True).start()
fixture = (ROOT / 'tests/fixtures/ui-refactor-ipc.js').read_text()
extra = """
(()=>{
 const original=window.__TAURI_INTERNALS__.invoke;
 window.__HOOKS__={enabled:false,count:0,recovery_required:false};
 window.__HOOK_CALLS__=[];window.__HOOK_APPROVE__=false;window.__HOOK_FAIL__=false;
 window.__TAURI_INTERNALS__.invoke=async(command,args)=>{
  if(command==='get_policy_hooks')return {...window.__HOOKS__};
  if(command==='preview_policy_hooks')return {pending_id:'12345678-1234-1234-1234-123456789012',expires_in_seconds:60,native_dialog_required:true,preview:{digest:'a'.repeat(64),runtime_only:true,network_allowed:false,requires_local_conversation_authority:true,hooks:args.specs.map(manifest=>({manifest,executable_sha256:'b'.repeat(64),script_sha256:'c'.repeat(64),script_source:'print("synthetic local script")\\n# <script>not executed</script>'}))}};
  if(command==='approve_policy_hooks'){
   window.__HOOK_CALLS__.push({command,args});
   if(window.__HOOK_FAIL__)throw Error('SYNTHETIC_PRIVATE_ERROR');
   if(!window.__HOOK_APPROVE__)return null;
   window.__HOOKS__={enabled:true,count:1,recovery_required:false};return {...window.__HOOKS__};
  }
  if(command==='disable_policy_hooks'){window.__HOOK_CALLS__.push({command,args});window.__HOOKS__.enabled=false;window.__HOOKS__.count=0;return {...window.__HOOKS__};}
  return original(command,args);
 };
})();
"""
report = {'transport': 'synthetic IPC / actual built UI', 'native_verified': False, 'ok': False, 'scenarios': [], 'errors': []}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=True, executable_path=os.environ.get('CHROMIUM_PATH'))
        page = browser.new_page(viewport={'width': 1280, 'height': 1000}, locale='zh-CN')
        page.on('pageerror', lambda error: report['errors'].append(type(error).__name__))
        page.add_init_script(fixture + '\n' + extra)
        page.goto(f'http://127.0.0.1:{server.server_port}/workspace/fixture-workspace', wait_until='networkidle')
        panel = page.locator('.hooks-panel')
        expect(panel.get_by_role('status')).to_have_text('已停用')
        assert page.evaluate('window.__HOOK_CALLS__.length') == 0
        panel.locator('summary').click()
        manifest = [{'id':'check','event':'before_tool','tool':'exec_command','executable':'/usr/bin/python3','args':['-'],'script':'check.py','timeout_ms':1000,'workspace_write':False}]
        panel.get_by_label('Hooks JSON 清单', exact=True).fill(json.dumps(manifest))
        panel.get_by_role('button', name='生成本机预览', exact=True).click()
        approve = panel.get_by_role('button', name='在本机确认批准', exact=True)
        expect(approve).to_be_disabled()
        expect(panel.get_by_label('Hook 1 完整脚本', exact=True)).to_contain_text('<script>not executed</script>')
        assert panel.locator('script').count() == 0
        for width in [1280, 390]:
            page.set_viewport_size({'width':width,'height':1000})
            assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            panel.screenshot(path=str(OUT/f'preview-{width}.png'))
        panel.get_by_role('checkbox').check()
        approve.click()
        expect(panel.get_by_text('已取消本机确认。若要继续，请重新生成预览。', exact=True)).to_be_visible()
        assert page.evaluate('window.__HOOK_CALLS__.length') == 1
        report['scenarios'].append('exact escaped preview and checkbox, cancellation consumes token')
        panel.get_by_role('button', name='生成本机预览', exact=True).click()
        panel.get_by_role('checkbox').check()
        page.evaluate('window.__HOOK_APPROVE__=true')
        approve.click()
        expect(panel.get_by_role('status').first).to_contain_text('已启用')
        assert page.evaluate('window.__HOOK_CALLS__.at(-1).args.digest') == 'a'*64
        report['scenarios'].append('exact digest submitted only after explicit review')
        panel.get_by_role('button', name='生成本机预览', exact=True).click()
        panel.get_by_role('checkbox').check()
        page.evaluate('window.__HOOK_FAIL__=true')
        approve.click()
        expect(panel.get_by_role('button', name='生成本机预览', exact=True)).to_be_disabled()
        assert 'SYNTHETIC_PRIVATE_ERROR' not in panel.inner_text()
        panel.get_by_role('button', name='刷新 Hooks 状态', exact=True).click()
        expect(panel.get_by_role('button', name='生成本机预览', exact=True)).to_be_disabled()
        panel.screenshot(path=str(OUT/'uncertain.png'))
        report['scenarios'].append('uncertain mutation stays locked through read-only refresh')
        page.evaluate('window.__HOOKS__.recovery_required=true')
        panel.get_by_role('button', name='停用全部 Hooks', exact=True).click()
        expect(panel.get_by_text('未知执行结果仍被锁定。请在本机完成恢复核查；停用不会解除此锁定。', exact=True)).to_be_visible()
        report['scenarios'].append('disable retains recovery lock')
        assert not report['errors']
        report['ok'] = True
        browser.close()
finally:
    server.shutdown()
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
