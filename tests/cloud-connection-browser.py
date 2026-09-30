"""Actual built UI, synthetic IPC only. No native/real-host verification."""
import functools, http.server, json, os, threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('UI_EVIDENCE_DIR','/workspace/shared/native-ui-evidence')); OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file() and not self.path.startswith('/_app/'): self.path='/index.html'
        super().do_GET()
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'build')))
threading.Thread(target=server.serve_forever,daemon=True).start()
fixture=(ROOT/'tests/fixtures/ui-refactor-ipc.js').read_text()
extra="""
(() => {
const original=window.__TAURI_INTERNALS__.invoke;
window.__CLOUD__={phase:'configured',connected:false,generation:null,configured:true};
window.__CLOUD_CALLS__=[]; window.__CLOUD_CONFIRM__=false;
window.__TAURI_INTERNALS__.invoke=async (cmd,args)=>{
 if(cmd==='get_cloud_connection_status')return {...window.__CLOUD__};
 if(cmd==='start_cloud_connection'||cmd==='stop_cloud_connection'){
  window.__CLOUD_CALLS__.push({cmd,args});
  window.__CLOUD__={...window.__CLOUD__,phase:cmd==='start_cloud_connection'?'connected':'configured',connected:cmd==='start_cloud_connection'};
  return {...window.__CLOUD__};
 }
 if(cmd==='plugin:dialog|message')return window.__CLOUD_CONFIRM__?'确认继续':'取消';
 return original(cmd,args);
};
})();
"""
report={'transport':'synthetic IPC / actual built Svelte UI','native_verified':False,'real_host_verified':False,'states':[],'errors':[]}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'],executable_path=os.environ.get('CHROMIUM_PATH'))
  page=browser.new_page(viewport={'width':1280,'height':900},locale='zh-CN')
  page.on('pageerror',lambda error:report['errors'].append(str(error)))
  page.add_init_script(fixture+'\n'+extra)
  page.goto(f'http://127.0.0.1:{server.server_port}/workspace/fixture-workspace',wait_until='networkidle')
  panel=page.locator('.cloud-connection'); expect(panel).to_be_visible()
  labels={'unconfigured':'未配置','configured':'已配置 · 未连接','starting':'正在连接','connected':'已连接 · 未授权','pending_approval':'待本机批准','approved':'本机已授权','paused':'远程执行已暂停','draining':'正在排空','recovery':'恢复锁定'}
  for phase,label in labels.items():
   page.evaluate('(phase)=>{window.__CLOUD__={phase,connected:["connected","approved","pending_approval"].includes(phase),configured:phase!=="unconfigured",generation:null}}',phase)
   panel.get_by_role('button',name='刷新连接状态').click()
   expect(panel.get_by_role('status')).to_have_text(label)
   if phase!='unconfigured':
    expect(panel.get_by_role('button',name='启动云连接',exact=True)).to_be_enabled() if phase=='configured' else expect(panel.get_by_role('button',name='启动云连接',exact=True)).to_be_disabled()
   panel.screenshot(path=str(OUT/f'{phase}.png')); report['states'].append(phase)
  page.evaluate('window.__CLOUD__={phase:"configured",configured:true,connected:false,generation:null}')
  panel.get_by_role('button',name='刷新连接状态').click()
  panel.get_by_role('button',name='启动云连接',exact=True).click()
  expect(panel.get_by_role('button',name='启动云连接',exact=True)).to_be_enabled()
  assert page.evaluate('window.__CLOUD_CALLS__.length')==0
  page.evaluate('window.__CLOUD_CONFIRM__=true')
  panel.get_by_role('button',name='启动云连接',exact=True).click()
  expect(panel.get_by_role('status')).to_have_text('已连接 · 未授权')
  assert page.evaluate('window.__CLOUD_CALLS__[0].args.initializeJournals') is False
  for width in [390,1280]:
   page.set_viewport_size({'width':width,'height':900}); panel.screenshot(path=str(OUT/f'connected-{width}.png'))
   assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
  page.goto(f'http://127.0.0.1:{server.server_port}/settings/general',wait_until='networkidle')
  page.evaluate('window.__UI_FIXTURE__.emit("cloud-drain-incomplete")')
  expect(page.get_by_text('云连接需要本机核查',exact=True)).to_be_visible()
  page.evaluate('window.__UI_FIXTURE__.emit("cloud-drain-incomplete")')
  expect(page.get_by_text('云连接需要本机核查',exact=True)).to_have_count(1)
  page.screenshot(path=str(OUT/'global-drain-warning.png'))
  report['global_drain_warning_outside_workspace']=True
  report['confirmation_cancelled_without_submit']=True; report['explicit_normal_start_without_initialization']=True
  assert not report['errors'],report['errors']; report['ok']=True
  browser.close()
finally:
 server.shutdown(); (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
