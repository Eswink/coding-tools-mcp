"""Actual production Svelte route with synthetic snapshot IPC. No native proof."""
import functools,http.server,json,os,threading
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_viewport_evidence import capture_control_viewports,native_window_contract
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('UI_EVIDENCE_DIR',str(ROOT/'snapshot-ui-evidence')));OUT.mkdir(parents=True,exist_ok=True)
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
const target={id:'a'.repeat(32),display_path:'managed/'+ 'a'.repeat(32),head:'b'.repeat(40),detached:true,native_profile_id:null};
const snapshot={id:'c'.repeat(32),digest:'d'.repeat(64),bytes:6,entries:[{path:'src/test.txt',directory:false,size:6,hash:'1'.repeat(64),mode:420}]};
window.__SNAPSHOTS__={target,snapshots:[],confirm:false,calls:[]};
window.__TAURI_INTERNALS__.invoke=async(cmd,args)=>{const s=window.__SNAPSHOTS__;
if(cmd==='list_managed_workspaces')return [{...target}];
if(cmd==='snapshot_list')return s.snapshots;
if(cmd==='register_managed_workspace'){s.calls.push({cmd,args});if(!s.confirm)return null;target.native_profile_id='registered-fixture';const profile={...window.__UI_FIXTURE__.state.workspaces[0],id:target.native_profile_id,name:'Managed snapshot fixture'};window.__UI_FIXTURE__.state.workspaces.push(profile);return profile;}
if(cmd==='snapshot_capture'){s.calls.push({cmd,args});s.snapshots=[snapshot];return snapshot;}
if(cmd==='snapshot_plan_restore')return {id:'e'.repeat(32),snapshot_id:snapshot.id,worktree_id:target.id,approval_digest:'f'.repeat(64),current_digest:'0'.repeat(64),snapshot_digest:snapshot.digest,expires_at:Date.now()/1000+120,changes:[{path:'src/test.txt',action:'replace'},{path:'extra.txt',action:'delete'}]};
if(cmd==='snapshot_restore'){s.calls.push({cmd,args});return s.confirm?{transaction_id:'1'.repeat(32),restored_digest:snapshot.digest,retained_backup:true}:null;}
return original(cmd,args);};})();
"""
report={'native_verified':False,'real_host_verified':False,'transport':'synthetic IPC / actual production Svelte UI','errors':[],'ok':False}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,chromium_sandbox=True,executable_path=os.environ.get('CHROMIUM_PATH'))
  page=browser.new_page(viewport={'width':1280,'height':900},locale='zh-CN');page.on('pageerror',lambda e:report['errors'].append(str(e)))
  page.add_init_script(fixture+'\n'+extra);page.goto(f'http://127.0.0.1:{server.server_port}/workspace/fixture-workspace',wait_until='networkidle')
  panel=page.locator('.snapshots');expect(panel).to_be_visible();assert page.evaluate('window.__SNAPSHOTS__.calls.length')==0
  panel.get_by_label('工作区',exact=True).select_option('a'*32)
  panel.get_by_role('button',name='在本机确认并注册独立工作区').click();expect(panel.get_by_role('status')).to_have_text('已取消注册。')
  assert page.evaluate('window.__SNAPSHOTS__.snapshots.length')==0
  page.evaluate('window.__SNAPSHOTS__.confirm=true');panel.get_by_role('button',name='在本机确认并注册独立工作区').click()
  expect(panel.get_by_role('link',name='打开独立工作区')).to_have_attribute('href','/workspace/registered-fixture')
  panel.get_by_role('button',name='创建明确快照').click();expect(panel.get_by_role('status')).to_contain_text('快照已完成')
  panel.get_by_role('button',name='预览恢复差异').click();expect(panel.get_by_text('移出并保留备份：extra.txt',exact=True)).to_be_visible()
  before_capture_calls=page.evaluate('window.__SNAPSHOTS__.calls.length')
  capture_control_viewports(page,panel,ROOT,OUT,'restore-plan',[390,native_window_contract(ROOT)['min_width'],1280],900,[
   ('workspace',panel.get_by_label('工作区',exact=True)),
   ('plan',panel.get_by_role('heading',name='恢复前核查',exact=True)),
   ('restore',panel.get_by_role('button',name='在本机核对并确认恢复',exact=True))],report)
  assert page.evaluate('window.__SNAPSHOTS__.calls.length')==before_capture_calls
  page.evaluate('window.__SNAPSHOTS__.confirm=false');panel.get_by_role('button',name='在本机核对并确认恢复').click();expect(panel.get_by_role('status')).to_have_text('已取消恢复。')
  panel.get_by_role('button',name='预览恢复差异').click();page.evaluate('window.__SNAPSHOTS__.confirm=true');panel.get_by_role('button',name='在本机核对并确认恢复').click();expect(panel.get_by_role('status')).to_contain_text('原内容备份仍保留')
  calls=page.evaluate('window.__SNAPSHOTS__.calls');assert set(calls[-1]['args'])=={'sourceId','worktreeId','planId','approvalDigest'}
  report.update({'ok':not report['errors'],'owner_cancel_preserved':True,'plan_bound_restore':True,'no_auto_capture':True,'calls':calls});browser.close()
finally:
 server.shutdown();(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['ok']
