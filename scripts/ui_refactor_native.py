"""Read actual installed pages with native clicks; never alter grants or UI data."""
from __future__ import annotations
import hashlib
from pathlib import Path
import time
import urllib.parse
from exclusive_native_http import legacy

PAGES = ('workspace', 'general', 'keys', 'frp', 'software')
SIZES = ((1280, 800), (960, 640))
THEMES = ('light', 'dark')
SCENARIO = 'ui-refactor-v1'


def review(session, profile, output: Path):
    rows = []
    routes = (
        ('workspace', 'Exclusive native acceptance', '/workspace/' + profile['id'], 'Exclusive native acceptance'),
        ('general', '通用', '/settings/general', '通用设置'),
        ('keys', '共享密钥', '/settings/keys', '共享密钥'),
        ('frp', 'FRP 配置', '/settings/frp', 'FRP 配置'),
        ('software', '软件管理', '/settings/software', '软件管理'),
    )
    def visit(label, route, heading):
        session.click_text(label)
        legacy.gui.wait_for(lambda: session.call('url'), lambda url:
            urllib.parse.urlsplit(url).path.rstrip('/') == route)
        legacy.gui.wait_for(lambda: session.execute(
            "return document.querySelector('main h2')?.textContent || ''"), lambda text: heading in text)

    for width, height in SIZES:
        session.call('window/rect', {'width': width, 'height': height})
        for theme in THEMES:
            visit('通用', '/settings/general', '通用设置')
            label = '浅色' if theme == 'light' else '深色'
            legacy.click(session, f"//*[@role='group' and @aria-label='外观主题']//button[normalize-space(.)='{label}']")
            legacy.gui.wait_for(lambda: session.execute("return document.documentElement.dataset.theme"), lambda value: value == theme)
            for name, label, route, heading in routes:
                visit(label, route, heading)
                if name == 'keys':
                    legacy.gui.wait_for(lambda: session.execute("return document.querySelectorAll('main input[type=password]').length"), lambda n: n == 9)
                time.sleep(.15)  # Layout settles; not a retry of any click/mutation.
                geometry = session.execute("""
                    return {width:innerWidth,height:innerHeight,
                      overflow:[...document.querySelectorAll('.app-layout,.tx-main,.page-scroll,.page-body')]
                        .map(e=>({container:e.className,excess:e.scrollWidth-e.clientWidth})).filter(e=>e.excess>2),
                      theme:document.documentElement.dataset.theme,
                      masked:!document.querySelector('main input[type=text][data-secret-revealed=true]')};
                """)
                assert not geometry['overflow'], f'native layout overflow: {name}/{width}/{theme}'
                assert geometry['theme'] == theme and geometry['width'] >= 800 and geometry['height'] >= 500
                # Viewport dimensions are observed separately from outer native window size.
                # Never claim screenshots match requested CSS pixels on a scaled desktop.
                if name == 'keys':
                    assert session.execute("return [...document.querySelectorAll('main input')].every(e=>e.type==='password')") is True
                file = output / f'ui-native-{name}-{width}x{height}-{theme}.png'
                session.screenshot(file)
                rows.append({'page': name, 'requested_window': [width, height], 'theme': theme,
                    'viewport': [geometry['width'], geometry['height']], 'overflow': geometry['overflow'],
                    'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'passed': True})
    # Return to a deterministic visible light workspace for the unchanged twelve
    # real OAuth / fingerprint / denial / draining / expiry / restart stages.
    session.call('window/rect', {'width': 1280, 'height': 800})
    visit('通用', '/settings/general', '通用设置')
    legacy.click(session, "//*[@role='group' and @aria-label='外观主题']//button[normalize-space(.)='浅色']")
    legacy.gui.wait_for(lambda: session.execute("return document.documentElement.dataset.theme"), lambda value: value == 'light')
    visit('Exclusive native acceptance', '/workspace/' + profile['id'], 'Exclusive native acceptance')
    return {'scenario': SCENARIO, 'passed': True, 'mock_transport': False,
        'interaction_source': 'native-webdriver-clicks', 'screens': rows, 'publish_approved': False}
