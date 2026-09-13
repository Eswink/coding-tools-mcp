"""Strict new-scenario evidence gate; legacy two-owner tests cannot satisfy it."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
from pathlib import Path
import json
import re

_spec = importlib.util.spec_from_file_location('legacy_evidence_loader', Path(__file__).with_name('聊天授权证据门禁v18.py'))
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
load, require = legacy.load, legacy.require
SCENARIO = 'exclusive-refresh-v1'
TEST_NAMES = (
    'installed native application and default exclusive policy',
    'configurable durations persist and render in the native form',
    'real discovery PKCE offline consent and code exchange',
    'unapproved missing context and forged tool arguments rejected',
    'global native modal requires fingerprint and scoped approval',
    'one hundred foreign requests produce no approval or owner replacement',
    'rotating access credentials preserve the approved owner and deadline',
    'live child prevents successor until local cancellation completes',
    'explicit release readonly successor and native denial',
    'background inbox and real ninety-second pending expiry',
    'process restart preserves refresh credentials but not chat approval',
    'spent refresh token revokes its family and linked access token',
)


def verify(value, *, source, run_id, version, kind, binary_sha256):
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None, 'invalid source')
    require(re.fullmatch(r'[1-9][0-9]*', run_id) is not None, 'invalid run')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is not None, 'invalid version')
    require(re.fullmatch(r'[0-9a-f]{64}', binary_sha256) is not None, 'invalid digest')
    require(kind in ('deb', 'appimage', 'nsis'), 'must test the installed package')
    expected = {'scenario': SCENARIO, 'source_sha': source, 'run_id': run_id, 'version': version,
        'package_kind': kind, 'binary_sha256': binary_sha256, 'build_kind': 'release-installed'}
    require(all(value.get(k) == v for k, v in expected.items()), 'candidate evidence identity mismatch')
    for key in ('passed', 'real_native_webview', 'real_oauth_http', 'real_local_ipc',
                'cleanup_completed', 'export_secret_scan_completed'):
        require(value.get(key) is True, 'missing completed observation: ' + key)
    for key in ('sandbox_disabled', 'cleanup_failed', 'real_chatgpt_verified', 'export_secrets_found'):
        require(value.get(key) is False, 'invalid observation boundary: ' + key)
    require(value.get('synthetic_conversation_metadata') is True, 'synthetic metadata must be labelled')
    require(not any(key in value for key in ('failure_type', 'cleanup_failure_type', 'host_exit_code')), 'failed evidence')
    tests = value.get('tests')
    require(type(tests) is list and len(tests) == len(TEST_NAMES), 'twelve new native stages required')
    require([t.get('name') for t in tests] == list(TEST_NAMES), 'missing reordered or legacy stages')
    require(all(type(t) is dict and t.get('passed') is True for t in tests), 'native stage failed')
    require(value.get('foreign_request_count') == 100, 'foreign request matrix missing')
    require(value.get('pending_elapsed_seconds', 0) >= 90, 'real pending deadline was not exercised')
    require(value.get('permission_approval_source') == 'native-webdriver-clicks', 'approval cannot be simulated')
    return {**expected, 'passed': True, 'native_stages': len(TEST_NAMES), 'publish_approved': False,
        'scope': 'installed native and real local HTTP only; not real ChatGPT provenance or OS toast visibility'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'binary'): p.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'run-id', 'version', 'kind'): p.add_argument('--' + key, required=True)
    a = p.parse_args()
    with a.binary.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps(verify(load(a.input), source=a.source, run_id=a.run_id,
        version=a.version, kind=a.kind, binary_sha256=digest)))


if __name__ == '__main__': main()
