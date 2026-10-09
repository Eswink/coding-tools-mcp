"""Source-only bounded owned Git preparation. Genuine phases are root-only.

No CLI, sudo, package installer, global LD environment, shim or system writes.
Trusted workspace, not a hostile same-UID sandbox or publisher authorization.
Default execute=False stops before Git make/install. Ordinary mocks are not gates.
"""
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import selectors
import shlex
import signal
import stat
import subprocess
import tarfile
import time
import types

OWNED_ROOT=Path('/workspace/work/rc070/publisher-supplementary-git-research/v3')
DEB_SOURCE=Path('/workspace/work/rc070/publisher-debian-msgfmt-research/v3/owned_debian_msgfmt_prepare.py')
DEB_SHA='382f47e98cb5e782e4080f781ba930a42a265a5d83250507199045b1d28ba0aa'
SOURCE_SHA='457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357'
SIGN_SHA='8673501946204c38ebfed09603c1f3a041ed8d12b31f0aa06a474d41e359e254'
KEY_SHA='fd2809d850e844b614ac60f13ded554c55d9052e5c799a5814abcba2a68a063c'
PRIMARY='96E07AF25771955980DAD10020D04E5A713660A7'
SUBKEY='E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB'
MAX_TAR=64*1024*1024
MAX_INSTALL=256*1024*1024
MAKEFILE_SHA='65b2ea79f25b46f191005fe7bb228c3fcc78d7066000c43926dcdb2004a8aae7'
TOOLCHAIN=Path('/workspace/work/rc070/windows-tools/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/bin')
CARGO_SHA='da77c8b33849312255ccde3179198ada4c8deb370488d050286146b1d1b27e14'
RUSTC_SHA='859254978c0a0402c32f949f6de0d99aee73be8d15f45aac00ae1448aac51e74'
SOURCE5=('owned_git_prepare_v3.py','owned_git_prepare_v3_tests.py',*(f'docs/specs/issue88-owned-native-git-build-v3/{name}.md' for name in ('requirements','design','tasks')))
PREFIX_FLAGS=['--no-pager','--no-replace-objects','--no-optional-locks','--no-lazy-fetch',
 '-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','core.untrackedCache=false',
 '-c','credential.helper=','-c','protocol.allow=never']


def load_reviewed_git_dependencies():
    # Bootstrap reads exact dependency source via one actual returned FD; never
    # infer ownership from a path/inode or fdopen handoff. No pycache writes.
    descriptor=None;primary=None;raw=bytearray()
    try:
        descriptor=os.open(DEB_SOURCE,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):raise ValueError('Regular adapter source required')
        while len(raw)<=65536:
            chunk=os.read(descriptor,min(65536,65537-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=DEB_SHA:
            raise ValueError('Frozen resource adapter source mismatch')
    except BaseException as error:primary=error;raise
    finally:
        if descriptor is not None:
            # Local UNKNOWN after this one attempt; no retry even on cancellation.
            try:os.close(descriptor)
            except BaseException as cleanup:
                if primary is not None:raise BaseExceptionGroup('Adapter primary and close failures',[primary,cleanup])
                raise
    module=types.ModuleType('exact_reviewed_debian_v3_adapter')
    exec(compile(bytes(raw),str(DEB_SOURCE),'exec'),module.__dict__)
    return module


def verify_git_source(archive,signature,public_key,evidence):
    m=load_reviewed_git_dependencies();inputs=[]
    for path,digest,size in ((archive,SOURCE_SHA,8177180),(signature,SIGN_SHA,566),(public_key,KEY_SHA,68820)):
        path=Path(path)
        if path.is_symlink():raise ValueError('Source input symlink denied')
        raw=m.owned_debian_file_io(path,read_limit=size+1)
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Official source/sign/key bytes differ')
        inputs.append(raw)
    evidence=Path(evidence)
    if evidence.parent.resolve()!=evidence.parent or not evidence.parent.is_relative_to(OWNED_ROOT):raise ValueError('Literal owned evidence parent required')
    evidence.mkdir(mode=0o700);home=evidence/'public-key-home';home.mkdir(mode=0o700);keyring=home/'pinned-public-key.gpg'
    before=m.snapshot_debian_tool('/usr/bin/gpg')
    decoded=subprocess.run(['/usr/bin/gpg','--homedir',str(home),'--batch','--no-options','--no-autostart','--output',str(keyring),'--dearmor',str(public_key)],capture_output=True,timeout=30)
    if len(decoded.stdout)+len(decoded.stderr)>2*1024*1024:raise ValueError('GPG log cap')
    m.owned_debian_file_io(evidence/'dearmor.stderr',data=decoded.stderr)
    if decoded.returncode:raise ValueError('Pinned public-key dearmor failed')
    decoder=lzma.LZMADecompressor(memlimit=128*1024*1024);tar_bytes=decoder.decompress(inputs[0],max_length=MAX_TAR+1)
    if len(tar_bytes)>MAX_TAR or not decoder.eof or decoder.unused_data:raise ValueError('Complete bounded original tar required')
    observed=subprocess.run(['/usr/bin/gpg','--homedir',str(home),'--batch','--no-options','--no-autostart','--no-auto-key-retrieve','--no-default-keyring','--keyring',str(keyring),'--status-fd','1','--verify',str(signature),'-'],input=tar_bytes,capture_output=True,timeout=30)
    if len(observed.stdout)+len(observed.stderr)>2*1024*1024:raise ValueError('GPG log cap')
    m.owned_debian_file_io(evidence/'developer.status',data=observed.stdout);m.owned_debian_file_io(evidence/'developer.stderr',data=observed.stderr)
    rows=[line.split() for line in observed.stdout.decode('ascii').splitlines()]
    valid=[r for r in rows if len(r)>=12 and r[:2]==['[GNUPG:]','VALIDSIG']]
    bad={'BADSIG','ERRSIG','EXPKEYSIG','EXPSIG','REVKEYSIG','KEYEXPIRED','SIGEXPIRED','NO_PUBKEY','FAILURE'}
    if observed.returncode or len(valid)!=1 or valid[0][2]!=SUBKEY or valid[0][-1]!=PRIMARY or any(len(r)>1 and r[1] in bad for r in rows):raise ValueError('Original developer signature refused')
    if m.snapshot_debian_tool('/usr/bin/gpg')!=before:raise ValueError('GPG runtime drift')
    m.owned_debian_file_io(evidence/'source-identity.json',data=json.dumps({'source_sha256':SOURCE_SHA,'source_bytes':8177180,'tar_bytes':len(tar_bytes),'tar_sha256':hashlib.sha256(tar_bytes).hexdigest(),'primary_fingerprint':PRIMARY,'subkey_fingerprint':SUBKEY,'gpg_exit':observed.returncode,'INSTALL':False,'SUT_runs':0,'trust':'Pinned original official signing identity, not publishergrant'},indent=2)+'\n')
    return tar_bytes


def extract_owned_git_source(tar_bytes,destination):
    m=load_reviewed_git_dependencies();destination=Path(destination)
    if destination.parent.resolve()!=destination.parent or not destination.parent.is_relative_to(OWNED_ROOT):raise ValueError('Literal fresh owned source destination required')
    if len(tar_bytes)>MAX_TAR:raise ValueError('Tar bound')
    with m.owned_debian_resource(tarfile.open(fileobj=io.BytesIO(tar_bytes),mode='r:')) as archive:
        members=archive.getmembers();paths=set();links=set();total=0
        if len(members)>10000:raise ValueError('Source entry cap')
        for member in members:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='git-2.55.0' or str(path) in paths:raise ValueError('Source prefix/path/duplicate denied')
            paths.add(str(path))
            if member.issym():
                target=posixpath.normpath(posixpath.join(str(path.parent),member.linkname))
                if PurePosixPath(member.linkname).is_absolute() or not target.startswith('git-2.55.0/'):raise ValueError('Escaped source link')
                links.add(str(path))
            elif not (member.isfile() or member.isdir()):raise ValueError('Source special/hardlink denied')
            if member.isfile():
                total+=member.size
                if member.size<0 or member.size>8*1024*1024 or total>MAX_TAR:raise ValueError('Source member cap')
        if any(str(parent) in links for name in paths for parent in PurePosixPath(name).parents):raise ValueError('Source underneath link')
        destination.mkdir(mode=0o700)
        for member in sorted(members,key=lambda x:(not x.isdir(),x.name)):
            path=destination/member.name
            if member.isdir():path.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                path.parent.mkdir(parents=True,exist_ok=True)
                with m.owned_debian_resource(archive.extractfile(member)) as stream:raw=stream.read(member.size+1)
                if len(raw)!=member.size:raise ValueError('Source member length differs')
                m.owned_debian_file_io(path,data=raw);path.chmod(member.mode&0o755)
        for member in members:
            if member.issym():
                path=destination/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(member.linkname)
    source=destination/'git-2.55.0';manifest=snapshot_original_git_source(source)
    m.owned_debian_file_io(destination/'SOURCE-MANIFEST.json',data=json.dumps(manifest,indent=2)+'\n')
    return source


def snapshot_original_git_source(source,expected=None,installed=False):
    m=load_reviewed_git_dependencies();source=Path(source)
    if source.resolve()!=source or not source.is_dir() or not source.is_relative_to(OWNED_ROOT):raise ValueError('Literal owned source/prefix required')
    names=sorted(expected) if expected is not None else sorted(p.relative_to(source).as_posix() for p in source.rglob('*'))
    if len(names)>10000:raise ValueError('Inventory cap')
    result={};total=0;inodes={};counts={};linkcounts={}
    for name in names:
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or str(relative)!=name:raise ValueError('Inventory path escapes or is not canonical')
        path=source/name;info=path.lstat();row={'mode':info.st_mode,'device':info.st_dev,'inode':info.st_ino}
        if path.is_symlink():
            row['link']=os.readlink(path)
            if installed and not path.resolve(strict=True).is_relative_to(source):raise ValueError('Installed link escapes owned prefix')
        elif stat.S_ISREG(info.st_mode):
            key=(info.st_dev,info.st_ino);fields=(info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink)
            if info.st_size>(MAX_TAR if installed else 8*1024*1024):raise ValueError('Member byte cap')
            if not installed or key not in inodes:
                total+=info.st_size
                if total>(MAX_INSTALL if installed else MAX_TAR):raise ValueError('Aggregate unique payload cap')
                lease=m.snapshot_debian_tool(path);inodes[key]=(fields,lease['sha256'])
            if fields!=inodes[key][0]:raise ValueError('Owned hardlink identity drift')
            row.update(bytes=info.st_size,sha256=inodes[key][1])
            if installed:
                row['link_count']=info.st_nlink;counts[key]=counts.get(key,0)+1;linkcounts[key]=info.st_nlink
        elif not stat.S_ISDIR(info.st_mode):raise ValueError('Source/prefix kind denied')
        result[name]=row
    if installed and counts!=linkcounts:raise ValueError('Installed hardlink count escapes prefix')
    # Inode is only observed data topology within a trusted owned prefix; it never
    # grants native owner/FD authority. At least one actual byte read per payload.
    return result


def verify_native_build_toolchain(evidence):
    m=load_reviewed_git_dependencies();evidence=Path(evidence)
    if evidence.parent.resolve()!=evidence.parent or not evidence.parent.is_relative_to(OWNED_ROOT):raise ValueError('Literal fresh owned tool evidence')
    evidence.mkdir(mode=0o700);home=evidence/'build-home';home.mkdir(mode=0o700);cargo_home=evidence/'cargo-home';cargo_home.mkdir(mode=0o700)
    env={'PATH':str(TOOLCHAIN)+':/usr/bin:/bin','RUSTC':str(TOOLCHAIN/'rustc'),'CARGO_HOME':str(cargo_home),'HOME':str(home),'LANG':'C','LC_ALL':'C','TZ':'UTC'}
    if TOOLCHAIN.resolve()!=TOOLCHAIN or not TOOLCHAIN.is_dir():raise ValueError('Literal real existing toolchain directory required')
    # The allowed real Rust directory must not shadow original host command roles.
    for host in m.HOST_TOOLS:
        candidate=TOOLCHAIN/Path(host).name
        if candidate.exists() or candidate.is_symlink():raise ValueError('Toolchain shadows original host command')
    paths=(*m.HOST_TOOLS,str(TOOLCHAIN/'cargo'),str(TOOLCHAIN/'rustc'));before={p:m.snapshot_debian_tool(p) for p in paths};versions=[]
    for name,digest in (('cargo',CARGO_SHA),('rustc',RUSTC_SHA)):
        path=TOOLCHAIN/name;lease=m.snapshot_debian_tool(path,native=True)
        if lease['sha256']!=digest:raise ValueError('Real original compiler exacthash differs')
        phase=subprocess.run([str(path),'--version'],env=env,capture_output=True,timeout=30)
        if len(phase.stdout)+len(phase.stderr)>2*1024*1024 or phase.returncode or not phase.stdout.decode('ascii').startswith(name+' 1.98.1 '):raise ValueError('Exact actual compiler version failed')
        versions.append({'path':str(path),'exit':phase.returncode,'stdout':phase.stdout.decode('ascii'),'stderr_sha256':hashlib.sha256(phase.stderr).hexdigest()})
    after={p:m.snapshot_debian_tool(p) for p in paths}
    if after!=before:raise ValueError('Compiler/system runtime drift')
    result={'passed':True,'runtime':before,'build_env':env,'versions':versions,'INSTALL':False,'SUT_runs':0}
    m.owned_debian_file_io(evidence/'tool-predicate.json',data=json.dumps(result,indent=2)+'\n');return result


def validate_msgfmt_assignment(receipt_path):
    m=load_reviewed_git_dependencies();receipt_path=Path(receipt_path)
    if receipt_path.parent.resolve()!=receipt_path.parent or not receipt_path.parent.is_relative_to(m.ROOT):raise ValueError('Current owned msgfmt result required')
    result=json.loads(m.owned_debian_file_io(receipt_path,read_limit=2*1024*1024+1,decode=True))
    if result.get('status')!='PASS_OWNED_MSGFMT_ONLY' or result.get('OWNED_EXTRACTION') is not True or result.get('HOST_INSTALL') is not False or result.get('PACKAGE_INSTALL') is not False or not all(result.get(k) is True for k in ('original_runtime_unchanged','owned_data_unchanged','native_final_unchanged')):raise ValueError('Actual complete msgfmt PASS required; not a grant')
    phases=result.get('phases',[])
    if len(phases)!=3 or any(p.get('reason') is not None for p in phases) or any(p.get('passed') is not True or p.get('exit')!=0 for p in phases[:2]) or type(phases[2].get('exit')) is not int or phases[2]['exit']==0:raise ValueError('Exact GNU version/positive/negative phases required')
    vector=phases[0].get('command',[])
    if len(vector)!=5 or vector[-1]!='--version' or vector[1]!='--library-path':raise ValueError('Exact genuine loader argv required')
    native=result['native'];base=vector[:4]
    if base[0]!=native['loader']['resolved'] or base[3]!=native['binary']['path'] or native.get('original_interpreter')!='/lib64/ld-linux-x86-64.so.2' or not native.get('dependencies') or not native.get('NEEDED') or not native.get('version_requirements'):raise ValueError('Complete original native lease inventory required')
    if m.snapshot_debian_tool(base[3],native=True)!=native['binary'] or m.snapshot_debian_tool(native['loader']['path'])!=native['loader']:raise ValueError('Current binary/loader drift')
    if Path(base[3]).resolve()!=Path(base[3]) or not Path(base[3]).is_relative_to(m.ROOT):raise ValueError('Literal owned msgfmt payload')
    dirs=base[2].split(':')
    if not dirs or not all(Path(d).resolve()==Path(d) and Path(d).is_dir() and Path(d).is_relative_to(receipt_path.parent/'packages') for d in dirs):raise ValueError('Literal owned package library dirs')
    if set(native['preloaded_host_libraries'])!=set(m.HOST_LIBRARIES):raise ValueError('Original fourABI set required')
    leases=[native['binary'],native['loader'],*native['dependencies'].values(),*native['preloaded_host_libraries'].values()]
    for lease in leases:
        if m.snapshot_debian_tool(lease['path'])!=lease:raise ValueError('Current actual dependency/ABI drift')
    if any(not isinstance(value,str) or re.search(r'[\s$`\x00\r\n]',value) for value in base):raise ValueError('Make/shell expansion unsafe')
    if any(phase['command'][:4]!=base for phase in phases):raise ValueError('All actual usability vectors must share identity')
    # CLI make variable overrides upstream +=, so keep original --check explicitly.
    assignment='MSGFMT='+shlex.join([*base,'--check'])
    return {'assignment':assignment,'vector':base,'leases':leases,'receipt_lease':m.snapshot_debian_tool(receipt_path),'receipt_path':str(receipt_path)}


def validate_owned_install_prefix(prefix):
    prefix=Path(prefix)
    if prefix.parent.resolve()!=prefix.parent or not prefix.parent.is_relative_to(OWNED_ROOT) or prefix.exists() or prefix.is_symlink():raise ValueError('Fresh literal workspace-only prefix required')
    if re.search(r'[\s$`\x00\r\n]',str(prefix)):raise ValueError('Unsafe make prefix expansion')
    return prefix


def run_owned_git_phase(vector,cwd,env,logfile,seconds,source_guard=None):
    m=load_reviewed_git_dependencies();logfile=Path(logfile)
    if logfile.parent.resolve()!=logfile.parent or not logfile.parent.is_relative_to(OWNED_ROOT) or not 0<seconds<=480 or 'LD_LIBRARY_PATH' in env or 'LD_PRELOAD' in env:raise ValueError('Bounded owned phase/no global loaderenv')
    if source_guard is not None:
        if set(source_guard)!=set(SOURCE5):raise ValueError('Exact five-source guard required')
        for name,lease in source_guard.items():
            if m.snapshot_debian_tool(OWNED_ROOT/name)!=lease:raise ValueError('Current helper source drift before native delegate')
    process=None;reader=None;reason=None;code=None;total=0;start=time.monotonic();primary=None
    with m.owned_debian_resource(logfile,'xb') as output:
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
        except BaseException as error:primary=error;raise
        finally:
            errors=[]
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
                except BaseException as error:errors.append(error)
                try:
                    if process.stdout:process.stdout.close()
                except BaseException as error:errors.append(error)
            try:
                if reader is not None:reader.close()
            except BaseException as error:errors.append(error)
            if errors:raise BaseExceptionGroup('Gitphase primary and cleanup failures',([primary] if primary is not None else [])+errors)
    return {'command':vector,'exit':code if code is not None else process.returncode,'reason':reason,'passed':not reason and code==0,'seconds':time.monotonic()-start,'log_bytes':logfile.stat().st_size,'log_sha256':hashlib.sha256(m.owned_debian_file_io(logfile,read_limit=2*1024*1024+1)).hexdigest()}


def prepare_owned_git_v3(archive,signature,public_key,evidence,msgfmt_receipt,execute=False,current_source5=None):
    m=load_reviewed_git_dependencies();evidence=Path(evidence)
    if evidence.parent.resolve()!=evidence.parent or not evidence.parent.is_relative_to(OWNED_ROOT):raise ValueError('Literal fresh owned evidence')
    evidence.mkdir(mode=0o700);prefix=validate_owned_install_prefix(evidence/'owned-prefix')
    result={'status':'PREPARED_NOT_EXECUTED','INSTALL':'NOTRUN','TOOL_INSTALL_ATTEMPTED':False,'HOST_INSTALL':False,'PRODUCT_INSTALL':'NOTRUN','SUT_runs':0,'RC_qualification':False,'build_runs':0,'install_runs':0,'phases':[]};runtime={p:m.snapshot_debian_tool(p) for p in (*m.HOST_TOOLS,*m.HOST_LIBRARIES,str(TOOLCHAIN/'cargo'),str(TOOLCHAIN/'rustc'))};msgfmt=None;primary=None;installed=None;source=None;source_before=None
    try:
        tar_bytes=verify_git_source(archive,signature,public_key,evidence/'source-auth')
        source=extract_owned_git_source(tar_bytes,evidence/'source')
        source_before=snapshot_original_git_source(source)
        if hashlib.sha256(m.owned_debian_file_io(source/'Makefile',read_limit=1024*1024)).hexdigest()!=MAKEFILE_SHA:raise ValueError('Original Makefile changed')
        if not execute:return result
        if current_source5 is None or set(current_source5)!=set(SOURCE5):raise ValueError('Root current-source5 startup lease required')
        for name,lease in current_source5.items():
            if m.snapshot_debian_tool(OWNED_ROOT/name)!=lease:raise ValueError('Root current source5 drift')
        msgfmt=validate_msgfmt_assignment(msgfmt_receipt)
        tools=verify_native_build_toolchain(evidence/'prebuild-tools');runtime.update(tools['runtime']);env=tools['build_env']
        if snapshot_original_git_source(source,source_before)!=source_before:raise ValueError('Original source drift before build')
        if validate_msgfmt_assignment(msgfmt_receipt)!=msgfmt:raise ValueError('Current msgfmt drift before build')
        if {p:m.snapshot_debian_tool(p) for p in runtime}!=runtime:raise ValueError('Runtime drift before build')
        vector=['/usr/bin/timeout','--signal=TERM','--kill-after=2s','480s','/usr/bin/make','-j2','prefix='+str(prefix),msgfmt['assignment'],'all']
        result['build_runs']=1;phase=run_owned_git_phase(vector,source,env,evidence/'actual-build.log',480,source_guard=current_source5);result['phases'].append(phase)
        if not phase['passed']:raise ValueError('Original fullmake failed; partial ELF unqualified')
        if snapshot_original_git_source(source,source_before)!=source_before:raise ValueError('Original source drift after build')
        if {p:m.snapshot_debian_tool(p) for p in runtime}!=runtime or validate_msgfmt_assignment(msgfmt_receipt)!=msgfmt:raise ValueError('Runtime/msgfmt drift before install')
        build_binary=m.snapshot_debian_tool(source/'git',native=True)
        validate_owned_install_prefix(prefix)
        result.update(TOOL_INSTALL_ATTEMPTED=True,INSTALL='ATTEMPTED_OR_FAILED',install_runs=1)
        install=['/usr/bin/timeout','--signal=TERM','--kill-after=2s','60s','/usr/bin/make','-j2','prefix='+str(prefix),msgfmt['assignment'],'install']
        phase=run_owned_git_phase(install,source,env,evidence/'actual-install.log',60,source_guard=current_source5);result['phases'].append(phase)
        if not phase['passed']:raise ValueError('Full owned install failed')
        installed=snapshot_original_git_source(prefix,installed=True)
        git=prefix/'bin/git';binary=m.snapshot_debian_tool(git,native=True)
        if (binary['sha256'],binary['stat']['st_size'])!=(build_binary['sha256'],build_binary['stat']['st_size']):raise ValueError('Installed Git differs from actual fullbuild binary')
        if not (prefix/'libexec/git-core').is_dir() or not (prefix/'share/git-core/templates').is_dir() or not (prefix/'share/locale').is_dir():raise ValueError('Full installed helpers/templates/locales required')
        source_correspondence={}
        for relative,row in installed.items():
            if 'sha256' not in row:continue
            parts=PurePosixPath(relative).parts;candidate=None
            if len(parts)==3 and parts[:2]==('libexec','git-core'):candidate=source/parts[2]
            elif parts[:2]==('share','locale'):candidate=source/'po/build/locale'/Path(*parts[2:])
            elif parts[:3]==('share','git-core','templates'):candidate=source/'templates/blt'/Path(*parts[3:])
            elif parts[:2]==('share','perl5'):candidate=source/'perl/build/lib'/Path(*parts[2:])
            if candidate is not None and candidate.is_file():
                observed=m.snapshot_debian_tool(candidate)
                if observed['sha256']!=row['sha256']:raise ValueError('Installed helper/resource differs from actual build artifact')
                source_correspondence[relative]={'bytes':row['bytes'],'sha256':row['sha256']}
        repo=evidence/'ordinary-install-probe';repo.mkdir(mode=0o700);started=time.monotonic()
        commands=[[str(git),*PREFIX_FLAGS,'--version'],[str(git),*PREFIX_FLAGS,'--exec-path'],[str(git),*PREFIX_FLAGS,'init','--bare',str(repo/'probe.git')],[str(git),*PREFIX_FLAGS,'-C',str(repo/'probe.git'),'hash-object','--stdin']]
        for i,command in enumerate(commands):
            if {p:m.snapshot_debian_tool(p) for p in runtime}!=runtime or validate_msgfmt_assignment(msgfmt_receipt)!=msgfmt:raise ValueError('Current runtime/msgfmt changed before installed probe')
            if snapshot_original_git_source(prefix,installed,installed=True)!=installed:raise ValueError('Full installed prefix drift')
            remaining=30-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('Shared installed native probe deadline')
            # hash-object uses /dev/null through explicit stdin, no user data.
            if i==3:command=[str(git),*PREFIX_FLAGS,'-C',str(repo/'probe.git'),'hash-object','/dev/null']
            phase=run_owned_git_phase(command,evidence,env,evidence/f'installed-{i}.log',remaining,source_guard=current_source5);result['phases'].append(phase)
            if not phase['passed']:raise ValueError('Actual installed Git probe failed')
        version=m.owned_debian_file_io(evidence/'installed-0.log',read_limit=2*1024*1024+1)
        execpath=m.owned_debian_file_io(evidence/'installed-1.log',read_limit=2*1024*1024+1,decode=True).strip()
        oid=m.owned_debian_file_io(evidence/'installed-3.log',read_limit=2*1024*1024+1).strip()
        if version!=b'git version 2.55.0\n' or Path(execpath)!=prefix/'libexec/git-core' or oid!=b'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391':raise ValueError('Exact installed fullflags/version/plumbing identity failed')
        result.update(status='PASS_OWNED_GIT_BUILD_INSTALL_ONLY',INSTALL=True,built_binary=build_binary,installed_binary=binary,installed_manifest=installed,installed_corresponding_build_artifacts=source_correspondence)
    except BaseException as error:primary=error;result.update(status='FAIL',error_type=type(error).__name__,error=str(error));raise
    finally:
        errors=[];unchanged=True
        for path,lease in runtime.items():
            try:
                if m.snapshot_debian_tool(path)!=lease:unchanged=False;errors.append(ValueError('Original tool runtime drift'))
            except BaseException as error:unchanged=False;errors.append(error)
        if source_before is not None:
            try:
                if snapshot_original_git_source(source,source_before)!=source_before:unchanged=False;errors.append(ValueError('Original source changed'))
            except BaseException as error:unchanged=False;errors.append(error)
        if current_source5 is not None:
            for name,lease in current_source5.items():
                try:
                    if name not in SOURCE5 or m.snapshot_debian_tool(OWNED_ROOT/name)!=lease:unchanged=False;errors.append(ValueError('Current helper source changed'))
                except BaseException as error:unchanged=False;errors.append(error)
        if msgfmt is not None:
            try:
                if validate_msgfmt_assignment(msgfmt_receipt)!=msgfmt:unchanged=False;errors.append(ValueError('Current msgfmt changed'))
            except BaseException as error:unchanged=False;errors.append(error)
        if installed is not None:
            try:
                if snapshot_original_git_source(prefix,installed,installed=True)!=installed:unchanged=False;errors.append(ValueError('Full installed prefix changed'))
            except BaseException as error:unchanged=False;errors.append(error)
        # Re-read the complete installed namespace too; an added file must deny.
        if installed is not None:
            try:
                if snapshot_original_git_source(prefix,installed=True)!=installed:unchanged=False;errors.append(ValueError('Installed namespace changed'))
            except BaseException as error:unchanged=False;errors.append(error)
        result['source_runtime_msgfmt_prefix_final_unchanged']=unchanged
        if not unchanged:result['status']='FAIL_FINAL_LEASE'
        try:m.owned_debian_file_io(evidence/'actual-build-install-result.json',data=json.dumps(result,indent=2)+'\n')
        except BaseException as error:errors.append(error)
        if errors:raise BaseExceptionGroup('Gitpreparation primary and final failures',([primary] if primary is not None else [])+errors)
    return result
