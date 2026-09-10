"""Run the real native acceptance as an ephemeral STANDARD Windows account.

CI-only. Credentials remain in this parent process; never argv, env or artifacts.
No production code, runtime security flags or existing accounts are changed.
The OS loads the new user's profile and provides an ordinary logon token.
"""
from __future__ import annotations
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

spec = importlib.util.spec_from_file_location('native_token_v22', Path(__file__).with_name('Windows非提升进程v12.py'))
medium = importlib.util.module_from_spec(spec)
spec.loader.exec_module(medium)
CONTEXT = ('GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID')
NAME = re.compile(r'ctmcpv22_[0-9a-f]{10}')
SID = re.compile(r'S-1-5-21-(?:[0-9]+-){3}[0-9]+')


def require_ci() -> None:
    if (sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
        or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
        or os.environ.get('GITHUB_REPOSITORY') != 'Eswink/coding-tools-mcp'):
        raise RuntimeError('only this repository disposable Windows runner is supported')


def inside(path: Path, root: Path) -> Path:
    path, root = path.resolve(), root.resolve()
    if path == root or root not in path.parents:
        raise ValueError('path must be strictly inside the owned fixture')
    return path


def owned_account(name: str, sid: str, marker: str, actual: tuple) -> None:
    if (not NAME.fullmatch(name) or not SID.fullmatch(sid)
        or not marker.startswith('coding-tools-native-v22:') or actual != (name, sid, marker)):
        raise RuntimeError('refusing to delete or reuse an account not created by this fixture')


class UserInfo1(c.Structure):
    _fields_ = [('name', w.LPWSTR), ('password', w.LPWSTR), ('age', w.DWORD),
        ('priv', w.DWORD), ('home', w.LPWSTR), ('comment', w.LPWSTR),
        ('flags', w.DWORD), ('script', w.LPWSTR)]


class UserInfo23(c.Structure):
    _fields_ = [('name', w.LPWSTR), ('full_name', w.LPWSTR), ('comment', w.LPWSTR),
        ('flags', w.DWORD), ('sid', c.c_void_p)]


class AccountApi(medium.Api):
    def __init__(self):
        super().__init__()
        self.net = c.WinDLL('netapi32', use_last_error=True)
        self.userenv = c.WinDLL('userenv', use_last_error=True)
        def bind(dll, name, result, args):
            fn = getattr(dll, name); fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)
        ptr = c.c_void_p
        bind(self.net, 'NetUserAdd', w.DWORD, [w.LPCWSTR, w.DWORD, ptr, c.POINTER(w.DWORD)])
        bind(self.net, 'NetUserGetInfo', w.DWORD, [w.LPCWSTR, w.LPCWSTR, w.DWORD, c.POINTER(ptr)])
        bind(self.net, 'NetUserDel', w.DWORD, [w.LPCWSTR, w.LPCWSTR])
        bind(self.net, 'NetApiBufferFree', w.DWORD, [ptr])
        bind(self.net, 'NetLocalGroupAddMembers', w.DWORD, [w.LPCWSTR, w.LPCWSTR, w.DWORD, ptr, w.DWORD])
        bind(self.adv, 'ConvertSidToStringSidW', w.BOOL, [ptr, c.POINTER(ptr)])
        bind(self.adv, 'LookupAccountSidW', w.BOOL, [w.LPCWSTR, ptr, w.LPWSTR, c.POINTER(w.DWORD), w.LPWSTR, c.POINTER(w.DWORD), c.POINTER(w.DWORD)])
        bind(self.adv, 'LogonUserW', w.BOOL, [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(w.HANDLE)])
        bind(self.adv, 'CreateProcessWithTokenW', w.BOOL, [w.HANDLE, w.DWORD, w.LPCWSTR, w.LPWSTR, w.DWORD, ptr, w.LPCWSTR, c.POINTER(medium.Startup), c.POINTER(medium.ProcessInfo)])
        bind(self.userenv, 'GetUserProfileDirectoryW', w.BOOL, [w.HANDLE, w.LPWSTR, c.POINTER(w.DWORD)])
        bind(self.userenv, 'DeleteProfileW', w.BOOL, [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR])

    @staticmethod
    def net_check(code: int, operation: str) -> None:
        if code: raise OSError(code, operation + ' failed')

    def sid_text(self, pointer) -> str:
        text = c.c_void_p()
        self.check(self.ConvertSidToStringSidW(pointer, c.byref(text)))
        try: return c.wstring_at(text)
        finally: self.LocalFree(text)

    def identity(self, name: str) -> tuple:
        buffer = c.c_void_p()
        self.net_check(self.NetUserGetInfo(None, name, 23, c.byref(buffer)), 'NetUserGetInfo')
        try:
            value = c.cast(buffer, c.POINTER(UserInfo23)).contents
            return value.name, self.sid_text(value.sid), value.comment
        finally: self.NetApiBufferFree(buffer)

    def add_users_group(self, sid_text: str) -> None:
        builtin, member = c.c_void_p(), c.c_void_p()
        try:
            self.check(self.ConvertStringSidToSidW('S-1-5-32-545', c.byref(builtin)))
            self.check(self.ConvertStringSidToSidW(sid_text, c.byref(member)))
            name, domain = c.create_unicode_buffer(256), c.create_unicode_buffer(256)
            size, domain_size, use = w.DWORD(256), w.DWORD(256), w.DWORD()
            self.check(self.LookupAccountSidW(None, builtin, name, c.byref(size), domain, c.byref(domain_size), c.byref(use)))
            # Level 0 consists of a pointer to the new account SID, not a name.
            code = self.NetLocalGroupAddMembers(None, name.value, 0, c.byref(member), 1)
            if code != 1378: self.net_check(code, 'NetLocalGroupAddMembers')
        finally:
            if builtin: self.LocalFree(builtin)
            if member: self.LocalFree(member)


def grant(path: Path, sid: str, access: str) -> None:
    if not SID.fullmatch(sid) or access not in ('(OI)(CI)(RX)', '(OI)(CI)(M)', '(RX)'):
        raise ValueError('invalid scoped fixture ACL')
    result = subprocess.run(['icacls', str(path), '/grant', f'*{sid}:{access}'],
        capture_output=True, timeout=30)
    if result.returncode: raise RuntimeError('scoped fixture ACL could not be granted')


def copy_sources(root: Path) -> dict:
    origin = Path(__file__).resolve().parent
    target = root / 'source' / 'scripts'; target.mkdir(parents=True)
    hashes = {}
    for path in sorted(origin.glob('*.py')):
        if path.is_symlink(): raise ValueError('test source symlinks are not permitted')
        raw = path.read_bytes()
        (target / path.name).write_bytes(raw)
        hashes['scripts/' + path.name] = hashlib.sha256(raw).hexdigest()
    package = origin.parent / 'package.json'
    (target.parent / package.name).write_bytes(package.read_bytes())
    hashes[package.name] = hashlib.sha256(package.read_bytes()).hexdigest()
    return hashes


def verify_sources(root: Path, hashes: dict) -> None:
    if not isinstance(hashes, dict) or not 1 <= len(hashes) <= 300:
        raise ValueError('invalid test-source inventory')
    for name, digest in hashes.items():
        path = inside(root / name, root)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('test source changed')


def child(manifest: Path) -> int:
    # No account creation or elevation is performed in this branch.
    if sys.platform != 'win32': raise RuntimeError('Windows required')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    root = manifest.parent.resolve()
    if not (root / '.standard-account-fixture-v22').is_file(): raise RuntimeError('missing fixture marker')
    api = AccountApi(); token = w.HANDLE()
    try:
        api.check(api.OpenProcessToken(api.GetCurrentProcess(), 0x0008, c.byref(token)))
        state = api.token_state(token)
        if not medium.use_normal_user_process(state, medium.token_has_restrictions(api, token)):
            raise RuntimeError('the test host must be a genuine unrestricted standard user')
    finally:
        if token: api.CloseHandle(token)
    if os.environ.get('USERNAME', '').casefold() != data['account'].casefold():
        raise RuntimeError('unexpected profile identity')
    for key in CONTEXT: os.environ[key] = data['context'][key]
    require_ci()
    state_root = inside(root / 'state', root)
    os.environ['RUNNER_TEMP'] = str(state_root)
    os.environ['PATH'] = data['path']
    os.environ['PYTHONUTF8'] = '1'; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['GITHUB_WORKSPACE'] = str(root / 'source')
    verify_sources(root / 'source', data['source_hashes'])
    output = state_root / 'evidence'; output.mkdir()
    work = state_root / 'work'; work.mkdir()
    (work / '.chat-native-fixture-v8').touch()
    args = data['arguments']
    if hashlib.sha256(Path(args['executable']).read_bytes()).hexdigest() != data['binary_sha256']:
        raise RuntimeError('native executable bytes changed')
    argv = ['聊天授权原生验收v6.py', '--executable', args['executable'], '--driver', args['driver'],
        '--kind', args['kind'], '--source', args['source'], '--output', str(output), '--fixture-root', str(work)]
    with (state_root / '标准用户执行v22.log').open('w', encoding='utf-8', buffering=1) as stream:
        originals = sys.stdout, sys.stderr, sys.argv
        sys.stdout, sys.stderr, sys.argv = stream, stream, argv
        try:
            runpy.run_path(str(root / 'source' / 'scripts' / argv[0]), run_name='__main__')
            return 0
        except SystemExit as error:
            return 0 if error.code in (None, 0) else 1
        except BaseException:
            traceback.print_exc(limit=20)
            return 1
        finally:
            sys.stdout, sys.stderr, sys.argv = originals


def run(args) -> None:
    require_ci()
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', args.source) or args.source != os.environ.get('GITHUB_SHA'):
        raise ValueError('exact source identity required')
    executable, driver = args.executable.resolve(strict=True), args.driver.resolve(strict=True)
    repository = Path(os.environ['GITHUB_WORKSPACE']).resolve()
    for path in (executable, driver):
        if not any(parent in path.parents for parent in (repository, temporary)) or path.is_symlink():
            raise ValueError('only owned CI binaries may be executed')
    output = args.output.resolve()
    if not any(parent in output.parents for parent in (repository, temporary)):
        raise ValueError('evidence output must be inside the CI repository or temporary directory')
    output.mkdir(parents=True, exist_ok=True)
    api = AccountApi()
    root = Path(tempfile.mkdtemp(prefix='chat-standard-v22-', dir=temporary))
    (root / '.standard-account-fixture-v22').touch()
    (root / 'state').mkdir()
    token = w.HANDLE(); process = None
    name = 'ctmcpv22_' + secrets.token_hex(5)
    password = secrets.token_urlsafe(32) + 'Aa1!'
    marker = 'coding-tools-native-v22:' + secrets.token_hex(16)
    created, sid, profile, primary = False, None, None, None
    evidence = {'passed': False, 'source_sha': args.source, 'run_id': os.environ.get('GITHUB_RUN_ID'),
        'genuine_standard_account': False, 'account_deleted': False, 'profile_deleted': False,
        'owned_processes_closed': False, 'credentials_scan_completed': False, 'credentials_found': None, 'sandbox_disabled': False}
    try:
        hashes = copy_sources(root)
        parameter = w.DWORD()
        info = UserInfo1(name, password, 0, 1, None, marker, 0x201, None)
        api.net_check(api.NetUserAdd(None, 1, c.byref(info), c.byref(parameter)), 'NetUserAdd')
        created = True
        actual = api.identity(name); sid = actual[1]
        owned_account(name, sid, marker, actual)
        api.add_users_group(sid)
        api.check(api.LogonUserW(name, '.', password, 2, 0, c.byref(token)))
        if not medium.use_normal_user_process(api.token_state(token), medium.token_has_restrictions(api, token)):
            raise RuntimeError('Windows did not issue an ordinary standard-user logon token')
        evidence['genuine_standard_account'] = True
        evidence['account_sid_sha256'] = hashlib.sha256(sid.encode()).hexdigest()
        grant(root, sid, '(OI)(CI)(RX)')
        grant(root / 'state', sid, '(OI)(CI)(M)')
        grant(executable, sid, '(RX)'); grant(driver, sid, '(RX)')
        data = {'account': name, 'source_hashes': hashes, 'context': {k:os.environ[k] for k in CONTEXT},
            'path': os.environ['PATH'], 'binary_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
            'arguments': {'executable':str(executable), 'driver':str(driver), 'kind':args.kind, 'source':args.source}}
        manifest = root / '启动上下文v22.json'
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        command = c.create_unicode_buffer(subprocess.list2cmdline([sys.executable,
            str(root / 'source' / 'scripts' / Path(__file__).name), '--child-manifest', str(manifest)]))
        startup = medium.Startup(); startup.cb = c.sizeof(startup)
        # NULL desktop: the OS inherits the caller desktop and grants this user
        # access (CreateProcessWithTokenW contract); no manual DACL broadening.
        info_process = medium.ProcessInfo()
        job = api.check(api.CreateJobObjectW(None, None))
        try:
            limits = medium.Limits(); limits.basic.flags = 0x2000
            api.check(api.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
            # This API implicitly creates a NEW_CONSOLE; DETACHED_PROCESS conflicts.
            # Keep SUSPENDED ownership and profile-created Unicode environment.
            api.check(api.CreateProcessWithTokenW(token, 1, sys.executable, command,
                0x4 | 0x400, None, str(root), c.byref(startup), c.byref(info_process)))
            # Own before resume; any failure terminates this still-suspended process.
            api.check(api.AssignProcessToJobObject(job, info_process.process))
            process = medium.OwnedProcess(api, info_process, job, {'standard_account': True})
            job = None
            length = w.DWORD(32768); path = c.create_unicode_buffer(length.value)
            api.check(api.GetUserProfileDirectoryW(token, path, c.byref(length)))
            profile = Path(path.value)
            if profile.name.casefold() != name.casefold(): raise RuntimeError('unexpected new account profile path')
            if api.ResumeThread(info_process.thread) == 0xffffffff: raise c.WinError(c.get_last_error())
        finally:
            if info_process.thread: api.CloseHandle(info_process.thread)
            if job:
                api.CloseHandle(job)
                if info_process.process:
                    api.TerminateProcess(info_process.process, 1); api.CloseHandle(info_process.process)
        code = process.wait(480)
        evidence['native_exit_code'] = code
        verify_sources(root / 'source', hashes)
        if code != 0: raise RuntimeError('standard-user native acceptance failed; inspect collected evidence')
        evidence['passed'] = True
    except BaseException as error:
        primary = error
        evidence['failure_type'] = type(error).__name__
    finally:
        failures = []
        if process:
            try: process.terminate_tree(); evidence['owned_processes_closed'] = True
            except BaseException as error: failures.append(type(error).__name__)
        if token: api.CloseHandle(token)
        try:
            evidence_dir = root / 'state' / 'evidence'
            candidates = list(evidence_dir.iterdir()) if evidence_dir.is_dir() else []
            log = root / 'state' / '标准用户执行v22.log'
            if log.is_file(): candidates.append(log)
            for file in candidates:
                if not file.is_file() or file.is_symlink() or file.stat().st_size > 8 * 1024 * 1024:
                    raise RuntimeError('unexpected evidence entry')
                raw = file.read_bytes()
                if password.encode() in raw or password.encode('utf-16-le') in raw:
                    evidence['credentials_found'] = True
                    raise RuntimeError('credential canary in evidence; not copying')
            evidence['credentials_scan_completed'] = True
            evidence['credentials_found'] = False
            for file in candidates: shutil.copyfile(file, output / file.name)
        except BaseException as error: failures.append(type(error).__name__)
        if created:
            try:
                actual = api.identity(name)
                sid = sid or actual[1]
                owned_account(name, sid, marker, actual)
                # Remove only ACEs for this new, identity-checked SID on the two
                # explicit CI binaries. No pre-existing account or broad ACL.
                for file in (executable, driver):
                    try:
                        code = subprocess.run(['icacls', str(file), '/remove:g', '*' + sid],
                            capture_output=True, timeout=30).returncode
                        if code: failures.append('FixtureAceRemovalFailed')
                    except BaseException as error: failures.append(type(error).__name__)
                try:
                    for attempt in range(4):
                        if api.DeleteProfileW(sid, None, None): break
                        error_code = c.get_last_error()
                        if error_code in (2, 3) and (profile is None or not profile.exists()): break
                        if attempt == 3: raise c.WinError(error_code)
                        time.sleep(0.5)
                    evidence['profile_deleted'] = True
                except BaseException as error: failures.append(type(error).__name__)
                finally:
                    # Profile cleanup failure must not leave a reusable account.
                    api.net_check(api.NetUserDel(None, name), 'NetUserDel')
                    evidence['account_deleted'] = True
            except BaseException as error: failures.append(type(error).__name__)
        try: shutil.rmtree(root)
        except BaseException as error: failures.append(type(error).__name__)
        if failures:
            evidence['passed'] = False; evidence['cleanup_errors'] = failures
        (output / '标准用户隔离结果v22.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        if primary is not None: raise primary
        if failures: raise RuntimeError('standard-user fixture cleanup failed')


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == '--child-manifest':
        raise SystemExit(child(Path(sys.argv[2])))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--kind', choices=('native','nsis'), required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture-root', type=Path)  # retained CLI compatibility; private fixture is created here
    run(parser.parse_args())


if __name__ == '__main__': main()
