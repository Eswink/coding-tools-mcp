"""Bounded workspace data preparation; genuine downloaded ELF needs root review.

No CLI, package installer, Git build, host writes, global loader env or shim.
Default execute=False authenticates and extracts data only. A private trusted
workspace is assumed: this is not an OS write sandbox or hostile same-UID guard.
"""
import contextlib
import email.utils
import hashlib
import io
import json
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

ROOT = Path('/workspace/work/rc070/publisher-debian-msgfmt-research')
INRELEASE_SHA = '77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa'
PACKAGES_SHA = '9e0b5aabb2465b3d2e7a7fe27f9913846277833f7a2826e7767acccff5b588c5'
EXPANDED_SHA = '515e692f2c4121c6fcec444ef100cc18f79a991910615f3a88c8b7becfc94d2f'
KEY_SHA = '506b815cbb32d9b6066b4a2aa524071e071761e7e7f68c3ac74f3061ba852017'
ANCHORS = {'B8B80B5B623EAB6AD8775C45B7C5D7D6350947F8',
           '4D64FEC119C2029067D6E791F8D2585B8783D481'}
SELECTED = ('gettext', 'gettext-base', 'libgomp1', 'libunistring2',
            'libxml2', 'libicu72', 'liblzma5', 'zlib1g')
HOST_TOOLS = ('/usr/bin/git', '/usr/bin/cc', '/usr/bin/make', '/usr/bin/gpg',
              '/usr/bin/python3', '/usr/bin/openssl', '/usr/bin/timeout',
              '/bin/sh', '/usr/bin/ar', '/usr/bin/ranlib', '/usr/bin/readelf',
              '/usr/bin/ldd', '/usr/bin/c++', '/usr/bin/nm', '/usr/bin/strip')
HOST_LIBRARIES = ('/lib/x86_64-linux-gnu/libc.so.6', '/lib/x86_64-linux-gnu/libm.so.6',
                  '/usr/lib/x86_64-linux-gnu/libstdc++.so.6', '/lib/x86_64-linux-gnu/libgcc_s.so.1')


class _OwnedDebianFile:
    """Known returned native FD only; failed close remains UNKNOWN, never retried.

    No fdopen handoff, descriptor-reuse inference or native authority is issued.
    This is finite trusted-workspace IO, not a same-UID adversary boundary.
    """
    def __init__(self, path, mode):
        if mode not in ('rb', 'xb'):
            raise ValueError('Only bounded read or exclusive new write allowed')
        self.state = 'UNOPENED'; self._fd = None; self.unknown_fd = None
        flags = os.O_RDONLY if mode == 'rb' else os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= os.O_NOFOLLOW | os.O_CLOEXEC
        # Assignment owns only an actual successfully returned os.open descriptor.
        self._fd = os.open(path, flags, 0o600); self.state = 'OPEN'
        try:
            if not stat.S_ISREG(os.fstat(self._fd).st_mode):
                raise ValueError('Regular native file required')
        except BaseException as primary:
            try: self.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup('FD constructor primary and close failures', [primary, cleanup])
            raise

    def read(self, count):
        if self.state != 'OPEN' or not isinstance(count, int) or not 0 <= count <= 128*1024*1024+1:
            raise ValueError('Open file and bounded byte count required')
        result = bytearray()
        while len(result) < count:
            chunk = os.read(self._fd, min(65536, count-len(result)))
            if not chunk: break
            result.extend(chunk)
        return bytes(result)

    def write(self, raw):
        if self.state != 'OPEN' or not isinstance(raw, bytes) or len(raw) > 128*1024*1024:
            raise ValueError('Open file and bounded byte payload required')
        view = memoryview(raw); offset = 0
        while offset < len(view):
            count = os.write(self._fd, view[offset:])
            if count <= 0: raise OSError('Native write made no progress')
            offset += count
        return offset

    def close(self):
        if self.state != 'OPEN':
            raise ValueError('Close already attempted; UNKNOWN is not retried')
        descriptor = self._fd
        # Record uncertainty BEFORE invoking a close that may fail or cancel.
        self._fd = None; self.unknown_fd = descriptor; self.state = 'UNKNOWN'
        os.close(descriptor)
        self.unknown_fd = None; self.state = 'CLOSED'


@contextlib.contextmanager
def owned_debian_resource(resource, mode=None):
    """Always attempt one close, retaining exact primary and close objects."""
    if mode is not None: resource = _OwnedDebianFile(resource, mode)
    primary = None
    try:
        yield resource
    except BaseException as error:
        primary = error
        raise
    finally:
        try: resource.close()
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup('Resource primary and close failures', [primary, cleanup])
            raise


def owned_debian_file_io(path, *, read_limit=None, data=None, decode=False):
    if (read_limit is None) == (data is None):
        raise ValueError('Exactly one bounded read or exclusive write required')
    if read_limit is not None:
        # Existing public registry keyring symlink is read by its literal target.
        # Callers retain their own lexical/target leases where applicable.
        with owned_debian_resource(Path(path).resolve(strict=True), 'rb') as stream:
            raw = stream.read(read_limit)
        return raw.decode('utf-8') if decode else raw
    if isinstance(data, str): data = data.encode('utf-8')
    with owned_debian_resource(path, 'xb') as stream:
        return stream.write(data)


def snapshot_debian_tool(path, native=False):
    path = Path(path); lexical = path.lstat(); resolved = path.resolve(strict=True)
    before = resolved.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if not stat.S_ISREG(before.st_mode) or before.st_size > 128*1024*1024:
        raise ValueError('Bounded regular payload required')
    if native and (path.is_symlink() or not before.st_mode & 0o111):
        raise ValueError('Literal executable regular ELF required')
    raw = owned_debian_file_io(resolved, read_limit=128*1024*1024+1)
    if (len(raw) != before.st_size or resolved != path.resolve() or
        tuple(getattr(before,k) for k in fields) != tuple(getattr(resolved.stat(),k) for k in fields) or
        tuple(getattr(lexical,k) for k in fields) != tuple(getattr(path.lstat(),k) for k in fields)):
        raise ValueError('Payload drift during actual read')
    if native and (raw[:6] != b'\x7fELF\x02\x01' or raw[18:20] != b'\x3e\x00'):
        raise ValueError('Native x86_64 ELF required; wrapper refused')
    return {'path':str(path), 'resolved':str(resolved), 'sha256':hashlib.sha256(raw).hexdigest(),
            'stat':{k:getattr(before,k) for k in fields},
            'lexical':{k:getattr(lexical,k) for k in fields}}


def validate_debian_signature_status(exit_code, raw):
    rows = [line.split() for line in raw.decode('ascii').splitlines()]
    allowed = {'NEWSIG','KEY_CONSIDERED','SIG_ID','GOODSIG','VALIDSIG',
               'TRUST_UNDEFINED','TRUST_MARGINAL','TRUST_FULLY','TRUST_ULTIMATE'}
    if exit_code or any(len(r)<2 or r[0]!='[GNUPG:]' or r[1] not in allowed for r in rows):
        raise ValueError('Bad, expired, revoked or unknown signature denied')
    groups = []; current = []
    for row in rows:
        if row[1]=='NEWSIG':
            if current: groups.append(current)
            current = []
        current.append(row)
    if current: groups.append(current)
    primaries = set()
    for group in groups:
        valid=[r for r in group if r[1]=='VALIDSIG']; good=[r for r in group if r[1]=='GOODSIG']
        if len(valid)!=1 or len(valid[0])!=12 or len(good)!=1 or good[0][2]!=valid[0][2][-16:]:
            raise ValueError('Each signature needs matching GOODSIG/VALIDSIG')
        primaries.add(valid[0][-1])
    if not ANCHORS.issubset(primaries): raise ValueError('Both official bookworm anchors required')
    return {'primaries':sorted(primaries), 'trust':'Official public registry pins; TRUST_UNDEFINED retained, not publisher authority'}


def verify_debian_metadata(inrelease, compressed, keyring, evidence):
    evidence = Path(evidence)
    if evidence.parent.resolve()!=evidence.parent or not evidence.parent.is_relative_to(ROOT):
        raise ValueError('Literal owned evidence parent required')
    inputs=[]
    for path,size,digest in ((inrelease,151075,INRELEASE_SHA),(compressed,8790396,PACKAGES_SHA),(keyring,55918,KEY_SHA)):
        raw=owned_debian_file_io(path, read_limit=size+1)
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Captured source byte pin mismatch')
        inputs.append(raw)
    evidence.mkdir(mode=0o700);home=evidence/'gpg-home';home.mkdir(mode=0o700)
    for name,raw in zip(('InRelease','Packages.xz','keyring.pgp'),inputs):
        owned_debian_file_io(evidence/name, data=raw)
    before=snapshot_debian_tool('/usr/bin/gpg')
    result=subprocess.run(['/usr/bin/gpg','--no-options','--homedir',str(home),'--batch',
        '--no-autostart','--no-auto-key-retrieve','--no-default-keyring','--keyring',str(evidence/'keyring.pgp'),
        '--status-fd','1','--verify',str(evidence/'InRelease')],capture_output=True,timeout=10)
    if len(result.stdout)+len(result.stderr)>2*1024*1024:raise ValueError('GPG log cap')
    owned_debian_file_io(evidence/'signature.status', data=result.stdout);owned_debian_file_io(evidence/'signature.stderr', data=result.stderr)
    identity=validate_debian_signature_status(result.returncode,result.stdout)
    if snapshot_debian_tool('/usr/bin/gpg')!=before:raise ValueError('GPG runtime drift')
    text=inputs[0].decode('ascii')
    if not all(re.search('^'+re.escape(row)+'$',text,re.M) for row in ('Origin: Debian','Codename: bookworm')):
        raise ValueError('Exact Debian release identity required')
    dates=re.findall(r'^Date: (.+)$',text,re.M)
    if len(dates)!=1 or email.utils.parsedate_to_datetime(dates[0]).timestamp()>time.time():
        raise ValueError('Signed date missing, ambiguous or future')
    expiry=re.findall(r'^Valid-Until: (.+)$',text,re.M)
    if len(expiry)>1 or (expiry and email.utils.parsedate_to_datetime(expiry[0]).timestamp()<=time.time()):
        raise ValueError('Declared validity expired or ambiguous')
    sha_section=text.split('\nSHA256:\n',1)[1].split('\n-----BEGIN PGP SIGNATURE-----',1)[0]
    rows=[r.split() for r in sha_section.splitlines() if r.strip()]
    matches=[r for r in rows if len(r)==3 and r[2]=='main/binary-amd64/Packages.xz']
    if matches!=[[PACKAGES_SHA,'8790396','main/binary-amd64/Packages.xz']]:raise ValueError('Exact signed SHA256 row required')
    decoder=lzma.LZMADecompressor(memlimit=128*1024*1024)
    expanded=decoder.decompress(inputs[1],max_length=128*1024*1024+1)
    if not decoder.eof or decoder.unused_data or len(expanded)!=50060337 or hashlib.sha256(expanded).hexdigest()!=EXPANDED_SHA:
        raise ValueError('Exact bounded Packages decode failed')
    identity.update(date=dates[0],valid_until=expiry or None,strict_freshness=False,anti_replay_proven=False)
    return expanded,identity


def select_debian_package(raw, name):
    if name not in SELECTED or len(raw)>128*1024*1024:raise ValueError('Finite package selection only')
    matches=[]
    for stanza in raw.decode('utf-8').split('\n\n'):
        fields={};last=None
        for line in stanza.splitlines():
            if line.startswith((' ','\t')) and last:fields[last]+='\n'+line
            elif ':' in line:
                key,value=line.split(':',1)
                if key in fields:raise ValueError('Duplicate package field')
                fields[key]=value.strip();last=key
            else:raise ValueError('Malformed package stanza')
        if fields.get('Package')==name:matches.append(fields)
    if len(matches)!=1:raise ValueError('Unique exact package required')
    fields=matches[0]
    if fields.get('Architecture')!='amd64' or not re.fullmatch(r'[0-9a-f]{64}',fields.get('SHA256','')):
        raise ValueError('Exact architecture and SHA256 required')
    filename=fields.get('Filename','');path=PurePosixPath(filename)
    if not filename.startswith('pool/main/') or path.is_absolute() or '..' in path.parts or str(path)!=filename:
        raise ValueError('Unsafe official pool filename')
    if not fields.get('Size','').isdigit() or not 0<int(fields['Size'])<=16*1024*1024:
        raise ValueError('Package size cap')
    if name in ('gettext','gettext-base') and fields.get('Version')!='0.21-12':raise ValueError('Exact gettext version required')
    return {k:fields[k] for k in ('Package','Version','Architecture','Filename','Size','SHA256','Depends') if k in fields}


def inspect_debian_ar(raw, record):
    if len(raw)!=int(record['Size']) or hashlib.sha256(raw).hexdigest()!=record['SHA256']:
        raise ValueError('Actual .deb size/hash differs from signed record')
    if not raw.startswith(b'!<arch>\n'):raise ValueError('Bad ar header')
    entries={};offset=8
    while offset<len(raw):
        header=raw[offset:offset+60]
        if len(header)!=60 or header[-2:]!=b'`\n':raise ValueError('Truncated ar member')
        name=header[:16].decode('ascii').strip().rstrip('/')
        if name not in ('debian-binary','control.tar.xz','data.tar.xz') or name in entries:
            raise ValueError('Only exact Debian xz members; duplicates/codecs denied')
        size_text=header[48:58].decode('ascii').strip()
        if not size_text.isdigit():raise ValueError('Bad ar size')
        size=int(size_text);offset+=60;data=raw[offset:offset+size]
        if len(data)!=size:raise ValueError('Truncated ar payload')
        entries[name]=data;offset+=size
        if size%2:
            if raw[offset:offset+1]!=b'\n':raise ValueError('Bad ar padding')
            offset+=1
    if set(entries)!= {'debian-binary','control.tar.xz','data.tar.xz'} or entries['debian-binary']!=b'2.0\n':
        raise ValueError('Complete exact .deb structure required')
    decoder=lzma.LZMADecompressor(memlimit=128*1024*1024)
    control=decoder.decompress(entries['control.tar.xz'],max_length=2*1024*1024+1)
    if len(control)>2*1024*1024 or not decoder.eof or decoder.unused_data:raise ValueError('Bounded complete control tar required')
    with owned_debian_resource(tarfile.open(fileobj=io.BytesIO(control),mode='r:')) as tar:
        controls=[member for member in tar if member.name in ('control','./control')]
        if len(controls)!=1 or not controls[0].isfile() or controls[0].size>128*1024:raise ValueError('Unique regular control record required')
        with owned_debian_resource(tar.extractfile(controls[0])) as stream:
            text=stream.read(128*1024+1).decode('utf-8')
        for key in ('Package','Version','Architecture'):
            values=re.findall('^'+key+': ([^\n]+)$',text,re.M)
            if values!=[record[key]]:raise ValueError('Package control identity differs from signed record')
    return entries


def extract_owned_debian_data(entries, destination, totals, deadline=None):
    destination=Path(destination)
    if destination.parent.resolve()!=destination.parent or not destination.parent.is_relative_to(ROOT):
        raise ValueError('Literal fresh owned data root required')
    deadline=time.monotonic()+60 if deadline is None else deadline;plain=[]
    for key,cap in (('control.tar.xz',2*1024*1024),('data.tar.xz',128*1024*1024)):
        decoder=lzma.LZMADecompressor(memlimit=128*1024*1024)
        raw=decoder.decompress(entries[key],max_length=cap+1)
        if len(raw)>cap or not decoder.eof or decoder.unused_data:raise ValueError('Bounded complete tar decode required')
        plain.append(raw)
    # Control is data inspected only: scripts are never materialized/executed.
    for raw,is_data in zip(plain,(False,True)):
        with owned_debian_resource(tarfile.open(fileobj=io.BytesIO(raw),mode='r:')) as tar:
            members=[];seen=set();symlinks={}
            for m in tar:
                members.append(m)
                name=m.name
                if name.startswith('./'):name=name[2:]
                if name in ('','.') and m.isdir():continue
                path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or str(path)!=name.rstrip('/') or str(path) in seen:
                    raise ValueError('Unsafe or duplicate archive path')
                seen.add(str(path));m.name=str(path)
                if m.mode & ~0o777 or not (m.isfile() or m.isdir() or (is_data and m.issym())):
                    raise ValueError('Special kind/hardlink/mode denied')
                if m.isfile():
                    if m.size<0 or m.size>64*1024*1024:raise ValueError('Member cap')
                    if is_data:totals['bytes']+=m.size
                if is_data:totals['entries']+=1
                if totals['bytes']>128*1024*1024 or totals['entries']>10000:raise ValueError('Aggregate extraction cap')
                if m.issym():
                    link=PurePosixPath(m.linkname)
                    if link.is_absolute():raise ValueError('Absolute package link denied')
                    # Canonicalize without touching host; require later in-root regular target.
                    parts=list(path.parent.parts)
                    for part in link.parts:
                        if part=='..':
                            if not parts:raise ValueError('Escaped package link')
                            parts.pop()
                        elif part!='.':parts.append(part)
                    symlinks[str(path)]='/'.join(parts)
                if time.monotonic()>deadline:raise TimeoutError('Extraction deadline')
            for m in members:
                if m.name in ('','.'):continue
                if any(parent.as_posix() in symlinks for parent in PurePosixPath(m.name).parents):
                    raise ValueError('Symlink archive parent denied')
            if not is_data:continue
            destination.mkdir(mode=0o700);manifest={}
            for m in sorted(members,key=lambda x:(not x.isdir(),x.name)):
                if m.name in ('','.'):continue
                path=destination/m.name
                if m.isdir():path.mkdir(parents=True,exist_ok=True)
                elif m.isfile():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with owned_debian_resource(tar.extractfile(m)) as stream:payload=stream.read(m.size+1)
                    if len(payload)!=m.size:raise ValueError('Member byte length differs')
                    owned_debian_file_io(path, data=payload)
                    path.chmod(m.mode);manifest[m.name]=snapshot_debian_tool(path)
                if time.monotonic()>deadline:raise TimeoutError('Extraction deadline')
            for link,target in symlinks.items():
                resolved=destination/target
                member=next(m for m in members if m.name==link)
                if destination.name=='libgomp1' and link=='usr/share/doc/libgomp1' and member.linkname=='gcc-12-base' and target=='usr/share/doc/gcc-12-base':
                    # One observed authenticated package documentation entry is
                    # dangling without gcc-base data. Preserve bytes/topology;
                    # it is never a loader dir or native dependency admission.
                    path=destination/link;path.parent.mkdir(parents=True,exist_ok=True);os.symlink(member.linkname,path)
                    info=path.lstat()
                    manifest[link]={'documentation_DATA_only':True,'link':member.linkname,'canonical_owned_target':target,
                        'lexical':{k:getattr(info,k) for k in ('st_dev','st_ino','st_mode','st_mtime_ns','st_ctime_ns')}}
                    continue
                if not resolved.is_file() or resolved.is_symlink() or not resolved.resolve().is_relative_to(destination):
                    raise ValueError('Link needs literal in-root regular target')
                path=destination/link;path.parent.mkdir(parents=True,exist_ok=True);os.symlink(next(m.linkname for m in members if m.name==link),path)
                manifest[link]={'link':os.readlink(path),'target_sha256':hashlib.sha256(owned_debian_file_io(resolved, read_limit=64*1024*1024+1)).hexdigest(),'lease':snapshot_debian_tool(path)}
            for m in members:
                if m.isdir() and m.name not in ('','.','./'):
                    path=destination/m.name;path.chmod(m.mode);info=path.lstat()
                    manifest[m.name]={'directory':True,'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino}
            return manifest


def run_debian_phase(vector, cwd, env, logfile, seconds):
    logfile=Path(logfile)
    if not logfile.parent.resolve().is_relative_to(ROOT) or not 0<seconds<=30:
        raise ValueError('Owned bounded native phase required')
    process=None;reader=None;reason=None;code=None;total=0;start=time.monotonic();primary=None
    with owned_debian_resource(logfile, 'xb') as output:
        try:
            process=subprocess.Popen(vector,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            reader=selectors.DefaultSelector();reader.register(process.stdout,selectors.EVENT_READ);deadline=start+seconds
            while reader.get_map():
                if time.monotonic()>=deadline:reason='TIMEOUT';break
                for key,_ in reader.select(min(.1,max(0,deadline-time.monotonic()))):
                    raw=os.read(key.fileobj.fileno(),65536)
                    if not raw:reader.unregister(key.fileobj);continue
                    total+=len(raw)
                    if total>2*1024*1024:reason='LOG_LIMIT';break
                    output.write(raw)
                if reason:break
            if not reason:
                try:code=process.wait(timeout=max(.01,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:reason='TIMEOUT'
        except BaseException as error:
            primary=error;raise
        finally:
            cleanup_errors=[]
            if process is not None:
                try:
                    if process.poll() is None or reason:
                        try:os.killpg(process.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                        try:process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            try:os.killpg(process.pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                            process.wait(timeout=2)
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                except BaseException as error:cleanup_errors.append(error)
                try:
                    if process.stdout:process.stdout.close()
                except BaseException as error:cleanup_errors.append(error)
            try:
                if reader is not None:reader.close()
            except BaseException as error:cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup('Native phase primary and cleanup failures',([primary] if primary is not None else [])+cleanup_errors)
    return {'command':vector,'exit':code if code is not None else process.returncode,'reason':reason,
            'passed':not reason and code==0,'seconds':time.monotonic()-start,
            'log_bytes':logfile.stat().st_size,'log_sha256':hashlib.sha256(owned_debian_file_io(logfile, read_limit=2*1024*1024+1)).hexdigest()}


def verify_debian_runtime(binary, loader, library_dirs, evidence, env, original_runtime, lease_state=None):
    binary=Path(binary);loader=Path(loader);evidence=Path(evidence)
    if not binary.resolve().is_relative_to(ROOT) or binary.is_symlink():raise ValueError('Literal owned binary only')
    before=snapshot_debian_tool(binary,native=True);load=snapshot_debian_tool(loader)
    if lease_state is None:lease_state={}
    lease_state.update(binary=before,loader=load,dependencies={})
    host_libraries={p:snapshot_debian_tool(p) for p in HOST_LIBRARIES}
    lease_state['preloaded_host_libraries']=host_libraries
    real_loader=Path(load['resolved']);snapshot_debian_tool(real_loader,native=True)
    if not real_loader.is_relative_to(Path('/usr/lib')) and not real_loader.is_relative_to(Path('/lib')):
        raise ValueError('Existing genuine host loader only')
    for d in library_dirs:
        d=Path(d)
        if d.resolve()!=d or not d.is_dir() or not d.is_relative_to(ROOT):raise ValueError('Literal owned library dirs only')
    if 'LD_LIBRARY_PATH' in env or 'LD_PRELOAD' in env:raise ValueError('No loader environment injection')
    vector=[str(real_loader),'--library-path',':'.join(map(str,library_dirs)),str(binary)]
    # Static inspection still invokes a preexisting real tool and is in this root-only
    # phase. Version requirements and original interpreter are retained as evidence.
    started=time.monotonic();static=[]
    for i,flags in enumerate((['-W','-l'],['-W','-d'],['-W','--version-info'])):
        if {p:snapshot_debian_tool(p) for p in HOST_TOOLS}!=original_runtime:raise ValueError('Original runtime drift before static inspection')
        remaining=30-(time.monotonic()-started)
        if remaining<=0:raise TimeoutError('Shared native inspection deadline')
        phase=run_debian_phase(['/usr/bin/readelf',*flags,str(binary)],evidence,env,evidence/f'elf-{i}.log',remaining)
        static.append(phase)
        if not phase['passed']:raise ValueError('Actual ELF static inspection failed')
    interpreter=re.findall(r'\[Requesting program interpreter: ([^\]]+)\]',owned_debian_file_io(evidence/'elf-0.log', read_limit=2*1024*1024+1, decode=True))
    if interpreter!=['/lib64/ld-linux-x86-64.so.2'] or Path(interpreter[0]).resolve()!=real_loader:
        raise ValueError('Exact original ELF interpreter identity required')
    needed=re.findall(r'\(NEEDED\).*\[([^\]]+)\]',owned_debian_file_io(evidence/'elf-1.log', read_limit=2*1024*1024+1, decode=True))
    requirements=re.findall(r'Name: ([^\s]+)',owned_debian_file_io(evidence/'elf-2.log', read_limit=2*1024*1024+1, decode=True))
    if not needed or not requirements:raise ValueError('Actual ELF NEEDED and symbol version inventory required')
    remaining=30-(time.monotonic()-started)
    if remaining<=0:raise TimeoutError('Shared native inspection deadline')
    phase=run_debian_phase(vector[:3]+['--list',str(binary)],evidence,env,evidence/'loader-list.log',remaining)
    if not phase['passed']:raise ValueError('Actual loader ABI/dependency resolution failed')
    deps={};names=set()
    for line in owned_debian_file_io(evidence/'loader-list.log', read_limit=2*1024*1024+1, decode=True).splitlines():
        line=line.strip()
        if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)',line):continue
        match=re.fullmatch(r'(?:[^\s]+ => )?(/[^\s]+) \(0x[0-9a-f]+\)',line)
        if not match:raise ValueError('Unknown or unresolved dependency')
        path=Path(match[1]);resolved=path.resolve(strict=True)
        if not any(resolved.is_relative_to(r) for r in (ROOT,Path('/usr/lib'),Path('/lib'),Path('/lib64'))):
            raise ValueError('Unapproved dependency location')
        deps[str(path)]=snapshot_debian_tool(path)
        lease_state['dependencies'][str(path)]=deps[str(path)]
        if not resolved.is_relative_to(ROOT) and resolved!=real_loader and resolved not in {Path(p['resolved']) for p in host_libraries.values()}:
            raise ValueError('Host dependency absent from pre-load identity allowlist')
        names.add(line.split(' => ',1)[0] if ' => ' in line else path.name)
    if not set(needed).issubset(names):raise ValueError('Incomplete actual NEEDED resolution')
    if not deps or before!=snapshot_debian_tool(binary,native=True) or load!=snapshot_debian_tool(loader):
        raise ValueError('Binary/loader missing or changed')
    if {p:snapshot_debian_tool(p) for p in HOST_TOOLS}!=original_runtime:raise ValueError('Original runtime drift after loader')
    if {p:snapshot_debian_tool(p) for p in HOST_LIBRARIES}!=host_libraries:raise ValueError('Host ABI library drift across first load')
    return vector,{'binary':before,'loader':load,'dependencies':deps,'loader_phase':phase,
                   'preloaded_host_libraries':host_libraries,'static_phases':static,'original_interpreter':interpreter[0],
                   'NEEDED':needed,'version_requirements':requirements,
                   'ABI':'Actual loader version resolution exit0 with exact ELF needs; package database installation/status not claimed'}


def read_native_mo(path):
    raw=owned_debian_file_io(path, read_limit=2*1024*1024+1)
    if not 28<=len(raw)<=2*1024*1024:raise ValueError('Bounded MO required')
    endian='<' if raw[:4]==b'\xde\x12\x04\x95' else '>' if raw[:4]==b'\x95\x04\x12\xde' else None
    if not endian:raise ValueError('Bad MO magic')
    _,revision,count,originals,translations,_,_=struct.unpack_from(endian+'7I',raw)
    if revision or count>100 or max(originals,translations)+8*count>len(raw):raise ValueError('Bad MO tables')
    result={}
    for i in range(count):
        values=[]
        for table in (originals,translations):
            length,offset=struct.unpack_from(endian+'2I',raw,table+8*i)
            if offset+length>=len(raw) or raw[offset+length]!=0:raise ValueError('MO string out of bounds')
            values.append(raw[offset:offset+length].decode('utf-8'))
        if values[0] in result:raise ValueError('Duplicate MO key')
        result[values[0]]=values[1]
    return result


def prepare_owned_debian_msgfmt(inrelease, compressed, keyring, packages, destination, execute=False):
    destination=Path(destination)
    if destination.parent.resolve()!=destination.parent or not destination.parent.is_relative_to(ROOT):
        raise ValueError('Literal fresh owned preparation root required')
    if set(packages)!=set(SELECTED):raise ValueError('Exactly eight proposed data packages required')
    destination.mkdir(mode=0o700);runtime={p:snapshot_debian_tool(p) for p in HOST_TOOLS}
    result={'status':'PREPARED_NOT_EXECUTED','OWNED_EXTRACTION':False,'HOST_INSTALL':False,
            'PACKAGE_INSTALL':False,'INSTALL':'NOTRUN','SUT_runs':0,'GitV3_runs':0,
            'RC_qualification':False,'phases':[]}
    manifests={};records={};totals={'entries':0,'bytes':0};native_leases={};primary=None
    try:
        raw,identity=verify_debian_metadata(inrelease,compressed,keyring,destination/'auth');result['metadata']=identity
        records={name:select_debian_package(raw,name) for name in SELECTED}
        if sum(int(r['Size']) for r in records.values())>32*1024*1024:raise ValueError('Aggregate compressed data cap')
        prefixes=destination/'packages';prefixes.mkdir(mode=0o700)
        deadline=time.monotonic()+60
        for name in SELECTED:
            r=records[name]
            payload=owned_debian_file_io(packages[name], read_limit=int(r['Size'])+1)
            manifests[name]=extract_owned_debian_data(inspect_debian_ar(payload,r),prefixes/name,totals,deadline)
        result['OWNED_EXTRACTION']=True;result['package_records']=records;result['totals']=totals
        if execute:
            # Bind all owned executable/library data to authenticated extraction
            # before the first loader or static-inspection delegate, not afterward.
            for name,manifest in manifests.items():
                for member,lease in manifest.items():
                    path=prefixes/name/member
                    if lease.get('documentation_DATA_only'):
                        info=path.lstat();same=path.is_symlink() and os.readlink(path)==lease['link'] and {k:getattr(info,k) for k in lease['lexical']}==lease['lexical']
                    elif 'link' in lease:
                        same=path.is_symlink() and os.readlink(path)==lease['link'] and snapshot_debian_tool(path)==lease['lease']
                    elif lease.get('directory'):
                        info=path.lstat();same=stat.S_ISDIR(info.st_mode) and {'directory':True,'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino}==lease
                    else:same=snapshot_debian_tool(path)==lease
                    if not same:raise ValueError('Authenticated owned package data drift before first native delegate')
            if {p:snapshot_debian_tool(p) for p in HOST_TOOLS}!=runtime:raise ValueError('Original runtime drift before first native delegate')
            home=destination/'home';home.mkdir(mode=0o700);env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C','LC_ALL':'C','TZ':'UTC'}
            library_dirs=[p for n in SELECTED for p in (prefixes/n/'usr/lib/x86_64-linux-gnu',prefixes/n/'lib/x86_64-linux-gnu') if p.is_dir()]
            vector,observed=verify_debian_runtime(prefixes/'gettext/usr/bin/msgfmt',Path('/lib64/ld-linux-x86-64.so.2'),library_dirs,destination,env,runtime,native_leases)
            native_leases.update(observed)
            po=destination/'known.po';bad=destination/'malformed.po';mo=destination/'known.mo'
            owned_debian_file_io(po, data='msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: fr\\n"\n\nmsgid "hello"\nmsgstr "bonjour é"\n')
            owned_debian_file_io(bad, data='msgid "unterminated\nmsgstr "no"\n')
            vectors=[vector+['--version'],vector+['--check','--statistics','--output-file='+str(mo),str(po)],vector+['--check','--output-file='+str(destination/'invalid.mo'),str(bad)]]
            start=time.monotonic()
            for i,command in enumerate(vectors):
                for lease in (native_leases['binary'],native_leases['loader'],*native_leases['dependencies'].values(),*native_leases['preloaded_host_libraries'].values()):
                    if snapshot_debian_tool(lease['path'])!=lease:raise ValueError('Native dependency drift before command')
                if {p:snapshot_debian_tool(p) for p in HOST_TOOLS}!=runtime:raise ValueError('Original runtime drift before native command')
                remaining=30-(time.monotonic()-start)
                if remaining<=0:raise TimeoutError('Shared native usability deadline')
                phase=run_debian_phase(command,destination,env,destination/f'native-{i}.log',remaining)
                result['phases'].append(phase)
                if phase['reason'] or (i<2 and not phase['passed']) or (i==2 and phase['exit']==0):raise ValueError('Actual GNU usability vector failed')
            if not owned_debian_file_io(destination/'native-0.log', read_limit=2*1024*1024+1).startswith(b'msgfmt (GNU gettext-tools) 0.21\n') or read_native_mo(mo).get('hello')!='bonjour é':
                raise ValueError('Genuine GNU0.21 version/MO semantics required')
            result.update(status='PASS_OWNED_MSGFMT_ONLY',native=native_leases,actual_MO_sha256=hashlib.sha256(owned_debian_file_io(mo, read_limit=2*1024*1024+1)).hexdigest())
    except BaseException as error:
        primary=error;result.update(status='FAIL',error_type=type(error).__name__,error=str(error));raise
    finally:
        final_errors=[];unchanged=True;data_unchanged=True;native_unchanged=True
        for p,lease in runtime.items():
            try:unchanged &= snapshot_debian_tool(p)==lease
            except BaseException as error:unchanged=False;final_errors.append(error)
        for name,manifest in manifests.items():
            for member,lease in manifest.items():
                try:
                    path=destination/'packages'/name/member
                    if lease.get('documentation_DATA_only'):
                        info=path.lstat();data_unchanged &= path.is_symlink() and os.readlink(path)==lease['link'] and {k:getattr(info,k) for k in lease['lexical']}==lease['lexical']
                    elif 'link' in lease:
                        data_unchanged &= path.is_symlink() and os.readlink(path)==lease['link'] and snapshot_debian_tool(path)==lease['lease']
                    elif lease.get('directory'):
                        info=path.lstat();data_unchanged &= stat.S_ISDIR(info.st_mode) and {'directory':True,'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino}==lease
                    else:data_unchanged &= snapshot_debian_tool(path)==lease
                except BaseException as error:data_unchanged=False;final_errors.append(error)
        for lease in ([native_leases['binary'],native_leases['loader'],*native_leases['dependencies'].values(),*native_leases.get('preloaded_host_libraries',{}).values()] if native_leases else []):
            try:native_unchanged &= snapshot_debian_tool(lease['path'])==lease
            except BaseException as error:native_unchanged=False;final_errors.append(error)
        result.update(original_runtime_unchanged=unchanged,owned_data_unchanged=data_unchanged,native_final_unchanged=native_unchanged)
        if not (unchanged and data_unchanged and native_unchanged):result['status']='FAIL_RUNTIME_OR_DATA_DRIFT'
        result['final_observation_errors']=[{'type':type(e).__name__,'error':str(e)} for e in final_errors]
        try:owned_debian_file_io(destination/'preparation-result.json', data=json.dumps(result,indent=2)+'\n')
        except BaseException as error:final_errors.append(error)
        if not (unchanged and data_unchanged and native_unchanged) and not final_errors:
            final_errors.append(ValueError('Final runtime/data lease failed'))
        if final_errors:
            # Final observations cannot replace the actual delegate or cancellation
            # object; preserve both in an explicit group when there is a primary.
            raise BaseExceptionGroup('Preparation primary and final observation failures',([primary] if primary is not None else [])+final_errors)
    return result
