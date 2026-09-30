"""Transfer one immutable engineering ZIP in bounded chunks; never unpack or run it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = 'Eswink/coding-tools-mcp'
REPOSITORY_ID = 1360355522
ARTIFACT_ID = 11114636713
RUN_ID = 36748964715
SOURCE_SHA = 'fde46cc6299be88ffcf6b3fa3236d222dbdda7b1'
SOURCE_TREE = '183ea60ebc6f08010c885d436f8b4c02fc7800d7'
ARTIFACT_NAME = 'NOT_FINAL-NOT_PUBLISHABLE-linux-rc-packages-' + SOURCE_SHA
ARCHIVE_SIZE = 97384787
ARCHIVE_SHA256 = 'e7d8c352ba7f384c8c5dce25b74620d43211508d4ce7dcf960dae4b53c7d720d'
CHUNK_BYTES = 23 * 1024 * 1024
CHUNK_COUNT = 5


class TransferError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise TransferError(code)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536,
            'invalid_json_file')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError):
        raise TransferError('invalid_json') from None
    require(type(value) is dict, 'invalid_json_object')
    return value


def original_identity():
    return dict(repository=REPOSITORY, artifact_id=ARTIFACT_ID, run_id=RUN_ID,
                source_sha=SOURCE_SHA, source_tree=SOURCE_TREE,
                name=ARTIFACT_NAME, size=ARCHIVE_SIZE, sha256=ARCHIVE_SHA256)


def validate_metadata(value):
    require(type(value) is dict, 'invalid_artifact_metadata')
    require(type(value.get('id')) is int and value['id'] == ARTIFACT_ID, 'wrong_artifact_id')
    require(value.get('name') == ARTIFACT_NAME and value.get('expired') is False,
            'wrong_or_expired_artifact')
    require(type(value.get('size_in_bytes')) is int and value['size_in_bytes'] == ARCHIVE_SIZE,
            'wrong_artifact_size')
    require(value.get('digest') == 'sha256:' + ARCHIVE_SHA256, 'wrong_artifact_digest')
    run = value.get('workflow_run')
    require(type(run) is dict and type(run.get('id')) is int and run['id'] == RUN_ID,
            'wrong_source_run')
    require(run.get('head_sha') == SOURCE_SHA
            and run.get('head_branch') == 'ci/preliminary-packages-20260930'
            and run.get('repository_id') == REPOSITORY_ID
            and run.get('head_repository_id') == REPOSITORY_ID, 'wrong_source_repository')


def validate_archive(path):
    require(path.is_file() and not path.is_symlink(), 'archive_not_regular')
    require(path.stat().st_size == ARCHIVE_SIZE, 'archive_size_mismatch')
    require(digest(path) == ARCHIVE_SHA256, 'archive_digest_mismatch')


def split_archive(archive, directory, transfer_sha, transfer_run):
    validate_archive(archive)
    require(re.fullmatch(r'[0-9a-f]{40}', transfer_sha) is not None
            and re.fullmatch(r'[1-9][0-9]*', transfer_run) is not None, 'invalid_transfer_identity')
    require((ARCHIVE_SIZE + CHUNK_BYTES - 1) // CHUNK_BYTES == CHUNK_COUNT,
            'unexpected_chunk_count')
    directory.mkdir(mode=0o700, exist_ok=False)
    parts = []
    with archive.open('rb') as stream:
        for index in range(CHUNK_COUNT):
            offset = index * CHUNK_BYTES
            expected = min(CHUNK_BYTES, ARCHIVE_SIZE - offset)
            data = stream.read(expected)
            require(len(data) == expected, 'source_changed_during_split')
            name = f'original.zip.part-{index:02d}'
            with (directory / name).open('xb') as output:
                output.write(data)
            parts.append(dict(name=name, offset=offset, size=len(data),
                              sha256=hashlib.sha256(data).hexdigest()))
        require(not stream.read(1), 'source_grew_during_split')
    validate_archive(archive)
    receipt = dict(schema=1, status='NOT_FINAL_NOT_PUBLISHABLE', original=original_identity(),
                   transfer_source_sha=transfer_sha, transfer_run_id=transfer_run,
                   original_bytes_unchanged=True, extraction_performed=False,
                   binary_execution_performed=False, release_approved=False, chunks=parts)
    # Independently stream the parts again; never trust only the source file hash.
    combined = hashlib.sha256()
    for part in parts:
        with (directory / part['name']).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                combined.update(block)
    require(combined.hexdigest() == ARCHIVE_SHA256, 'split_roundtrip_mismatch')
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def join_archive(directory, output):
    receipt = read_json(directory / 'receipt.json')
    require(receipt.get('schema') == 1 and receipt.get('original') == original_identity(),
            'wrong_original_identity')
    require(receipt.get('status') == 'NOT_FINAL_NOT_PUBLISHABLE'
            and receipt.get('original_bytes_unchanged') is True
            and receipt.get('extraction_performed') is False
            and receipt.get('binary_execution_performed') is False
            and receipt.get('release_approved') is False, 'invalid_transfer_scope')
    parts = receipt.get('chunks')
    require(type(parts) is list and len(parts) == CHUNK_COUNT, 'wrong_chunk_inventory')
    expected_names = {'receipt.json'} | {f'original.zip.part-{i:02d}' for i in range(CHUNK_COUNT)}
    require({p.name for p in directory.iterdir()} == expected_names, 'unexpected_transfer_files')
    for index, part in enumerate(parts):
        name = f'original.zip.part-{index:02d}'
        size = min(CHUNK_BYTES, ARCHIVE_SIZE - index * CHUNK_BYTES)
        require(type(part) is dict and part.get('name') == name
                and type(part.get('offset')) is int and part['offset'] == index * CHUNK_BYTES
                and type(part.get('size')) is int and part['size'] == size, 'invalid_chunk_record')
        path = directory / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == size,
                'invalid_chunk_file')
        require(re.fullmatch(r'[0-9a-f]{64}', str(part.get('sha256'))) is not None
                and digest(path) == part['sha256'], 'chunk_digest_mismatch')
    require(not output.exists() and not output.is_symlink(), 'output_already_exists')
    created = False
    try:
        with output.open('xb') as destination:
            created = True
            for part in parts:
                with (directory / part['name']).open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        destination.write(block)
        validate_archive(output)
    except Exception:
        if created:
            output.unlink()
        raise
    return original_identity()


def github_read(endpoint, destination):
    env = {**os.environ, 'GH_HOST': 'github.com', 'GH_DEBUG': ''}
    command = ['gh', 'api', '--method', 'GET', '-H', 'X-GitHub-Api-Version: 2022-11-28',
               '/repos/' + REPOSITORY + endpoint]
    with destination.open('xb') as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                env=env, timeout=180, check=False)
    # Never export raw CLI errors, request headers, credentials or redirect URLs.
    require(result.returncode == 0, 'github_artifact_read_failed')


def rematerialize_fixed_artifact(directory):
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'hosted_owned_repository_only')
    require(directory.resolve() == Path(os.environ['RUNNER_TEMP']).resolve() / 'fde46cc-transfer',
            'fixed_disposable_destination_required')
    directory.mkdir(mode=0o700, exist_ok=False)
    metadata = directory / 'source-metadata.json'
    endpoint = f'/actions/artifacts/{ARTIFACT_ID}'
    github_read(endpoint, metadata)
    validate_metadata(read_json(metadata))
    archive = directory / 'original.zip'
    github_read(endpoint + '/zip', archive)
    return split_archive(archive, directory / 'chunks', os.environ['GITHUB_SHA'],
                         os.environ['GITHUB_RUN_ID'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    commands.add_parser('fetch')
    join = commands.add_parser('join')
    join.add_argument('--directory', type=Path, required=True)
    join.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'fetch':
        result = rematerialize_fixed_artifact(Path(os.environ['RUNNER_TEMP']) / 'fde46cc-transfer')
        print(json.dumps(dict(transferred=True, original=result['original'], chunks=len(result['chunks']),
                              release_approved=False)))
    else:
        print(json.dumps(dict(reassembled=True, original=join_archive(args.directory, args.output),
                              release_approved=False)))


if __name__ == '__main__':
    try:
        main()
    except (TransferError, OSError, subprocess.SubprocessError, KeyError) as error:
        print(json.dumps(dict(passed=False, error=error.args[0] if isinstance(error, TransferError)
                              else 'transfer_io_or_environment_failure')))
        raise SystemExit(1) from None
