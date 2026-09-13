"""Bounded real OAuth HTTP probes for the installed exclusive-session fixture.

Only synthetic, ephemeral credentials are accepted by the caller. Never follow
an OAuth redirect, log a token, or use these probes against a user's workspace.
"""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import urllib.parse

_spec = importlib.util.spec_from_file_location('legacy_native_http', Path(__file__).with_name('聊天授权原生验收v6.py'))
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
exchange, rpc = legacy.exchange, legacy.rpc


def code_pair(base: str, profile: dict, password: str, secret: str, sensitive: list[str]) -> dict:
    client = profile['auth']['oauth_client_id']
    callback = profile['auth']['oauth_redirect_uri']
    resource = base + '/mcp'
    for suffix in ('/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/mcp'):
        status, headers, raw = exchange(base + suffix)
        value = json.loads(raw)
        assert status == 200 and headers['Cache-Control'] == 'no-store'
        assert value['resource'] == resource and value['authorization_servers'] == [base]
        assert value['scopes_supported'] == ['mcp']
    status, headers, raw = exchange(base + '/.well-known/oauth-authorization-server')
    value = json.loads(raw)
    assert status == 200 and headers['Cache-Control'] == 'no-store'
    assert value['issuer'] == base and value['authorization_endpoint'] == base + '/oauth/authorize'
    assert value['token_endpoint'] == base + '/oauth/token'
    assert set(value['grant_types_supported']) == {'authorization_code', 'refresh_token'}
    assert set(value['scopes_supported']) == {'mcp', 'offline_access'}
    assert value['code_challenge_methods_supported'] == ['S256']
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    request = {'client_id': client, 'redirect_uri': callback, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'resource': resource,
        'scope': 'offline_access mcp mcp', 'state': 'exclusive-native-fixture'}
    status, _, page = exchange(base + '/oauth/authorize?' + urllib.parse.urlencode({**request, 'response_type': 'code'}))
    assert status == 200 and b'Offline access requested' in page
    assert all(item.encode() not in page for item in (password, secret, profile['path']))
    status, headers, _ = exchange(base + '/oauth/authorize', {**request, 'password': password}, form=True)
    assert status == 303
    location, expected = urllib.parse.urlsplit(headers['Location']), urllib.parse.urlsplit(callback)
    assert (location.scheme, location.netloc, location.path) == (expected.scheme, expected.netloc, expected.path)
    query = urllib.parse.parse_qs(location.query)
    assert query['state'] == [request['state']]
    form = {'grant_type': 'authorization_code', 'code': query['code'][0], 'code_verifier': verifier,
        'client_id': client, 'redirect_uri': callback, 'resource': resource}
    for wrong in (form, {**form, 'client_secret': 'invalid-exclusive-fixture'}):
        status, headers, raw = exchange(base + '/oauth/token', wrong, form=True)
        assert status == 401 and headers['WWW-Authenticate'] == 'Basic realm="oauth"'
        assert json.loads(raw)['error'] == 'invalid_client'
    status, headers, raw = exchange(base + '/oauth/token', {**form, 'client_secret': secret}, form=True)
    result = validate_pair(status, headers, raw, profile, sensitive)
    status, _, raw = exchange(base + '/oauth/token', {**form, 'client_secret': secret}, form=True)
    assert status == 400 and json.loads(raw)['error'] == 'invalid_grant'
    return result


def validate_pair(status, headers, raw, profile, sensitive):
    assert status == 200 and headers['Cache-Control'] == 'no-store' and headers['Pragma'] == 'no-cache'
    result = json.loads(raw)
    assert result['token_type'] == 'Bearer' and result['scope'] == 'mcp offline_access'
    assert result['expires_in'] == profile['auth']['session_policy']['access_token_ttl_seconds']
    assert isinstance(result['refresh_token'], str) and len(result['refresh_token']) > 40
    assert 0 < result['refresh_token_expires_in'] <= profile['auth']['session_policy']['refresh_session_ttl_seconds']
    sensitive.extend((result['access_token'], result['refresh_token']))
    return result


def rotate(base, profile, secret, pair, sensitive):
    form = {'grant_type': 'refresh_token', 'refresh_token': pair['refresh_token'],
        'client_id': profile['auth']['oauth_client_id'], 'client_secret': secret}
    # Resource omission is allowed only because the original binding is retained.
    status, headers, raw = exchange(base + '/oauth/token', form, form=True)
    result = validate_pair(status, headers, raw, profile, sensitive)
    assert result['refresh_token'] != pair['refresh_token']
    assert result['refresh_token_expires_in'] <= pair['refresh_token_expires_in']
    return result


def replay(base, profile, secret, spent):
    status, headers, raw = exchange(base + '/oauth/token', {'grant_type': 'refresh_token',
        'refresh_token': spent['refresh_token'], 'client_id': profile['auth']['oauth_client_id'],
        'client_secret': secret}, form=True)
    assert status == 400 and headers['Cache-Control'] == 'no-store'
    assert json.loads(raw)['error'] == 'invalid_grant'


def unavailable(value, private_path, code='CHAT_AUTHORIZATION_REQUIRED'):
    assert value.get('ok') is False and value.get('error', {}).get('code') == code
    rendered = json.dumps(value, ensure_ascii=False)
    assert private_path not in rendered and 'exclusive-child-canary' not in rendered
    if code != 'CHAT_AUTHORIZATION_REQUIRED':
        assert value['error']['retryable'] is False and value['requires_local_action'] is False
        assert 'authorization' not in value and 'fingerprint' not in rendered
