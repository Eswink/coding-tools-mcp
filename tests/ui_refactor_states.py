"""State coverage for the actual application, with explicitly synthetic IPC only."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
from playwright.sync_api import Browser, expect


def check_states(browser: Browser, origin: str, fixture: Path, evidence: Path) -> list[dict]:
    results = []
    fixture_script = fixture.read_text(encoding='utf-8')

    @contextmanager
    def case(name: str, route: str, setup: str = '', theme: str = 'light'):
        context = browser.new_context(viewport={'width': 960, 'height': 640}, locale='zh-CN', color_scheme=theme)
        # One init script gives ordering guarantees: API stub, state overrides, app.
        context.add_init_script(script=fixture_script + '\n' + setup)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        try:
            page.goto(origin + route, wait_until='networkidle')
            expect(page.locator('main h2').first).to_be_visible()
            yield page
            overflow = page.evaluate('''() => [...document.querySelectorAll('.app-layout,.tx-main,.page-scroll,.page-body')].map(e=>({name:e.className,overflow:e.scrollWidth-e.clientWidth})).filter(e=>e.overflow>2)''')
            assert not overflow, f'{name}: {overflow}'
            assert not page.evaluate('window.__UI_FIXTURE__.state.unknown'), name
            assert not errors, f'{name}: {errors}'
            page.screenshot(path=str(evidence / f'state-{name}.png'), animations='disabled')
            results.append({'name': name, 'ok': True, 'file': f'state-{name}.png', 'native_verified': False})
        except Exception as error:
            results.append({'name': name, 'ok': False, 'error': str(error), 'browser_errors': errors})
            page.screenshot(path=str(evidence / f'state-{name}-failure.png'), animations='disabled')
            (evidence / f'state-{name}-failure.html').write_text(page.content(), encoding='utf-8')
            raise
        finally:
            (evidence / 'state-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            context.close()

    with case('empty-workspace', '/', 'window.__UI_FIXTURE__.state.workspaces=[];') as page:
        expect(page.get_by_role('heading', name='添加你的第一个工作区')).to_be_visible()
        expect(page.get_by_role('button', name='添加工作区', exact=True)).to_be_enabled()
        assert not page.evaluate("window.__UI_FIXTURE__.state.calls.some(c=>c.command.startsWith('start_'))")

    with case('empty-frp', '/settings/frp', 'window.__UI_FIXTURE__.state.profiles=[];') as page:
        expect(page.get_by_text('暂无 FRP 配置。', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='添加', exact=True)).to_be_enabled()

    with case('empty-software', '/settings/software', 'window.__UI_FIXTURE__.state.software=[];', theme='dark') as page:
        expect(page.get_by_text('暂无信息。', exact=True)).to_be_visible()
        expect(page.get_by_role('table')).to_have_count(0)

    with case('long-workspace', '/workspace/fixture-workspace', '''
        const profile=window.__UI_FIXTURE__.state.workspaces[0];
        profile.name='research-system-遥感化探钻孔长期开发工作区-'.repeat(4);
        profile.path='D:/projects/'+'nested-research-directory-'.repeat(24);
    ''') as page:
        assert len(page.locator('main h2').first.inner_text()) > 90
        danger = page.get_by_role('button', name='删除工作区', exact=True)
        expect(danger).to_be_visible()
        before = danger.evaluate('(el)=>getComputedStyle(el).color')
        danger.hover()
        assert danger.evaluate('(el)=>getComputedStyle(el).color') == before, 'Hover must preserve destructive emphasis'

    with case('partial-secret-failure', '/settings/keys', '''
        const original=window.__TAURI_INTERNALS__.invoke;
        window.__TAURI_INTERNALS__.invoke=async(command,args)=>{
          if(command==='get_shared_secret'&&args.key==='oauth_token_secret'){
            window.__UI_FIXTURE__.state.calls.push({command,args});
            throw Error('Synthetic key unavailable');
          }
          return original(command,args);
        };
    ''', theme='dark') as page:
        expect(page.get_by_label('MCP Token Secret', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='保存更改', exact=True)).to_be_disabled()
        expect(page.get_by_text('读取失败，禁止编辑/复制。', exact=True)).to_be_visible()
        assert 'SYNTHETIC_SECRET' not in page.inner_text('body')

    with case('task-empty-and-error', '/workspace/fixture-workspace', '''
        const original=window.__TAURI_INTERNALS__.invoke;
        window.__TAURI_INTERNALS__.invoke=async(command,args)=>{
          if(command==='control_exec_tasks'){
            window.__UI_FIXTURE__.state.calls.push({command,args});
            return window.__UI_FIXTURE__.state.healthFailure
              ?{ok:false,error:{message:'Synthetic task read unavailable'}}:{ok:true,jobs:[]};
          }
          return original(command,args);
        };
    ''') as page:
        page.get_by_role('tab', name='异步任务', exact=True).click()
        expect(page.get_by_text('暂无任务。通过 MCP／Actions 的 start_exec_task 提交；此面板不会自动启动命令。', exact=True)).to_be_visible()
        budget = page.get_by_role('button', name='保存预算', exact=True)
        assert budget.evaluate('(el)=>getComputedStyle(el).borderTopStyle') == 'solid'
        assert budget.evaluate('(el)=>el.getBoundingClientRect().height') >= 40
        page.evaluate('window.__UI_FIXTURE__.state.healthFailure=true')
        expect(page.get_by_role('alert')).to_have_text('Error: Synthetic task read unavailable')
        assert not page.evaluate("window.__UI_FIXTURE__.state.calls.some(c=>c.command==='control_exec_tasks'&&c.args.action!=='list')")
        assert not page.evaluate("window.__UI_FIXTURE__.state.calls.some(c=>c.command.startsWith('start_'))")

    with case('approval-minimum-dark', '/settings/general', theme='dark') as page:
        page.evaluate('window.__UI_FIXTURE__.pending()')
        dialog = page.get_by_role('dialog', name='ChatGPT 请求访问工作区')
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role('button', name='批准并独占', exact=True)).to_be_disabled()
        for _ in range(12):
            page.keyboard.press('Tab')
            assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)"), 'Focus escaped local approval'
        page.get_by_role('dialog').evaluate('(el)=>el.scrollTop=0')
        assert not page.evaluate("window.__UI_FIXTURE__.state.calls.some(c=>c.command==='chat_authorization_control'&&c.args.action==='approve')")

    with case('system-theme-live', '/settings/general', theme='light') as page:
        page.get_by_role('group', name='外观主题').get_by_role('button', name='跟随系统', exact=True).click()
        page.emulate_media(color_scheme='dark')
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        page.emulate_media(color_scheme='light')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')

    return results
