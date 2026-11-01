"""A1 C9-2: actual production Svelte route with synthetic IPC. No native proof:
the native confirm dialog is owned by the Rust command and is simulated here."""
import functools,http.server,json,os,threading
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_viewport_evidence import capture_control_viewports
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('UI_EVIDENCE_DIR',str(ROOT/'integration-attention-evidence')));OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def do_GET(self):
  if not Path(self.translate_path(self.path)).is_file() and not self.path.startswith('/_app/'):self.path='/index.html'
  super().do_GET()
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'build')))
threading.Thread(target=server.serve_forever,daemon=True).start()
fixture=(ROOT/'tests/fixtures/ui-refactor-ipc.js').read_text()
extra="""
(()=>{const original=window.__TAURI_INTERNALS__.invoke;
window.__ATTENTION__={journal:sessionStorage.getItem('fixture-journal')||'needs_attention',confirm:false,calls:[]};
window.__TAURI_INTERNALS__.invoke=async(cmd,args)=>{const s=window.__ATTENTION__;
if(cmd==='list_pending_integrations'){s.calls.push({cmd,args});return {recovery:{state:'none',journal:s.journal},pending:[]};}
if(cmd==='clear_integration_attention'){s.calls.push({cmd,args});if(!s.confirm)return null;s.journal='none';sessionStorage.setItem('fixture-journal','none');return {integration_id:'b'.repeat(32),state:'none',entries_discarded:3,workspace_files_written:false};}
return original(cmd,args);};})();
"""
report={'native_verified':False,'real_host_verified':False,'transport':'synthetic IPC / actual production Svelte UI','errors':[],'ok':False}
calls=lambda page:page.evaluate('window.__ATTENTION__.calls')
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,chromium_sandbox=True,executable_path=os.environ.get('CHROMIUM_PATH'))
  page=browser.new_page(viewport={'width':1280,'height':900},locale='zh-CN');page.on('pageerror',lambda e:report['errors'].append(str(e)))
  page.add_init_script(fixture+'\n'+extra);page.goto(f'http://127.0.0.1:{server.server_port}/workspace/fixture-workspace',wait_until='networkidle')
  panel=page.locator('section.attention');expect(panel.get_by_role('heading',name='合并日志需要处理')).to_be_visible()
  assert calls(page)==[{'cmd':'list_pending_integrations','args':{'id':'fixture-workspace'}}],calls(page)
  button=panel.get_by_role('button',name='在本机核对并清除',exact=True)
  capture_control_viewports(page,panel,ROOT,OUT,'needs-attention',[390,1280],900,[('notice',panel.get_by_role('heading',name='合并日志需要处理')),('clear',button)],report)
  page.set_viewport_size({'width':1280,'height':900})
  button.click();expect(panel.get_by_role('status')).to_contain_text('已取消')
  expect(button).to_be_visible();page.screenshot(path=str(OUT/'cancelled-1280.png'),full_page=False,animations='disabled')
  page.evaluate('window.__ATTENTION__.confirm=true');button.click();expect(panel.get_by_role('status')).to_contain_text('未写入任何工作区文件')
  expect(button).to_have_count(0);panel.scroll_into_view_if_needed();page.screenshot(path=str(OUT/'cleared-1280.png'),full_page=False,animations='disabled')
  final=calls(page);assert [c['cmd'] for c in final]==['list_pending_integrations','clear_integration_attention','clear_integration_attention'],final
  assert all(c['args']=={'id':'fixture-workspace'} for c in final)
  page.goto(f'http://127.0.0.1:{server.server_port}/workspace/fixture-workspace',wait_until='networkidle')
  expect(page.locator('section.attention')).to_have_count(0)
  assert [c['cmd'] for c in calls(page)]==['list_pending_integrations']
  report.update({'ok':not report['errors'],'one_scan_per_profile_load':True,'owner_cancel_preserved':True,'cleared_hides_notice':True,'idle_journal_shows_nothing':True,'calls':final});browser.close()
finally:
 server.shutdown();(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['ok']
