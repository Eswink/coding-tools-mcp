"""Reviewed workspace proposal. No CLI, system install, Git build or CI launch.

Only prepare_owned_gettext(execute=True) executes authenticated GNU source;
that separate call requires root review. Default is provenance/extraction only.
This assumes a private trusted workspace, not hostile concurrent same-UID access.
"""
import io
import json
import hashlib
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import struct
import subprocess
import tarfile
import time

OWNED_ROOT = Path('/workspace/work/rc070/publisher-owned-gettext-research')
SOURCE_SHA = '71132a3fb71e68245b8f2ac4e9e97137d3e5c02f415636eb508ae607bc01add7'
SIGN_SHA = 'f0a94f0bde80f56a7dc079b9a22aaf3594915acd66fdd916e1508a10ccee506a'
KEY_SHA = '0fe55175b96a8ea1c4b670cc3fe11d56b341e4eff81b161ea49958ae550be6ca'
SIGNER = 'E0FFBD975397F77A32AB76ECB6301D9E1BBEAC08'
TOOLS = ('/usr/bin/git', '/usr/bin/cc', '/usr/bin/make', '/usr/bin/gpg',
         '/usr/bin/python3', '/usr/bin/openssl', '/usr/bin/timeout',
         '/bin/sh', '/usr/bin/ar', '/usr/bin/ranlib', '/usr/bin/readelf', '/usr/bin/ldd',
         '/usr/bin/c++', '/usr/bin/nm', '/usr/bin/strip')


def validate_gettext_signature_status(exit_code, raw_status):
    rows = [line.split() for line in raw_status.decode('ascii').splitlines()]
    allowed = {'NEWSIG', 'KEY_CONSIDERED', 'SIG_ID', 'GOODSIG', 'VALIDSIG',
               'TRUST_UNDEFINED', 'TRUST_MARGINAL', 'TRUST_FULLY', 'TRUST_ULTIMATE'}
    if any(len(r) < 2 or r[0] != '[GNUPG:]' or r[1] not in allowed for r in rows):
        raise ValueError('Unknown, expired, revoked or bad signing status denied')
    valid = [r for r in rows if r[1] == 'VALIDSIG']
    good = [r for r in rows if r[1] == 'GOODSIG']
    if (exit_code or len(valid) != 1 or len(valid[0]) != 12 or
            valid[0][2] != SIGNER or valid[0][-1] != SIGNER or
            len(good) != 1 or good[0][2] != SIGNER[-16:]):
        raise ValueError('Exact GNU signer and GOODSIG/VALIDSIG required')
    return {'signer': SIGNER, 'trust': 'Explicit official GNU registry pin; TRUST_UNDEFINED retained; not publisher grant'}


def snapshot_owned_tool(path, native=False):
    path = Path(path)
    lexical = path.lstat()
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024 * 1024:
        raise ValueError('Bounded regular tool required')
    if native and (path.is_symlink() or not before.st_mode & 0o111):
        raise ValueError('Literal executable regular native payload required')
    with resolved.open('rb') as stream:
        data = stream.read(128 * 1024 * 1024 + 1)
    after = resolved.stat()
    stable_fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    lexical_after = path.lstat()
    if (tuple(getattr(before,k) for k in stable_fields) != tuple(getattr(after,k) for k in stable_fields) or
            tuple(getattr(lexical,k) for k in stable_fields) != tuple(getattr(lexical_after,k) for k in stable_fields) or
            path.resolve() != resolved):
        raise ValueError('Tool identity changed during read')
    if native and data[:4] != b'\x7fELF':
        raise ValueError('Native ELF required; wrapper refused')
    return {'path': str(path), 'resolved_path': str(resolved), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'mode': before.st_mode,
            'device': before.st_dev, 'inode': before.st_ino, 'mtime_ns': before.st_mtime_ns,
            'ctime_ns': before.st_ctime_ns,
            'lexical_mode': lexical.st_mode, 'lexical_device': lexical.st_dev,
            'lexical_inode': lexical.st_ino}


def verify_gettext_source(archive, signature, keyring, evidence):
    inputs = []
    for path, size, digest in ((archive, 10721600, SOURCE_SHA),
                              (signature, 228, SIGN_SHA), (keyring, 3698125, KEY_SHA)):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source input must be literal regular file')
        with path.open('rb') as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Source input byte pin mismatch')
        inputs.append(raw)
    evidence = Path(evidence)
    if evidence.parent.resolve() != evidence.parent or not evidence.parent.is_relative_to(OWNED_ROOT):
        raise ValueError('Literal owned evidence parent required')
    evidence.mkdir(mode=0o700)  # Fresh exclusive namespace; existing target refused.
    home = evidence / 'gpg-home'; home.mkdir(mode=0o700)
    # Use exact captured pinned bytes for GPG and later extraction.
    for name, raw in zip(('source.tar.xz', 'source.sig', 'keyring.gpg'), inputs):
        with (evidence / name).open('xb') as stream:
            stream.write(raw)
    before = snapshot_owned_tool('/usr/bin/gpg')
    observed = subprocess.run(['/usr/bin/gpg', '--homedir', str(home), '--batch',
        '--no-options', '--no-autostart', '--no-auto-key-retrieve', '--no-default-keyring',
        '--keyring', str(evidence/'keyring.gpg'), '--status-fd', '1', '--verify',
        str(evidence/'source.sig'), str(evidence/'source.tar.xz')], capture_output=True, timeout=30)
    (evidence/'signature.status').write_bytes(observed.stdout)
    (evidence/'signature.stderr').write_bytes(observed.stderr)
    identity = validate_gettext_signature_status(observed.returncode, observed.stdout)
    if before != snapshot_owned_tool('/usr/bin/gpg'):
        raise ValueError('GPG payload lease changed')
    identity.update(source_sha256=SOURCE_SHA, signature_sha256=SIGN_SHA,
                    keyring_sha256=KEY_SHA, SOURCE_EXECUTION=False,
                    OWNED_INSTALL=False, HOST_INSTALL=False, SUT_runs=0)
    (evidence/'source-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    return inputs[0]


def inspect_gettext_archive(compressed, exact=True):
    if len(compressed) > 10721600:
        raise ValueError('Compressed archive too large')
    with lzma.open(io.BytesIO(compressed), 'rb') as expanded:
        tar_bytes = expanded.read(256*1024*1024+1)
    if len(tar_bytes) > 256*1024*1024:
        raise ValueError('Expanded tar exceeds bound before member discovery')
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode='r:') as archive:
        members = []
        for member in archive:
            members.append(member)
            if len(members) > 9346:
                raise ValueError('Too many entries')
        seen = set(); total = 0; files = 0; dirs = 0
        for member in members:
            p = PurePosixPath(member.name)
            if (not p.parts or p.is_absolute() or '..' in p.parts or
                    p.parts[0] != 'gettext-1.0' or str(p) in seen or
                    member.name.rstrip('/') != str(p)):
                raise ValueError('Unsafe or duplicate source path')
            seen.add(str(p))
            if member.mode & ~0o777 or not (member.isfile() or member.isdir()):
                raise ValueError('Special mode, link or file kind denied')
            if member.isfile():
                files += 1; total += member.size
                if member.size < 0 or member.size > 40*1024*1024 or total > 256*1024*1024:
                    raise ValueError('Expanded source exceeds bounds')
            else:
                dirs += 1
        if exact and (files, dirs, total) != (9038, 308, 247291870):
            raise ValueError('Exact official source vector differs')
        return members


def run_owned_gettext_phase(vector, cwd, env, logfile, seconds):
    """Finite actual process. Any failure/timeout/log overflow prevents next phase.

    Reaps direct child and bounds process-group cleanup; no native-family/ECHILD claim.
    """
    logfile = Path(logfile)
    if not logfile.parent.resolve().is_relative_to(OWNED_ROOT):
        raise ValueError('Owned log required')
    process = None; reader = None; total = 0; reason = None; code = None
    started = time.monotonic()
    with logfile.open('xb') as output:
        try:
            process = subprocess.Popen(vector, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            reader = selectors.DefaultSelector(); reader.register(process.stdout, selectors.EVENT_READ)
            deadline = started + seconds
            while reader.get_map():
                if time.monotonic() >= deadline:
                    reason = 'TIMEOUT'; break
                for key, _ in reader.select(min(0.1, max(0, deadline-time.monotonic()))):
                    raw = os.read(key.fileobj.fileno(), 65536)
                    if not raw:
                        reader.unregister(key.fileobj); continue
                    total += len(raw)
                    if total > 2*1024*1024:
                        reason = 'LOG_LIMIT'; break
                    output.write(raw)
                if reason: break
            if not reason:
                try: code = process.wait(timeout=max(0.01, deadline-time.monotonic()))
                except subprocess.TimeoutExpired: reason = 'TIMEOUT'
        finally:
            if process is not None:
                if process.poll() is None or reason:
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        process.wait(timeout=2)
                # A reaped leader may leave the group alive; send final bounded kill.
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                if process.stdout: process.stdout.close()
            if reader is not None: reader.close()
    return {'command': vector, 'exit_code': code if code is not None else process.returncode,
            'reason': reason, 'passed': reason is None and code == 0,
            'seconds': time.monotonic()-started, 'log_bytes': logfile.stat().st_size,
            'log_sha256': hashlib.sha256(logfile.read_bytes()).hexdigest()}


def inspect_msgfmt_dependencies(binary, prefix, env):
    before = snapshot_owned_tool(binary, native=True)
    observed = subprocess.run(['/usr/bin/ldd', str(binary)], env=env, capture_output=True, timeout=30)
    if observed.returncode or observed.stderr:
        raise ValueError('Actual native dependency resolution failed')
    dependencies = {}
    for line in observed.stdout.decode('ascii').splitlines():
        line = line.strip()
        if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)', line): continue
        match = re.fullmatch(r'(?:[^\s]+ => )?(/[^\s]+) \(0x[0-9a-f]+\)', line)
        if match is None:
            raise ValueError('Unknown or unresolved shared library')
        path = Path(match[1]); resolved = path.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in (Path(prefix), Path('/usr/lib'), Path('/lib'), Path('/lib64'))):
            raise ValueError('Unapproved shared library location')
        dependencies[str(path)] = snapshot_owned_tool(path)
    if not dependencies or before != snapshot_owned_tool(binary, native=True):
        raise ValueError('Missing dependencies or executable drift')
    return dependencies


def read_message_catalog(path):
    raw = Path(path).read_bytes()
    if len(raw) < 28 or len(raw) > 2*1024*1024:
        raise ValueError('Bounded MO required')
    if raw[:4] == b'\xde\x12\x04\x95': endian = '<'
    elif raw[:4] == b'\x95\x04\x12\xde': endian = '>'
    else: raise ValueError('Bad MO magic')
    _, revision, count, originals, translations, _, _ = struct.unpack_from(endian+'7I', raw)
    if revision != 0 or count > 100 or originals + 8*count > len(raw) or translations + 8*count > len(raw):
        raise ValueError('Bad MO table')
    result = {}
    for i in range(count):
        strings = []
        for table in (originals, translations):
            length, offset = struct.unpack_from(endian+'2I', raw, table+8*i)
            if offset+length >= len(raw) or raw[offset+length] != 0:
                raise ValueError('Bad MO string bounds')
            strings.append(raw[offset:offset+length].decode('utf-8'))
        if strings[0] in result: raise ValueError('Duplicate MO key')
        result[strings[0]] = strings[1]
    return result


def verify_real_msgfmt(binary, prefix, evidence, env):
    binary = Path(binary); prefix = Path(prefix); evidence = Path(evidence)
    if binary != prefix/'bin/msgfmt' or not prefix.resolve().is_relative_to(OWNED_ROOT):
        raise ValueError('Exact genuine owned prefix executable required')
    before = snapshot_owned_tool(binary, native=True)
    deps = inspect_msgfmt_dependencies(binary, prefix, env)
    version = subprocess.run([str(binary), '--version'], env=env, capture_output=True, timeout=30)
    if version.returncode or version.stderr or not version.stdout.startswith(b'msgfmt (GNU gettext-tools) 1.0\n'):
        raise ValueError('Genuine GNU1.0 version failed')
    po = evidence/'known.po'; mo = evidence/'known.mo'; bad = evidence/'malformed.po'
    po.write_text('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: fr\\n"\n\nmsgid "hello"\nmsgstr "bonjour é"\n', encoding='utf-8')
    bad.write_text('msgid "unterminated\nmsgstr "no"\n')
    good = subprocess.run([str(binary),'--check','--output-file='+str(mo),str(po)],env=env,capture_output=True,timeout=30)
    negative = subprocess.run([str(binary),'--check','--output-file='+str(evidence/'invalid.mo'),str(bad)],env=env,capture_output=True,timeout=30)
    if good.returncode or negative.returncode == 0 or read_message_catalog(mo).get('hello') != 'bonjour é':
        raise ValueError('Actual PO/MO usability or negative control failed')
    if before != snapshot_owned_tool(binary, native=True) or deps != inspect_msgfmt_dependencies(binary,prefix,env):
        raise ValueError('msgfmt executable/dependency drift')
    return {'binary':before,'dependencies':deps,'version_exit':version.returncode,
            'good_PO_exit':good.returncode,'malformed_PO_exit':negative.returncode,
            'actual_MO_sha256':hashlib.sha256(mo.read_bytes()).hexdigest()}


def prepare_owned_gettext(archive, signature, keyring, destination, execute=False):
    destination = Path(destination)
    if destination.parent.resolve() != destination.parent or not destination.parent.is_relative_to(OWNED_ROOT):
        raise ValueError('Literal private owned workspace required')
    destination.mkdir(mode=0o700)
    runtime = {p:snapshot_owned_tool(p) for p in TOOLS}
    compressed = verify_gettext_source(archive,signature,keyring,destination/'authentication')
    members = inspect_gettext_archive(compressed)
    source_parent = destination/'source'; source_parent.mkdir(mode=0o700)
    source_before = {}
    # A seekable plain tar avoids repeated xz re-decompression in sorted order.
    with lzma.open(io.BytesIO(compressed),'rb') as expanded:
        plain_tar=expanded.read(256*1024*1024+1)
    if len(plain_tar)>256*1024*1024:raise ValueError('Expanded tar exceeds bound')
    with tarfile.open(fileobj=io.BytesIO(plain_tar),mode='r:') as tar:
        for member in sorted(members,key=lambda m:(not m.isdir(),m.name)):
            path=source_parent/member.name
            if member.isdir(): path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                raw=tar.extractfile(member).read(member.size+1)
                if len(raw)!=member.size:raise ValueError('Actual source member length differs')
                descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(descriptor,'wb') as stream:stream.write(raw)
                path.chmod(member.mode);os.utime(path,(member.mtime,member.mtime))
        for member in sorted((m for m in members if m.isdir()),key=lambda m:len(m.name),reverse=True):
            path=source_parent/member.name;path.chmod(member.mode);os.utime(path,(member.mtime,member.mtime))
    source=source_parent/'gettext-1.0';prefix=destination/'owned-prefix'
    for member in members:
        path=source_parent/member.name
        if member.isfile():source_before[member.name]=snapshot_owned_tool(path)
        else:
            info=path.lstat()
            source_before[member.name]={'directory':True,'mode':info.st_mode,
                'device':info.st_dev,'inode':info.st_ino}
    home=destination/'home';home.mkdir(mode=0o700)
    temporary=destination/'tmp';temporary.mkdir(mode=0o700)
    env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C','LC_ALL':'C','TZ':'UTC',
         'CC':'/usr/bin/cc','CXX':'/usr/bin/c++','AR':'/usr/bin/ar',
         'RANLIB':'/usr/bin/ranlib','NM':'/usr/bin/nm','STRIP':'/usr/bin/strip','TMPDIR':str(temporary)}
    vectors=[(['./configure','--prefix='+str(prefix)],120),(['/usr/bin/make','-j2','all'],480),(['/usr/bin/make','install'],60)]
    result={'status':'PREPARED_NOT_EXECUTED','SOURCE_EXECUTION':False,'OWNED_INSTALL':False,
            'HOST_INSTALL':False,'SUT_runs':0,'GitV3_runs':0,'RC_qualification':False,
            'commands':vectors,'phases':[],'original_source_entries':len(source_before),'runtime_before':runtime}
    try:
        if execute:
            result['SOURCE_EXECUTION']=True
            for i,(vector,seconds) in enumerate(vectors):
                if {p:snapshot_owned_tool(p) for p in TOOLS} != runtime:
                    raise ValueError('Original runtime drift before source phase')
                if prefix.is_symlink() or prefix.resolve() != prefix:
                    raise ValueError('Owned prefix redirected before source phase')
                phase=run_owned_gettext_phase(vector,source,env,destination/f'phase-{i}.log',seconds)
                result['phases'].append(phase)
                if {p:snapshot_owned_tool(p) for p in TOOLS} != runtime:
                    raise ValueError('Original runtime drift after source phase')
                if not phase['passed']:result['status']='FAIL';break
            else:
                result['msgfmt']=verify_real_msgfmt(prefix/'bin/msgfmt',prefix,destination,env)
                installed={}
                for path in prefix.rglob('*'):
                    if path.is_symlink():
                        target=path.resolve(strict=True)
                        if not target.is_relative_to(prefix):raise ValueError('Installed link escapes owned prefix')
                        installed[str(path.relative_to(prefix))]={'link':os.readlink(path),'payload':snapshot_owned_tool(target)}
                    elif path.is_file():installed[str(path.relative_to(prefix))]=snapshot_owned_tool(path)
                    elif not path.is_dir():raise ValueError('Installed special file denied')
                result.update(status='OWNED_PREPARATION_SUCCESS',OWNED_INSTALL=True,installed_inventory=installed)
    except BaseException as primary:
        result.update(status='FAIL_EXCEPTION',error_type=type(primary).__name__,OWNED_INSTALL=False)
        raise
    finally:
        # Includes final real GNU version/PO/MO/dependency commands before this lease.
        source_after={}
        for name,row in source_before.items():
            path=source_parent/name
            try:
                if row.get('directory'):
                    info=path.lstat();source_after[name]={'directory':stat.S_ISDIR(info.st_mode),
                        'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino}
                else:source_after[name]=snapshot_owned_tool(path)
            except (OSError,ValueError) as observation:
                source_after[name]={'identity_error':type(observation).__name__}
        result['original_source_unchanged']=source_before==source_after
        result['runtime_after']={}
        for p in TOOLS:
            try:result['runtime_after'][p]=snapshot_owned_tool(p)
            except (OSError,ValueError) as observation:
                result['runtime_after'][p]={'identity_error':type(observation).__name__}
        result['runtime_unchanged']=runtime==result['runtime_after']
        if not result['original_source_unchanged'] or not result['runtime_unchanged']:
            result.update(status='FAIL_IDENTITY',OWNED_INSTALL=False)
        (destination/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
