"""Exact standalone release bytes and bounded evidence, never deployment authority."""
from __future__ import annotations
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tomllib
from rc_version_gate import verify_source, require
from final_rc_evidence import read_json
from exclusive_native_gate import legacy

BINS = ('coding-tools-gateway', 'coding-tools-agent', 'coding-tools-control-gateway', 'coding-tools-mcp-gateway')
MEMBERS = {*(f'bin/{name}' for name in BINS), 'manifest.json', 'README.md'}
TARGET = 'x86_64-unknown-linux-gnu'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def versions(root: Path, product: str) -> dict:
    components = {}
    for folder in ('cloud-gateway', 'cloud-agent', 'local-agent'):
        base = root / 'services' / folder
        package = tomllib.loads((base / 'Cargo.toml').read_text())['package']
        lock = tomllib.loads((base / 'Cargo.lock').read_text())['package']
        own = [p for p in lock if p.get('name') == package['name']]
        require(len(own) == 1 and own[0]['version'] == package['version'], 'component lock version mismatch')
        components[package['name']] = package['version']
    require(components['coding-tools-cloud-gateway'] == product,
            'BLOCKED: externally visible gateway product version must match selected RC')
    return components


def identity(root: Path, product: str) -> dict:
    proof = verify_source(root, expected_sha=os.environ['GITHUB_SHA'], expected_version=product)
    require(re.fullmatch(r'[1-9][0-9]*', os.environ.get('GITHUB_RUN_ID', '')) is not None, 'CI run required')
    return dict(source_sha=proof['source_sha'], source_tree=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True).strip(), run_id=os.environ['GITHUB_RUN_ID'],
        product_version=product, component_versions=versions(root, product), target=TARGET)


def elf(path: Path) -> None:
    require(path.is_file() and not path.is_symlink(), 'binary must be regular')
    with path.open('rb') as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01'
            and int.from_bytes(header[18:20], 'little') == 62, 'expected Linux ELF64 amd64 binary')


def probe(path: Path, product: str) -> dict:
    elf(path)
    results = {}
    for argument in ('--help', '--version'):
        result = subprocess.run([str(path), argument], capture_output=True, timeout=20, check=False)
        require(result.returncode == 0 and result.stdout and not result.stderr, 'release CLI probe failed')
        text = result.stdout.decode('utf-8')
        require(path.name in text, 'binary identity absent from CLI')
        if argument == '--version':
            parts = text.strip().split()
            require(len(parts) >= 2 and parts[0] == path.name and parts[1] == product, 'built product version mismatch')
        results[argument] = hashlib.sha256(result.stdout).hexdigest()
    invalid = subprocess.run([str(path)], input=b'', capture_output=True, timeout=20, check=False)
    require(invalid.returncode != 0, 'missing arguments must fail closed')
    dependencies = subprocess.run(['ldd', str(path)], capture_output=True, text=True, timeout=20, check=False)
    require(dependencies.returncode == 0 and 'not found' not in dependencies.stdout, 'unresolved runtime dependency')
    return {'cli_output_sha256': results, 'missing_arguments_rejected': True,
            'dynamic_dependencies': dependencies.stdout.splitlines()}


def build(root: Path, binary_dir: Path, output: Path, expected: dict) -> dict:
    require(not output.exists(), 'output must be new')
    os_info = platform.freedesktop_os_release()
    require(os_info.get('ID') == 'ubuntu' and os_info.get('VERSION_ID') == '22.04'
            and platform.machine() == 'x86_64', 'build must use Ubuntu22 amd64')
    entries = {}
    for name in BINS:
        path = binary_dir / name
        observations = probe(path, expected['product_version'])
        entries[name] = dict(sha256=digest(path), size=path.stat().st_size, **observations)
    manifest = dict(expected, schema=1, binaries=entries, build_os='ubuntu-22.04', publish_approved=False,
                    scope='Standalone cloud release binaries; no embedded configuration or credentials')
    output.mkdir(parents=True)
    archive = output / 'cloud-linux-amd64.tar.gz'
    with archive.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as tar:
            for member in sorted(MEMBERS):
                if member.startswith('bin/'):
                    data = (binary_dir / member.removeprefix('bin/')).read_bytes()
                elif member == 'manifest.json':
                    data = (json.dumps(manifest, indent=2) + '\n').encode()
                else:
                    data = (root / 'docs/releases/cloud-binary-install.md').read_bytes()
                info = tarfile.TarInfo(member); info.size = len(data); info.mtime = 0
                info.mode = 0o755 if member.startswith('bin/') else 0o644
                tar.addfile(info, io.BytesIO(data))
    receipt = dict(expected, passed=True, archive=dict(name=archive.name, size=archive.stat().st_size,
                                                      sha256=digest(archive)), publish_approved=False)
    (output / 'archive-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def unpack(directory: Path, output: Path, expected: dict) -> dict:
    require(not output.exists(), 'unpack target must be new')
    receipt = read_json(directory / 'archive-receipt.json')
    require(all(receipt.get(k) == v for k, v in expected.items()) and receipt.get('passed') is True,
            'archive source/version/run mismatch')
    item = receipt.get('archive', {})
    require(item.get('name') == 'cloud-linux-amd64.tar.gz', 'fixed archive name required')
    archive = directory / item['name']
    require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size == item.get('size')
            and digest(archive) == item.get('sha256'), 'archive digest mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        require(len(members) == len(MEMBERS) and {m.name for m in members} == MEMBERS,
                'archive member allowlist mismatch')
        require(all(m.isfile() and m.size > 0 and m.size < 256 * 1024**2
                    and m.mode == (0o755 if m.name.startswith('bin/') else 0o644) for m in members),
                'archive links/types/modes/sizes rejected')
        manifest_member = tar.getmember('manifest.json')
        require(manifest_member.size < 1024**2, 'manifest too large')
        manifest = json.loads(tar.extractfile(manifest_member).read(),
                              object_pairs_hook=legacy.unique_object, parse_constant=legacy.reject_constant)
        require(all(manifest.get(k) == v for k, v in expected.items()) and type(manifest.get('schema')) is int and manifest['schema'] == 1
                and manifest.get('build_os') == 'ubuntu-22.04' and manifest.get('publish_approved') is False,
                'inner manifest identity mismatch')
        require(set(manifest.get('binaries', {})) == set(BINS), 'four binary records required')
        # All names/types validated before any path is written; extractall is never used.
        output.mkdir(parents=True)
        for member in members:
            data = tar.extractfile(member).read()
            if member.name.startswith('bin/'):
                record = manifest['binaries'][member.name.removeprefix('bin/')]
                require(len(data) == record.get('size') and hashlib.sha256(data).hexdigest() == record.get('sha256'),
                        'binary payload digest mismatch')
            path = output / member.name; path.parent.mkdir(exist_ok=True)
            path.write_bytes(data); path.chmod(member.mode)
    return manifest


def unpack_trusted(directory: Path, output: Path, expected: dict, archive_sha256: str) -> dict:
    from release_dependency_contract import hash_value
    hash_value(archive_sha256)
    archive = directory / 'cloud-linux-amd64.tar.gz'
    require(archive.is_file() and not archive.is_symlink() and digest(archive) == archive_sha256,
            'archive differs from trusted producer digest')
    return unpack(directory, output, expected)


def smoke_reports(root: Path, evidence: Path) -> dict:
    results = {}
    for script, suite in [('run_service_http.py', 'standalone_process_http'), ('run_agent_process.py', 'agent_process_wss')]:
        tree = ast.parse((root / 'services/cloud-gateway/tests' / script).read_text())
        names = {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'passed'
                 and node.args and isinstance(node.args[0], ast.Constant)}
        value = read_json(evidence / (suite + '.json'))
        require(value.get('suite') == suite and value.get('result') == 'PASS'
                and type(value.get('passed')) is int and value['passed'] == len(names)
                and type(value.get('cases')) is list and len(value['cases']) == len(names)
                and set(value['cases']) == names, 'missing or failed release process cases')
        require(value.get('production_touched', False) is False and value.get('physical_host', False) is False,
                'process scope mismatch')
        results[suite] = value
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('versions', 'build', 'unpack', 'finish'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--expected-archive-sha256')
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    expected = identity(root, args.version)
    if args.mode == 'versions':
        print(json.dumps(expected)); return
    require(args.directory is not None and args.output is not None, 'directory/output required')
    if args.mode == 'build':
        build(root, args.directory.resolve(), args.output.resolve(), expected)
    elif args.mode == 'unpack':
        require(args.expected_archive_sha256 is not None, 'trusted producer archive digest required')
        unpack_trusted(args.directory.resolve(), args.output.resolve(), expected, args.expected_archive_sha256)
    else:
        require(args.evidence is not None, 'process evidence required')
        reports = smoke_reports(root, args.evidence)
        manifest = read_json(args.directory / 'manifest.json')
        require(all(manifest.get(k) == v for k, v in expected.items()), 'smoked source mismatch')
        for name in BINS:
            path = args.directory / 'bin' / name
            require(digest(path) == manifest['binaries'][name]['sha256'], 'smoked binary changed')
            probe(path.resolve(), expected['product_version'])
        args.output.write_text(json.dumps(dict(expected, passed=True, publish_approved=False, process_reports=reports,
            scope='Identity HTTP and control/Agent WSS process smoke; MCP CLI smoke only; no VPS or ChatGPT claim'), indent=2) + '\n')


if __name__ == '__main__':
    main()
