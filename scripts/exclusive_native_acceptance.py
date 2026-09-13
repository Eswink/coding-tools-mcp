"""Installed WebKit/WebView2 acceptance of the default single-owner workflow.

Real local IPC is used for owned fixture setup, window control and cancellation,
never to approve a conversation. Permission decisions are native WebDriver
clicks. Conversation metadata and OAuth credentials are explicitly synthetic.
OS toast visibility and real ChatGPT provenance are not inferred from this test.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import time
import urllib.parse
from native_approval_presentation import open_pending_dialog
from exclusive_native_gate import SCENARIO, TEST_NAMES
from exclusive_native_http import legacy, exchange, rpc, code_pair, rotate, replay, unavailable

gui, adapter = legacy.gui, legacy.adapter
NAME = 'Exclusive native acceptance'
MODAL = "//dialog[@aria-labelledby='global-approval-title']"
PANEL = "//section[@aria-labelledby='chat-authorization-heading']"


def status(session, profile):
    return session.invoke('chat_authorization_control', {'id': profile['id'], 'action': 'status',
        'requestId': None, 'scopes': None, 'exclusive': None})


def inbox(session):
    return session.invoke('chat_authorization_inbox')


def visit(session, profile):
    session.click_text(NAME)
    gui.wait_for(lambda: session.call('url'), lambda url:
        urllib.parse.urlsplit(url).path.rstrip('/') == '/workspace/' + profile['id'])
    gui.wait_for(session.body, lambda text: 'ChatGPT 聊天授权' in text and '远程会话安全' in text)


def modal_open(session):
    return session.execute("return !!document.querySelector('dialog[aria-labelledby=global-approval-title][open]')")


def candidate(session, base, token, chat, scopes):
    first = rpc(base, token, chat, 'request_chat_authorization', {'scopes': scopes})
    assert first.get('ok') is True and first['authorization']['status'] == 'pending'
    grant = first['authorization']
    again = rpc(base, token, chat, 'request_chat_authorization', {'scopes': scopes})
    assert again['authorization'] == grant, 'retry must not change pending scope or deadline'
    gui.wait_for(lambda: inbox(session), lambda value: len(value['pending']) == 1)
    # A native window not focused by its desktop may use the explicit inbox button.
    open_pending_dialog(lambda: modal_open(session),
        lambda: legacy.click(session, "//button[contains(@class,'approval-inbox')]"))
    gui.wait_for(lambda: modal_open(session))
    assert grant['fingerprint'] in session.body()
    assert session.execute("return document.querySelector('.approval-dialog .verify input').checked") is False
    assert session.execute("return document.querySelector('.approval-dialog footer .tx-btn-primary').disabled") is True
    return grant


def decide(session, base, token, chat, *, approve=True, drop_scope=None):
    if approve:
        if drop_scope:
            legacy.click(session, MODAL + f"//fieldset//input[@value='{drop_scope}']")
        legacy.click(session, MODAL + "//label[contains(@class,'verify')]//input")
        legacy.click(session, MODAL + "//button[normalize-space(.)='批准并独占']")
    else:
        legacy.click(session, MODAL + "//button[normalize-space(.)='拒绝']")
    expected = 'active' if approve else 'denied'
    value = gui.wait_for(lambda: rpc(base, token, chat, 'auth_status', {}),
        lambda value: value.get('authorization', {}).get('status') == expected)
    gui.wait_for(lambda: not modal_open(session))
    return value['authorization']


def revoke(session, profile):
    visit(session, profile)
    legacy.click(session, PANEL + "//button[normalize-space(.)='撤销全部']")


def scan_export(output, sensitive):
    found = 0
    for file in output.iterdir():
        if not file.is_file() or file.is_symlink(): continue
        raw = file.read_bytes()
        changed = raw
        for secret in sensitive:
            for encoding in ('utf-8', 'utf-16-le'):
                needle = secret.encode(encoding)
                if needle in changed:
                    found += 1
                    changed = changed.replace(needle, '[synthetic-secret-redacted]'.encode(encoding))
        if changed != raw: file.write_bytes(changed)
    return found


def run(args):
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    evidence = {'scenario': SCENARIO, 'passed': False, 'source_sha': args.source,
        'run_id': os.environ.get('GITHUB_RUN_ID'), 'platform': platform.platform(),
        'package_kind': args.kind, 'build_kind': 'release-installed',
        'real_native_webview': False, 'real_oauth_http': False, 'real_local_ipc': False,
        'synthetic_conversation_metadata': True, 'real_chatgpt_verified': False,
        'sandbox_disabled': False, 'cleanup_failed': False, 'cleanup_completed': False,
        'permission_approval_source': 'native-webdriver-clicks',
        'os_toast_visibility_verified': False, 'tests': []}
    session, profile, root = None, None, None
    sensitive = []
    def passed(index):
        assert index == len(evidence['tests'])
        evidence['tests'].append({'name': TEST_NAMES[index], 'passed': True})
        print('PASS ' + TEST_NAMES[index], flush=True)
    try:
        assert args.kind in ('deb', 'appimage', 'nsis')
        evidence['binary_sha256'] = hashlib.sha256(args.executable.read_bytes()).hexdigest()
        home = adapter.fixture_root(args)
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 1)
        evidence['real_native_webview'] = True
        evidence['version'] = session.invoke('plugin:app|version')
        assert evidence['version'] == json.loads(Path(__file__).resolve().parents[1].joinpath('package.json').read_text())['version']
        assert session.invoke('list_workspaces') == [], 'refusing an existing application profile'
        evidence['real_local_ipc'] = True
        root = home / 'exclusive-workspace'; root.mkdir()
        (root / 'sample.txt').write_text('exclusive-file-canary', encoding='utf-8')
        (root / 'hold.py').write_text("import pathlib,time\npathlib.Path('started').write_text('ready')\nprint('exclusive-child-canary',flush=True)\ntime.sleep(120)\n", encoding='utf-8')
        profile = session.invoke('create_workspace', {'path': str(root), 'name': NAME})
        p = profile['auth']['session_policy']
        assert p == {'exclusive': True, 'access_token_ttl_seconds': 3600,
            'refresh_session_ttl_seconds': 2592000, 'chat_lease_ttl_seconds': 86400, 'chat_idle_timeout_seconds': 0}
        passed(0)
        profile['tunnel'].update(type='none', public_url='')
        profile['auth'].update(type='oauth', oauth_client_id='exclusive-native-client', use_shared_secrets=False,
            oauth_redirect_uri='https://chatgpt.com/connector/oauth/exclusive-native-fixture')
        p.update(access_token_ttl_seconds=900, refresh_session_ttl_seconds=172800, chat_lease_ttl_seconds=7200)
        profile['runtime'].update(local_port=gui.port(), tool_profile='full')
        profile['actions'].update(tunnel_type='none', public_url='', auth_type='none', local_port=gui.port())
        assert profile['actions']['local_port'] != profile['runtime']['local_port']
        session.invoke('update_workspace', {'profile': profile})
        password, secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        sensitive.extend((password, secret))
        for key, value in [('oauth_password', password), ('oauth_client_secret', secret), ('oauth_token_secret', secrets.token_urlsafe(48))]:
            sensitive.append(value)
            session.invoke('set_workspace_secret', {'id': profile['id'], 'key': key, 'value': value})
        session.call('refresh', {}); visit(session, profile)
        fields = session.execute("return Array.from(document.querySelectorAll('.remote-session-settings input[type=number]'),e=>Number(e.value))")
        assert fields == [15, 2, 2, 0]
        assert session.execute("return document.querySelector('.remote-session-settings input[type=checkbox]').checked") is True
        assert session.invoke('list_workspaces')[0]['auth']['session_policy'] == p
        session.screenshot(output / 'native-session-settings.png')
        passed(1)
        session.invoke('start_runtime', {'id': profile['id']})
        base = 'http://127.0.0.1:' + str(profile['runtime']['local_port'])
        code, headers, _ = exchange(base + '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert code == 401 and headers['WWW-Authenticate'] == f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource/mcp", scope="mcp"'
        first = code_pair(base, profile, password, secret, sensitive); token = first['access_token']
        evidence['real_oauth_http'] = True
        passed(2)
        a, b, c = ['synthetic-exclusive-' + secrets.token_hex(16) for _ in range(3)]
        for chat, arguments in [(a, {}), (b, {'authorized': True, '_meta': {'openai/session': a}}), (None, {})]:
            unavailable(rpc(base, token, chat, 'server_info', arguments), str(root))
        assert rpc(base, token, a, 'auth_status', {})['authorization']['status'] == 'unauthorized'
        passed(3)
        session.click_text('通用')
        gui.wait_for(lambda: session.call('url'), lambda url: urllib.parse.urlsplit(url).path.rstrip('/') == '/settings/general')
        grant = candidate(session, base, token, a, legacy.SCOPES)
        assert 'Exclusive native acceptance' in session.body()
        # A fresh global dialog is visible away from the workspace route.
        session.screenshot(output / 'native-approval-modal.png')
        decision_start = int(time.time())
        active = decide(session, base, token, a, drop_scope='files.write')
        assert 'files.write' not in active['scopes']
        assert decision_start + 7200 <= active['expires_at'] <= int(time.time()) + 7200
        assert rpc(base, token, a, 'read_file', {'path': 'sample.txt'})['ok'] is True
        unavailable(rpc(base, token, a, 'apply_patch', {'patch': 'must-not-apply'}), str(root))
        passed(4)
        before = inbox(session)
        for _ in range(100):
            unavailable(rpc(base, token, b, 'request_chat_authorization', {'scopes': legacy.SCOPES}), str(root), 'EXCLUSIVE_CHAT_LOCKED')
        after = inbox(session)
        assert after['pending'] == [] and after['revision'] == before['revision']
        assert rpc(base, token, a, 'auth_status', {})['authorization']['id'] == grant['id']
        unavailable(rpc(base, token, b, 'server_info', {}), str(root), 'EXCLUSIVE_CHAT_LOCKED')
        assert not modal_open(session)
        evidence['foreign_request_count'] = 100
        passed(5)
        second = rotate(base, profile, secret, first, sensitive); token = second['access_token']
        refreshed = rpc(base, token, a, 'auth_status', {})['authorization']
        assert all(refreshed[key] == active[key] for key in ('id', 'fingerprint', 'expires_at', 'scopes'))
        assert rpc(base, token, a, 'server_info', {})['ok'] is True
        unavailable(rpc(base, token, b, 'request_chat_authorization', {}), str(root), 'EXCLUSIVE_CHAT_LOCKED')
        passed(6)
        python = 'python' if sys.platform == 'win32' else 'python3'
        job = rpc(base, token, a, 'start_exec_task', {'cmd': python + ' hold.py', 'request_id': 'exclusive-native-child', 'timeout_ms': 180000})
        assert job['ok'] is True
        gui.wait_for(lambda: (root / 'started').is_file(), timeout=25)
        revoke(session, profile)
        assert status(session, profile)['lease_state'] == 'draining'
        unavailable(rpc(base, token, b, 'request_chat_authorization', {}), str(root), 'CHAT_WORK_DRAINING')
        task_args = {'id': profile['id'], 'channel': 'mcp', 'action': 'cancel', 'args': {'job_id': job['job_id']}}
        assert session.invoke('control_exec_tasks', task_args)['ok'] is True
        task_args['action'] = 'get'
        stopped = gui.wait_for(lambda: session.invoke('control_exec_tasks', task_args), lambda value: value.get('terminal') is True)
        assert stopped['status'] == 'cancelled'
        gui.wait_for(lambda: status(session, profile), lambda value: value['lease_state'] == 'free')
        passed(7)
        candidate(session, base, token, b, ['workspace.read', 'files.read'])
        decide(session, base, token, b)
        unavailable(rpc(base, token, a, 'server_info', {}), str(root), 'EXCLUSIVE_CHAT_LOCKED')
        unavailable(rpc(base, token, b, 'exec_command', {'cmd': python + ' hold.py'}), str(root))
        unavailable(rpc(base, token, b, 'request_permissions', {'mode': 'dangerous', 'confirm': True}), str(root))
        revoke(session, profile)
        candidate(session, base, token, c, ['workspace.read'])
        decide(session, base, token, c, approve=False)
        unavailable(rpc(base, token, c, 'server_info', {}), str(root))
        passed(8)
        session.invoke('hide_to_tray')
        start = time.monotonic()
        pending = rpc(base, token, a, 'request_chat_authorization', {'scopes': ['workspace.read']})
        assert pending['ok'] is True
        time.sleep(1)
        assert len(inbox(session)['pending']) == 1
        session.invoke('show_main_window')
        open_pending_dialog(lambda: modal_open(session),
            lambda: legacy.click(session, "//button[contains(@class,'approval-inbox')]"))
        gui.wait_for(lambda: modal_open(session))
        assert session.execute("return document.querySelector('.approval-dialog .verify input').checked") is False
        session.screenshot(output / 'native-background-inbox.png')
        # Exercise the real backend deadline; never change its clock or policy.
        time.sleep(max(0, 90.2 - (time.monotonic() - start)))
        expired = gui.wait_for(lambda: rpc(base, token, a, 'auth_status', {}),
            lambda value: value.get('authorization', {}).get('status') == 'expired', timeout=12)
        assert expired['authorization']['id'] == pending['authorization']['id']
        gui.wait_for(lambda: not modal_open(session), timeout=12)
        assert inbox(session)['pending'] == []
        evidence['pending_elapsed_seconds'] = round(time.monotonic() - start, 3)
        passed(9)
        session.invoke('stop_runtime', {'id': profile['id']}); session.close(); session = None
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 2)
        restored = session.invoke('list_workspaces')
        assert len(restored) == 1 and restored[0]['auth']['session_policy'] == p
        session.invoke('start_runtime', {'id': profile['id']})
        third = rotate(base, profile, secret, second, sensitive)
        assert rpc(base, third['access_token'], a, 'auth_status', {})['authorization']['status'] == 'unauthorized'
        unavailable(rpc(base, third['access_token'], a, 'server_info', {}), str(root))
        assert inbox(session)['pending'] == []
        session.screenshot(output / 'native-restart-without-grant.png')
        passed(10)
        replay(base, profile, secret, first)
        replay(base, profile, secret, third)
        code, headers, _ = exchange(base + '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, token=third['access_token'])
        assert code == 401 and 'resource_metadata=' in headers['WWW-Authenticate']
        assert session.invoke('refresh_session_control', {'id': profile['id'], 'action': 'status'})['active_families'] == 0
        passed(11)
        assert len(evidence['tests']) == len(TEST_NAMES)
        evidence['passed'] = True
    except BaseException as error:
        evidence['failure_type'] = type(error).__name__
        if isinstance(error, adapter.NativeHostExited): evidence['host_exit_code'] = error.exit_code
        if session:
            try: session.screenshot(output / 'native-failure.png')
            except BaseException: pass
        raise
    finally:
        if session:
            try:
                session.close(); evidence['cleanup_completed'] = True
            except BaseException as error:
                evidence.update(passed=False, cleanup_failed=True, cleanup_failure_type=type(error).__name__)
        redactions = scan_export(output, sensitive)
        evidence.update(export_secret_scan_completed=True, export_secrets_found=False, secret_redactions=redactions)
        if redactions: evidence.update(passed=False, failure_type='SyntheticCredentialInExport')
        (output / 'exclusive-native.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': evidence['passed'], 'stages': len(evidence['tests']), 'scenario': SCENARIO}), flush=True)
        if not evidence['passed'] and sys.exc_info()[0] is None:
            raise RuntimeError('native acceptance or cleanup did not complete')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('executable', 'driver', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--kind', choices=('deb', 'appimage', 'nsis'), required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--fixture-root', type=Path)
    run(p.parse_args())
