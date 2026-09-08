from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect
import os, hashlib
root=Path(os.environ['TASK_PANEL_TEST_DIR']).resolve()
results=[]; errors=[]
def passed(name): results.append({'test':name,'passed':True})
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE'),headless=True)
  page=browser.new_page(viewport={'width':1100,'height':900})
  page.on('pageerror',lambda error: errors.append(str(error)))
  page.set_content('<meta charset="utf-8"><div id="app"></div>')
  page.add_script_tag(content=(root/'面板测试v3.js').read_text())
  expect(page.locator('pre').first).to_have_text('one/mcp/A中文🙂',timeout=7000)
  expect(page.locator('input')).to_have_value('30'); passed('生产Svelte面板挂载、双流中文与初始预算')
  page.wait_for_timeout(1700)
  expect(page.locator('pre').first).to_have_text('one/mcp/A中文🙂'); assert page.evaluate('window.maxInFlight')==1
  passed('同一视图轮询不重叠且日志不重复')
  page.evaluate("window.holdJob='A'"); page.wait_for_function('window.delayed.length===1')
  page.get_by_role('button',name='one/mcp/B').click();page.evaluate('window.releaseHeld()')
  expect(page.locator('pre').first).to_have_text('one/mcp/B中文🙂',timeout=5000);passed('任务切换丢弃迟到的旧任务响应')
  page.evaluate("window.holdJob='B'");page.wait_for_function('window.delayed.length===1')
  page.evaluate("window.changeView('two','actions')")
  expect(page.locator('pre').first).to_have_text('two/actions/A中文🙂',timeout=5000)
  page.evaluate('window.releaseHeld()');page.wait_for_timeout(100)
  expect(page.locator('pre').first).to_have_text('two/actions/A中文🙂');passed('工作区与服务切换隔离旧响应')
  page.evaluate('window.approve=false');page.get_by_role('button',name='请求取消',exact=True).click()
  page.wait_for_timeout(100);assert page.evaluate('window.cancelled.length')==0;passed('拒绝确认不发送取消')
  page.evaluate('window.approve=true');page.get_by_role('button',name='请求取消',exact=True).click()
  page.wait_for_function('window.cancelled.length===1');assert page.evaluate('window.cancelled[0]')==['two','actions','A',False]
  passed('取消仅作用于选定工作区与任务')
  page.get_by_role('button',name='two/actions/B').click()
  page.get_by_role('button',name='已人工确认旧进程停止').click(timeout=5000)
  page.wait_for_function('window.cancelled.length===2');assert page.evaluate('window.cancelled[1]')==['two','actions','B',True]
  passed('中断任务人工核查走显式确认参数')
  page.locator('input').fill('-1');page.get_by_role('button',name='保存上限',exact=True).click()
  expect(page.get_by_role('alert')).to_contain_text('1至1440');assert page.evaluate('window.saved.length')==0
  passed('无效执行预算不会保存')
  page.locator('input').fill('45');page.get_by_role('button',name='保存上限',exact=True).click()
  page.wait_for_function('window.saved.length===1');assert page.evaluate('window.saved[0]')==2700000
  passed('执行预算分钟正确换算为毫秒')
  page.evaluate("() => {window.oldGet=window.mockApi.get;window.mockApi.get=async()=>{throw new Error('fixture-storage-failed')};}")
  expect(page.get_by_role('alert')).to_contain_text('fixture-storage-failed',timeout=5000);passed('查询失败可见且不提交新命令')
  page.evaluate('() => {window.mockApi.get=window.oldGet;}');page.wait_for_timeout(1700)
  expect(page.get_by_role('alert')).to_have_count(0)
  page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true})")
  before=page.evaluate('window.calls.length');page.wait_for_timeout(1700);assert before==page.evaluate('window.calls.length')
  passed('后台隐藏面板暂停轮询并在错误消失后恢复显示')
  assert not errors, errors
  passed('全程无Svelte或浏览器运行异常')
  page.screenshot(path=str(root/'面板交互截图v3.png'),full_page=True)
  browser.close()
finally:
 (root/'面板交互结果v3.json').write_text(json.dumps({'passed':len(results)==12 and not errors,'count':len(results),'results':results,'browser_errors':errors,'bundle_sha256':hashlib.sha256((root/'面板测试v3.js').read_bytes()).hexdigest(),'scope':'production TaskPanel/TaskLogCursor, mocked Tauri API and native dialog; not native desktop end-to-end'},ensure_ascii=False,indent=2))
print(json.dumps({'tests':len(results),'errors':errors},ensure_ascii=False))
