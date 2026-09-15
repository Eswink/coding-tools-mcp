"""Strict installed-native evidence gate for numbered release candidates only.

This intentionally leaves the stable exclusive_native_gate unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import exclusive_native_gate as stable

RC_VERSION = re.compile(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-rc\.(?:0|[1-9]\d*)')


def verify(value, *, source, run_id, version, kind, binary_sha256):
    require = stable.require
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None, 'invalid source')
    require(re.fullmatch(r'[1-9][0-9]*', run_id) is not None, 'invalid run')
    require(RC_VERSION.fullmatch(version) is not None, 'invalid release-candidate version')
    require(re.fullmatch(r'[0-9a-f]{64}', binary_sha256) is not None, 'invalid digest')
    require(kind in ('deb', 'appimage', 'nsis'), 'must test the installed package')
    expected = {
        'scenario': stable.SCENARIO,
        'source_sha': source,
        'run_id': run_id,
        'version': version,
        'package_kind': kind,
        'binary_sha256': binary_sha256,
        'build_kind': 'release-installed',
    }
    require(all(value.get(key) == expected_value for key, expected_value in expected.items()),
            'candidate evidence identity mismatch')
    for key in ('passed', 'real_native_webview', 'real_oauth_http', 'real_local_ipc',
                'cleanup_completed', 'export_secret_scan_completed'):
        require(value.get(key) is True, 'missing completed observation: ' + key)
    for key in ('sandbox_disabled', 'cleanup_failed', 'real_chatgpt_verified', 'export_secrets_found'):
        require(value.get(key) is False, 'invalid observation boundary: ' + key)
    require(value.get('synthetic_conversation_metadata') is True, 'synthetic metadata must be labelled')
    require(not any(key in value for key in ('failure_type', 'cleanup_failure_type', 'host_exit_code')),
            'failed evidence')
    tests = value.get('tests')
    require(type(tests) is list and len(tests) == len(stable.TEST_NAMES), 'twelve new native stages required')
    require([test.get('name') for test in tests] == list(stable.TEST_NAMES), 'missing reordered or legacy stages')
    require(all(type(test) is dict and test.get('passed') is True for test in tests), 'native stage failed')
    require(value.get('foreign_request_count') == 100, 'foreign request matrix missing')
    require(value.get('pending_elapsed_seconds', 0) >= 90, 'real pending deadline was not exercised')
    require(value.get('permission_approval_source') == 'native-webdriver-clicks', 'approval cannot be simulated')
    return {
        **expected,
        'passed': True,
        'native_stages': len(stable.TEST_NAMES),
        'publish_approved': False,
        'scope': 'installed RC native and real local HTTP only; not real ChatGPT provenance or OS toast visibility',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'binary'):
        parser.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'run-id', 'version', 'kind'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    with args.binary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = verify(stable.load(args.input), source=args.source, run_id=args.run_id,
                    version=args.version, kind=args.kind, binary_sha256=digest)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
