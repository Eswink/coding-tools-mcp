#!/usr/bin/env python3
"""Capture unchanged non-cloud RustSec reports and separate desktop source proof.

This is evidence production, not a security verdict. The final dependency
contract validates these reports, including warnings, before packages can build.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import urllib.request

import exact_build_audit as exact
from release_dependency_contract import LOCKS, hash_file

GLIB_URL = 'https://static.crates.io/crates/glib/glib-0.18.5.crate'
GLIB_SHA = '233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5'


def capture(root, output, audit_bin, database, sha, version):
    source = exact.source_identity(root, sha, version, 'x86_64-unknown-linux-gnu')
    exact.need(not output.exists() and not output.is_relative_to(root), 'capture_output_must_be_new_external')
    exact.need(not database.exists() and not database.is_relative_to(root), 'database_must_be_new_external')
    output.mkdir(parents=True)
    subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/RustSec/advisory-db.git', str(database)],
                   cwd=root, check=True)
    snapshot = exact.database_identity(database)
    code, version_bytes, _ = exact.execute([str(audit_bin), '--version'], root)
    exact.need(code == 0 and version_bytes.decode().strip() == 'cargo-audit 0.22.2', 'wrong_audit_tool')
    records = {}
    for name in ('desktop', 'local-agent', 'cloud-agent'):
        command = [str(audit_bin), 'audit', '--no-fetch', '--db', str(database), '--json', '--file', LOCKS[name]]
        code, data, error = exact.execute(command, root)
        (output / f'rust-audit-{name}.json').write_bytes(data)
        (output / f'rust-audit-{name}.stderr').write_bytes(error)
        exact.need(code in (0, 1), 'raw_audit_execution_failed')
        records[name] = dict(command=command, exit=code, raw_sha256=exact.digest(data),
                             lock_sha256=hash_file(root / LOCKS[name]))
    lock = tomllib.loads(exact.read(root / LOCKS['desktop']).decode())
    local_glib = any(p['name'] == 'glib' and p.get('source') is None for p in lock['package'])
    if local_glib:
        verifier = root / 'scripts/verify_glib_backport.py'
        exact.need(verifier.is_file() and not verifier.is_symlink(), 'desktop_glib_source_verifier_required')
        archive = output / 'glib-upstream.crate'
        with urllib.request.urlopen(GLIB_URL, timeout=60) as response:
            data = response.read(8 * 1024**2 + 1)
        exact.need(len(data) <= 8 * 1024**2 and exact.digest(data) == GLIB_SHA, 'wrong_glib_upstream_archive')
        archive.write_bytes(data)
        subprocess.run([sys.executable, str(verifier), '--root', str(root), '--archive', str(archive),
                        '--audit-bin', str(audit_bin), '--audit-db', str(database),
                        '--output', str(output / 'desktop-glib')], cwd=root, check=True)
        shutil.move(archive, output / 'desktop-glib/upstream.crate')
    exact.need(snapshot == exact.database_identity(database), 'advisory_database_changed')
    exact.need(source == exact.source_identity(root, sha, version, 'x86_64-unknown-linux-gnu'), 'source_changed')
    receipt = dict(schema=1, **source, source_root=str(root), run_id=os.environ['GITHUB_RUN_ID'],
                   run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], job=os.environ['GITHUB_JOB'],
                   workflow_ref=os.environ['GITHUB_WORKFLOW_REF'], repository=os.environ['GITHUB_REPOSITORY'],
                   audit_version=version_bytes.decode().strip(), audit_binary_sha256=hash_file(audit_bin),
                   advisory_database=snapshot, reports=records, desktop_glib_source_proof_required=local_glib,
                   release_approved=False, publish_approved=False)
    (output / 'raw-audit-capture.json').write_text(json.dumps(receipt, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'output', 'audit-bin', 'audit-db'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--version', required=True)
    a = p.parse_args()
    capture(a.root.resolve(), a.output.resolve(), a.audit_bin.resolve(), a.audit_db.resolve(),
            a.expected_sha, a.version)


if __name__ == '__main__':
    main()
