"""Private owned-workspace source preparation. No installer, sudo, PATH or host writes."""
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import tarfile

OWNED_ROOT = Path('/workspace/work/rc070/publisher-supplementary-git-research')
SOURCE_SHA = '457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357'
SIGN_SHA = '8673501946204c38ebfed09603c1f3a041ed8d12b31f0aa06a474d41e359e254'
KEY_SHA = 'fd2809d850e844b614ac60f13ded554c55d9052e5c799a5814abcba2a68a063c'
PRIMARY = '96E07AF25771955980DAD10020D04E5A713660A7'
SUBKEY = 'E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB'
MAX_TAR = 64 * 1024 * 1024


def verify_git_source(archive, signature, public_key, evidence):
    # Pin downloaded material before any archive or source execution.
    for path, expected, limit in ((archive, SOURCE_SHA, 8177180), (signature, SIGN_SHA, 566), (public_key, KEY_SHA, 68820)):
        if Path(path).is_symlink():
            raise ValueError('source input symlink denied')
        data = Path(path).read_bytes()
        if len(data) != limit or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('source, signature or public-key bytes differ')
    evidence = Path(evidence)
    if not evidence.parent.resolve().is_relative_to(OWNED_ROOT) or evidence.exists() or evidence.is_symlink():
        raise ValueError('fresh owned evidence required')
    evidence.mkdir(mode=0o700)
    home = evidence / 'public-key-home'
    home.mkdir(mode=0o700)
    keyring = home / 'pinned-public-key.gpg'
    dearmored = subprocess.run(['/usr/bin/gpg', '--homedir', str(home), '--batch',
        '--no-options', '--no-autostart', '--output', str(keyring), '--dearmor', str(public_key)],
        capture_output=True, timeout=30)
    (evidence / 'dearmor.stderr').write_bytes(dearmored.stderr)
    if dearmored.returncode:
        raise ValueError('pinned public-key dearmor failed')
    with lzma.open(archive, 'rb') as compressed:
        tar_bytes = compressed.read(MAX_TAR + 1)
    if len(tar_bytes) > MAX_TAR:
        raise ValueError('archive expanded beyond bound')
    observed = subprocess.run(['/usr/bin/gpg', '--homedir', str(home), '--batch', '--no-options',
                              '--no-autostart', '--no-auto-key-retrieve', '--no-default-keyring',
                              '--keyring', str(keyring), '--status-fd', '1', '--verify', str(signature), '-'],
                              input=tar_bytes, capture_output=True, timeout=30)
    (evidence / 'developer.status').write_bytes(observed.stdout)
    (evidence / 'developer.stderr').write_bytes(observed.stderr)
    rows = [line.split() for line in observed.stdout.decode('ascii').splitlines()]
    valid = [r for r in rows if len(r) >= 12 and r[:2] == ['[GNUPG:]', 'VALIDSIG']]
    bad = {'BADSIG', 'ERRSIG', 'EXPKEYSIG', 'EXPSIG', 'REVKEYSIG', 'KEYEXPIRED', 'SIGEXPIRED', 'NO_PUBKEY', 'FAILURE'}
    if observed.returncode or len(valid) != 1 or valid[0][2] != SUBKEY or valid[0][-1] != PRIMARY or any(len(r)>1 and r[1] in bad for r in rows):
        raise ValueError('developer signature or pinned signer refused')
    (evidence / 'source-identity.json').write_text(json.dumps(dict(source_sha256=SOURCE_SHA,
        source_bytes=8177180,tar_bytes=len(tar_bytes),tar_sha256=hashlib.sha256(tar_bytes).hexdigest(),
        primary_fingerprint=PRIMARY,subkey_fingerprint=SUBKEY,gpg_exit=observed.returncode,
        trust='UNDEFINED; explicit pinned keyring and official primary fingerprint; not publisher grant',
        INSTALL=False,SUT_runs=0),indent=2)+'\n')
    return tar_bytes


def extract_owned_git_source(tar_bytes, destination):
    destination = Path(destination)
    if not destination.parent.resolve().is_relative_to(OWNED_ROOT) or destination.exists() or destination.is_symlink():
        raise ValueError('fresh owned source destination required')
    if len(tar_bytes) > MAX_TAR:
        raise ValueError('tar exceeds bound')
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) > 10000:
            raise ValueError('too many source entries')
        paths = set(); links = set(); total = 0
        for m in members:
            p = PurePosixPath(m.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'git-2.55.0' or str(p) in paths:
                raise ValueError('source path escapes, duplicates or wrong prefix')
            paths.add(str(p))
            if m.issym():
                target = posixpath.normpath(posixpath.join(str(p.parent), m.linkname))
                if PurePosixPath(m.linkname).is_absolute() or not target.startswith('git-2.55.0/'):
                    raise ValueError('source symlink escapes')
                links.add(str(p))
            elif not (m.isfile() or m.isdir()):
                raise ValueError('special or hard-linked source entry refused')
            if m.isfile():
                total += m.size
                if m.size > 8 * 1024 * 1024 or total > MAX_TAR:
                    raise ValueError('source member size exceeds bound')
        if any(str(parent) in links for name in paths for parent in PurePosixPath(name).parents):
            raise ValueError('source member under symlink refused')
        destination.mkdir(mode=0o700)
        manifest = []
        for m in sorted(members, key=lambda n: (not n.isdir(), n.name)):
            path = destination / m.name
            if m.isdir():
                path.mkdir(parents=True,exist_ok=True)
            elif m.isfile():
                path.parent.mkdir(parents=True,exist_ok=True)
                data = archive.extractfile(m).read()
                fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
                path.chmod(m.mode & 0o755)
                manifest.append(dict(path=m.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),mode=oct(m.mode&0o755)))
        for m in members:
            if m.issym():
                path = destination / m.name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.symlink_to(m.linkname)
                manifest.append(dict(path=m.name,symlink=m.linkname))
    (destination/'SOURCE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return destination/'git-2.55.0'


def build_owned_git(source, evidence):
    source=Path(source); evidence=Path(evidence)
    if not source.resolve().is_relative_to(OWNED_ROOT) or source.is_symlink() or not evidence.resolve().is_relative_to(OWNED_ROOT):
        raise ValueError('owned workspace only')
    # No install target, package manager, PATH override or external privileged write.
    vector=['/usr/bin/timeout','--signal=TERM','--kill-after=2s','480s','/usr/bin/make','-j2',
            'prefix='+str(evidence/'owned-prefix'),'all']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and not p.is_symlink()}
    with (evidence/'actual-build.log').open('xb') as log:
        completed=subprocess.run(vector,cwd=source,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,timeout=490)
    after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
    result=dict(command=vector,exit_code=completed.returncode,INSTALL=False,host_setup=False,
                original_source_files_unchanged=before==after,original_source_files=len(before),
                build_log_sha256=hashlib.sha256((evidence/'actual-build.log').read_bytes()).hexdigest(),
                SUT_runs=0,RC_qualification=False)
    binary=source/'git'
    if completed.returncode==0 and before==after and binary.is_file() and not binary.is_symlink():
        observed=subprocess.run([str(binary),'--no-pager','--no-replace-objects','--no-optional-locks','--no-lazy-fetch',
            '-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','core.untrackedCache=false',
            '-c','credential.helper=','-c','protocol.allow=never','--version'],capture_output=True,timeout=30)
        result.update(native_binary_bytes=binary.stat().st_size,native_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                      actual_fullflags_exit=observed.returncode,actual_fullflags_stdout=observed.stdout.decode('ascii'),
                      actual_fullflags_stderr_sha256=hashlib.sha256(observed.stderr).hexdigest())
    (evidence/'actual-build-result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
