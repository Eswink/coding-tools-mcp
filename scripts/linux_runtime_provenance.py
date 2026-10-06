"""Bounded ordinary-user backing-file observations, never a launch or security authority."""
from __future__ import annotations
import argparse
import atexit
import hashlib
import json
import multiprocessing
from multiprocessing.connection import wait as wait_for_worker
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile
import signal
from types import SimpleNamespace
import time
from AppImage入口配置v3 import setup_python_library

SCHEMA = 'linux-runtime-provenance-v1'
MAIN = 'usr/bin/coding-tools-mcp-desktop'
BINDING_KEYS = ('schema', 'profile', 'source_sha', 'source_tree', 'run_id', 'run_attempt',
                'workflow', 'os', 'kind', 'package', 'envelope_sha256', 'artifact_id', 'artifact_digest', 'members', 'python_loader')
LIMITS = dict(processes=128, files=512, maps=1048576, rows=8192, path=4096,
              file_bytes=256*1024**2, hash_bytes=8*1024**3, raw_bytes=128*1024**2,
              evidence_bytes=256*1024**2, seconds=900)
ENV_KEYS = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'LD_BIND_NOW',
            'GIO_EXTRA_MODULES', 'GIO_MODULE_DIR', 'GIO_USE_TLS', 'GIO_USE_VFS',
            'GTK_PATH', 'GTK_MODULES', 'GDK_BACKEND', 'APPIMAGE', 'APPDIR', 'APPIMAGE_EXTRACT_AND_RUN')
FALSE_CLAIMS = dict(atomic_snapshot=False, complete_lifetime_closure=False,
                   tls_runtime_closure=False, official_archive_byte_origin=False,
                   native_linker_consumption_verified=False, retained_glib_code_verified=False,
                   security_approved=False, publish_approved=False)
def require(condition, message):
    if not condition: raise ValueError(message)
def bounded(path, limit):
    with Path(path).open('rb') as stream: raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'read limit')
    return raw
def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key'); result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)
def metadata(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
def process_identity(pid):
    raw = bounded(f'/proc/{pid}/stat', 8192).decode()
    fields = raw[raw.rfind(')') + 2:].split()
    require(len(fields) >= 20, 'invalid process stat')
    if fields[0] == 'Z': raise ProcessLookupError('exited process')
    return dict(pid=pid, start=int(fields[19]), parent=int(fields[1]),
                executable=metadata(os.stat(f'/proc/{pid}/exe')),
                executable_path=os.readlink(f'/proc/{pid}/exe'))
def same_process(first, last):
    return all(first[key] == last[key] for key in ('pid', 'start', 'executable'))
def parse_maps(raw):
    require(len(raw) <= LIMITS['maps'] and raw.endswith(b'\n'), 'truncated or oversized maps')
    rows, end = [], 0
    for line in raw.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]+)-([0-9a-f]+) ([r-][w-][x-][ps]) ([0-9a-f]+) ([0-9a-f]+):([0-9a-f]+) ([0-9]+)(?: +(.*))?', line)
        require(match is not None, 'invalid maps row')
        a, b, perms, offset, major, minor, inode, path = match.groups(); path = path or ''
        a, b = int(a, 16), int(b, 16)
        require(end <= a < b and len(path.encode()) <= LIMITS['path'], 'overlap or path limit')
        end = b
        category = ('deleted' if path.endswith(' (deleted)') else 'ambiguous' if '\\' in path else
                    'kernel' if path.startswith('[') else 'anonymous' if not path else 'file')
        require(category != 'file' or (path.startswith('/') and int(inode) > 0), 'invalid file mapping')
        rows.append(dict(start=a, end=b, permissions=perms, offset=int(offset, 16),
                         device=[int(major, 16), int(minor, 16)], inode=int(inode), path=path, category=category))
        require(len(rows) <= LIMITS['rows'], 'maps row limit')
    require(rows, 'empty maps')
    return rows
def environment_projection(pid=None, environment=None):
    result = {}
    if environment is not None:
        entries = ((key, environment[key]) for key in ENV_KEYS if key in environment)
    else:
        # Stream entries; never retain or export the complete process environment.
        entries = []
        with open(f'/proc/{pid}/environ', 'rb') as stream:
            pending, total = b'', 0
            while chunk := stream.read(4096):
                total += len(chunk); require(total <= 1024**2, 'environment read limit')
                pending += chunk
                while b'\0' in pending:
                    item, pending = pending.split(b'\0', 1)
                    key, _, value = item.partition(b'=')
                    if key.decode(errors='replace') in ENV_KEYS:
                        entries.append((key.decode(), value.decode('utf-8', 'strict')))
                require(len(pending) <= 65536, 'environment entry limit')
            require(not pending, 'truncated environment')
    for key, value in entries:
        require(len(value.encode()) <= 4096 and key not in result, 'environment projection limit')
        result[key] = value
    require(len(json.dumps(result).encode()) <= 16384, 'environment projection limit')
    return result
def validate_environment(launch, observed, package_root, python_loader=None):
    for key in ('LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'GTK_PATH', 'GTK_MODULES', 'GIO_USE_TLS', 'GIO_USE_VFS'):
        require(not launch.get(key) and not observed.get(key), 'loader override present')
    expected = {key:launch.get(key, '') for key in ('LD_LIBRARY_PATH', 'GIO_MODULE_DIR', 'GIO_EXTRA_MODULES')}
    if package_root:
        root = package_root['path']; prefix = root + '/usr/lib:' + root + '/usr/lib/x86_64-linux-gnu'
        expected['LD_LIBRARY_PATH'] = prefix + (':' + expected['LD_LIBRARY_PATH'] if expected['LD_LIBRARY_PATH'] else '')
        expected['GIO_MODULE_DIR'] = expected['GIO_EXTRA_MODULES'] = root + '/usr/lib/x86_64-linux-gnu/gio/modules'
    require(all(observed.get(key, '') == value for key, value in expected.items()), 'loader environment disagreement')
    require(not any(launch.get(k) for k in ('GIO_MODULE_DIR', 'GIO_EXTRA_MODULES')) and launch.get('LD_LIBRARY_PATH', '') in ('', setup_python_library(python_loader)), 'inherited loader override present')
def package_origin(path, identity, binding, package_root=None):
    equivalent = sorted(m['path'] for m in binding['members']
                        if identity['sha256'] == m['sha256'] and identity['size'] == m['size'])
    member = path.lstrip('/') if binding['kind'] == 'deb' else None
    if binding['kind'] == 'appimage' and package_root and path.startswith(package_root['path'] + '/'):
        member = path[len(package_root['path']) + 1:]
        require(identity['identity'][0] == package_root['identity'][0], 'package root device mismatch')
    expected = [m for m in binding['members'] if m['path'] == member]
    if expected:
        require(member in equivalent, 'package member bytes mismatch')
        return dict(kind='package', members=[member], equivalent_members=equivalent)
    if {k: identity[k] for k in ('sha256', 'size')} == binding['package']:
        return dict(kind='outer-package', members=[], equivalent_members=equivalent)
    return dict(kind='system', members=[], equivalent_members=equivalent)
def package_owner(path, phase, deadline=None):
    def query(arguments):
        remaining = 5 if deadline is None else min(5, deadline - time.monotonic())
        require(remaining > 0, 'observation time limit')
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(['/usr/bin/dpkg-query', *arguments], stdout=output, stderr=subprocess.DEVNULL,
                                    env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=remaining)
            require(output.tell() <= 65536, 'dpkg diagnostic limit')
            output.seek(0); return result.returncode, output.read().decode('utf-8', 'strict')
    code, owners = query(['-S', path])
    if code and path.startswith('/usr/'):
        alias = path[4:]
        if os.path.exists(alias) and os.path.samestat(os.stat(alias), os.stat(path)):
            code, owners = query(['-S', alias])
    packages = sorted({line.rsplit(': ', 1)[0] for line in owners.splitlines() if ': ' in line})
    require(code == 0 and 0 < len(packages) <= 8, 'unresolved system owner')
    code, versions = query(['-W', '-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n', *packages])
    require(code == 0 and versions.strip(), 'unresolved system version')
    return dict(phase=phase, ownership=owners, versions=versions, official_archive_byte_origin=False)

class Observer:
    def __init__(self, binding, output, phase, launch_environment=None):
        self.binding, self.output, self.phase = binding, Path(output), phase
        self.errors, self.processes, self.files, self.samples, self.cache = [], {}, {}, [], {}
        self.raw_bytes = self.hash_bytes = self.evidence_bytes = 0
        self.started = time.monotonic(); self.stopped = False; self.commands = 0
        self.worker = self.control = self.process = None; self.finished = False; self.signal_handler = self.pending_signal = None
        self.launch_environment = environment_projection(environment=os.environ if launch_environment is None else launch_environment)

    def fail(self, error):
        code = str(error) if isinstance(error, (str, ValueError)) else type(error).__name__
        if code not in self.errors and len(self.errors) < 128: self.errors.append(code)

    def attach(self, owned_process):
        self.process = owned_process
        try:
            require(owned_process.poll() is None, 'anchor already exited')
            self.anchor = process_identity(owned_process.pid)
            self.processes[owned_process.pid] = self.anchor
            context = multiprocessing.get_context('spawn')
            receiver, self.control = context.Pipe(duplex=False)
            self.worker = context.Process(target=observe_worker, args=(self.binding, self.output, self.phase,
                self.launch_environment, self.anchor, self.started, receiver))
            try: self.worker.start()
            finally: receiver.close()
            os.set_blocking(self.control.fileno(), False)
            if signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
                self.signal_handler = signal.signal(signal.SIGTERM, self._handle_term)
                atexit.register(self._redeliver)
        except Exception as error: self.fail(error)
        return self

    def _handle_term(self, number, frame):
        self.pending_signal = number
        raise SystemExit(128 + number)

    def _redeliver(self):
        if self.pending_signal:
            signal.signal(self.pending_signal, signal.SIG_DFL); os.kill(os.getpid(), self.pending_signal)

    def _discover(self):
        # children is per thread; do not infer ancestry from process names/groups.
        pending = list(self.processes); threads = 0
        while pending:
            require(time.monotonic() - self.started <= LIMITS['seconds'], 'observation time limit')
            pid = pending.pop(0); known = self.processes[pid]
            try:
                current = process_identity(pid)
                require(current['start'] == known['start'], 'PID reused')
                for task in Path(f'/proc/{pid}/task').iterdir():
                    threads += 1; require(threads <= LIMITS['rows'], 'thread discovery limit')
                    for item in bounded(task / 'children', 65536).split():
                        child = int(item)
                        if child in self.processes: continue
                        require(len(self.processes) < LIMITS['processes'], 'process limit')
                        identity = process_identity(child)
                        require(identity['parent'] == pid, 'child ancestry changed')
                        identity['ancestor'] = [pid, known['start']]
                        self.processes[child] = identity; pending.append(child)
            except (FileNotFoundError, ProcessLookupError):
                if not any((sample['before']['pid'], sample['before']['start']) == (pid, known['start']) for sample in self.samples): self.fail('transient process not sampled')
                continue  # Previously sampled descendants remain retained after exit/reparenting.
            except Exception as error: self.fail(error)

    def _file(self, pid, row, package_root=None):
        require(time.monotonic() - self.started <= LIMITS['seconds'], 'observation time limit')
        path = f'/proc/{pid}/root' + row['path']
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor); identity = metadata(before)
            require(stat.S_ISREG(before.st_mode), 'nonregular backing file')
            require([os.major(before.st_dev), os.minor(before.st_dev)] == row['device'] and before.st_ino == row['inode'], 'namespace backing identity mismatch')
            require(before.st_size <= LIMITS['file_bytes'], 'file limit')
            key = ':'.join(map(str, identity))
            if key not in self.cache:
                first = os.read(descriptor, 4)
                if first != b'\x7fELF':
                    require(metadata(os.fstat(descriptor)) == identity, 'non-ELF descriptor changed')
                    return {'category': 'non-ELF', 'identity': identity}
                require(len(self.files) < LIMITS['files'], 'ELF file limit')
                require(self.hash_bytes + before.st_size <= LIMITS['hash_bytes'], 'total hash limit')
                digest = hashlib.sha256(first); count = len(first)
                while chunk := os.read(descriptor, 1024**2):
                    count += len(chunk); require(count <= LIMITS['file_bytes'], 'file growth limit')
                    require(time.monotonic() - self.started <= LIMITS['seconds'], 'observation time limit')
                    digest.update(chunk)
                require(count == before.st_size, 'partial backing read')
                self.cache[key] = dict(identity=identity, sha256=digest.hexdigest(), size=count)
                self.hash_bytes += count
            require(metadata(os.fstat(descriptor)) == identity and metadata(os.stat(path)) == identity, 'descriptor changed while hashing')
            value = dict(self.cache[key]); value['origin'] = package_origin(row['path'], value, self.binding, package_root)
            file_key = hashlib.sha256((key + row['path']).encode()).hexdigest()
            if file_key not in self.files:
                if value['origin']['kind'] == 'system':
                    if pid == self.process.pid and self.phase.startswith('native') and identity[:2] == self.anchor['executable'][:2]:
                        value['origin'] = dict(kind='owned-driver', members=[], equivalent_members=[])
                    else:
                        try: value['owner'] = package_owner(row['path'], self.phase, self.started + LIMITS['seconds'])
                        except Exception as error:
                            value['owner'] = dict(phase=self.phase, unresolved=type(error).__name__); self.fail(error)
                self.evidence_bytes += len(json.dumps(value).encode()) + len(row['path'].encode()) + 100
                require(self.evidence_bytes <= LIMITS['evidence_bytes'] - 4*1048576, 'runtime evidence limit')
                self.files[file_key] = {**value, 'path': row['path']}
            return dict(category='ELF', file=file_key)
        finally: os.close(descriptor)

    def _sample(self, pid, stage):
        before = process_identity(pid)
        require(before['start'] == self.processes[pid]['start'], 'PID reused')
        raw = bounded(f'/proc/{pid}/maps', LIMITS['maps']); rows = parse_maps(raw)
        require(self.raw_bytes + len(raw) <= LIMITS['raw_bytes'], 'raw evidence limit')
        environment = environment_projection(pid)
        package_root = None
        appdir = environment.get('APPDIR')
        if appdir and self.binding['kind'] == 'appimage':
            require(appdir.startswith('/') and '..' not in Path(appdir).parts, 'ambiguous package root')
            root_stat = os.stat(f'/proc/{pid}/root' + appdir)
            require(stat.S_ISDIR(root_stat.st_mode), 'invalid package root')
            package_root = dict(path=appdir.rstrip('/'), identity=[root_stat.st_dev, root_stat.st_ino])
        try: validate_environment(self.launch_environment, environment, package_root, self.binding['python_loader'])
        except ValueError as error: self.fail(error)
        observed = []
        for row in rows:
            item = dict(category=row['category'])
            if row['category'] == 'file':
                try: item = self._file(pid, row, package_root)
                except Exception as error: item = dict(category='unresolved', reason=type(error).__name__); self.fail(error)
            elif row['category'] in ('deleted', 'ambiguous'): self.fail(row['category'] + ' mapping')
            observed.append(item)
        after_rows = parse_maps(bounded(f'/proc/{pid}/maps', LIMITS['maps']))
        after = process_identity(pid)
        if package_root:
            root_stat = os.stat(f'/proc/{pid}/root' + package_root['path'])
            require([root_stat.st_dev, root_stat.st_ino] == package_root['identity'], 'package root changed')
        require(same_process(before, after), 'process executable changed during sample')
        require(all(row in after_rows for row in rows if row['category'] == 'file'), 'mapping changed during hash')
        executable = [item['file'] for row, item in zip(rows, observed) if item['category'] == 'ELF'
                      and row['inode'] == before['executable'][1]
                      and row['device'] == [os.major(before['executable'][0]), os.minor(before['executable'][0])]]
        require(executable, 'executable mapping unresolved')
        self.raw_bytes += len(raw)
        sample = dict(stage=stage, monotonic=time.monotonic(), wall=time.time(), before=before, after=after,
                                 raw_maps=raw.decode(), observed=observed, executable=sorted(set(executable)), environment=environment, package_root=package_root)
        self.evidence_bytes += len(json.dumps(sample).encode())
        require(self.evidence_bytes <= LIMITS['evidence_bytes'] - 4*1048576, 'runtime evidence limit')
        self.samples.append(sample)

    def _run(self, control):
        next_map = 0
        try:
            while time.monotonic() - self.started <= LIMITS['seconds']:
                self._discover()
                stage = control.recv_bytes(128).decode() if control.poll(.25) else None
                if stage or time.monotonic() >= next_map:
                    self._checkpoint(stage or 'sample'); next_map = time.monotonic() + 1
                if stage == 'before-cleanup': return
            self.fail('observation time limit')
        except Exception as error: self.fail(error)
        finally:
            control.close()
            with self.output.with_suffix('.partial').open('xb') as stream: stream.write(self._receipt_bytes())

    def _checkpoint(self, stage):
        if time.monotonic() - self.started > LIMITS['seconds']:
            self.fail('observation time limit'); self.stopped = True; return
        for pid in list(self.processes):
            try: self._sample(pid, stage)
            except (FileNotFoundError, ProcessLookupError):
                known = self.processes[pid]
                if not any((s['before']['pid'], s['before']['start']) == (pid, known['start']) for s in self.samples):
                    self.fail('transient process not sampled')
            except Exception as error: self.fail(error)

    def checkpoint(self, stage):
        if self.stopped: return
        try:
            require(re.fullmatch('[a-z0-9-]{1,64}', stage) and self.commands < 64, 'checkpoint limit')
            self.commands += 1
            if self.control: self.control.send_bytes(stage.encode())
        except Exception as error: self.fail(error)
        finally:
            if stage == 'before-cleanup': self._stop_worker()

    def _stop_worker(self):
        cancellation = None
        worker = self.worker
        def preserve(error):
            nonlocal cancellation
            if isinstance(error, Exception): self.fail(error)
            elif cancellation is None: cancellation = error
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            try:
                if self.control: self.control.close(); self.control = None
            except BaseException as error: preserve(error)
            if worker and worker.pid is not None:
                # Do not reap the leader before stopping its private query group.
                try:
                    if not wait_for_worker([worker.sentinel], timeout=10): self.fail('observer cleanup timeout')
                except BaseException as error: preserve(error)
                for number in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        if os.getpgid(worker.pid) == worker.pid: os.killpg(worker.pid, number)
                        elif number == signal.SIGTERM: worker.terminate()
                        else: worker.kill()
                        wait_for_worker([worker.sentinel], timeout=2)
                    except ProcessLookupError: pass
                    except BaseException as error: preserve(error)
                try:
                    worker.join(timeout=2)
                    if worker.is_alive(): self.fail('observer cleanup uncertain')
                    else:
                        if worker.exitcode != 0: self.fail('observer exited without final capture')
                        worker.close(); self.worker = None
                except BaseException as error: preserve(error)
        finally:
            self.stopped = True
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if cancellation is not None: raise cancellation

    def _receipt_bytes(self):
        receipt = dict(schema=SCHEMA, binding={key:self.binding[key] for key in BINDING_KEYS}, phase=self.phase,
            launch_environment=self.launch_environment, host=dict(os_release=bounded('/etc/os-release',16384).decode(),
            kernel=platform.release(), architecture=platform.machine(), uid=os.getuid()), anchor=getattr(self,'anchor',None),
            processes=list(self.processes.values()), files=self.files, samples=self.samples, errors=self.errors,
            cleanup_completed=False, raw_bytes=self.raw_bytes, hash_bytes=self.hash_bytes, claims=FALSE_CLAIMS)
        raw = json.dumps(receipt, ensure_ascii=False, separators=(',', ':')).encode()
        require(len(raw) <= LIMITS['evidence_bytes'], 'runtime evidence limit')
        return raw

    def finish(self, cleanup_result):
        if self.finished: return
        try:
            if not self.stopped: self.checkpoint('before-cleanup')
            capture = self.output.with_suffix('.partial')
            if self.process is not None and not capture.is_file(): self.fail('observer capture missing')
            receipt = decode(bounded(capture,LIMITS['evidence_bytes'])) if capture.is_file() else decode(self._receipt_bytes())
            self.cleanup = cleanup_result is True
            for known in receipt['processes']:
                try:
                    current = process_identity(known['pid'])
                    if current['start'] == known['start']: self.cleanup = False
                except (FileNotFoundError, ProcessLookupError): pass
                except Exception: self.cleanup = False
            if not self.cleanup: self.fail('cleanup uncertain')
            receipt['errors'] = sorted(set(receipt['errors'] + self.errors)); receipt['cleanup_completed'] = self.cleanup
            raw = json.dumps(receipt,separators=(',', ':')).encode() + b'\n'
            require(len(raw) <= LIMITS['evidence_bytes'], 'runtime evidence limit')
            with self.output.open('xb') as stream: stream.write(raw)
            if capture.exists(): capture.unlink()
        except Exception as error: self.fail(error)
        finally:
            if self.signal_handler is not None: signal.signal(signal.SIGTERM,self.signal_handler)
            if self.pending_signal is None: atexit.unregister(self._redeliver)
            self.finished = True
def observe_worker(binding, output, phase, launch_environment, anchor, started, control):
    os.setsid()  # Private observer/query group; never the product group.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    observer = Observer(binding, output, phase, launch_environment)
    observer.process = SimpleNamespace(pid=anchor['pid']); observer.anchor = anchor; observer.started = started
    observer.processes[anchor['pid']] = anchor
    observer._run(control)
def notify(observer, method, *arguments):
    if observer is not None:
        try: return getattr(observer, method)(*arguments)
        except Exception as error: observer.fail(error)
def configured(output, phase, launch_environment=None):
    name = os.environ.get('LINUX_PACKAGE_PROVENANCE_BINDING')
    if not name: return None
    try: return Observer(decode(bounded(name, 2*1024**2)), output, phase, launch_environment)
    except Exception: return None  # Required verifier rejects a missing receipt; behavior still runs.
def verify_receipt(receipt, binding, phase):
    require(receipt['schema'] == SCHEMA and receipt['phase'] == phase, 'receipt schema/phase mismatch')
    require(receipt['binding'] == {key: binding[key] for key in BINDING_KEYS}, 'runtime binding mismatch')
    require(receipt['claims'] == FALSE_CLAIMS, 'unsupported runtime claim')
    require(not receipt['errors'] and receipt['cleanup_completed'] is True, 'incomplete runtime observations')
    require(receipt['anchor'] and 0 < len(receipt['processes']) <= LIMITS['processes'], 'missing anchor')
    require(receipt['host']['uid'] > 0 and receipt['host']['architecture'] == 'x86_64', 'host identity mismatch')
    identities = {(p['pid'], p['start']): p for p in receipt['processes']}
    anchor = (receipt['anchor']['pid'], receipt['anchor']['start'])
    require(anchor in identities, 'anchor identity missing')
    for key, process in identities.items():
        seen = set()
        while key != anchor:
            require(key not in seen, 'ancestry cycle'); seen.add(key)
            key = tuple(process.get('ancestor', [])); require(key in identities, 'unbound ancestry'); process = identities[key]
    require(0 < len(receipt['files']) <= LIMITS['files'], 'missing file observations')
    release = dict(line.split('=',1) for line in receipt['host']['os_release'].splitlines() if '=' in line)
    require(release.get('ID','').strip(chr(34)) == 'ubuntu' and release.get('VERSION_ID','').strip(chr(34)) == binding['os'].removeprefix('ubuntu-'), 'OS identity mismatch')
    roles, observed_members, raw_bytes, used = set(), set(), 0, set()
    unique = {tuple(value['identity']):value['size'] for value in receipt['files'].values()}
    require(sum(unique.values()) == receipt['hash_bytes'] <= LIMITS['hash_bytes'], 'hash budget mismatch')
    for value in receipt['files'].values():
        require(0 < value['size'] <= LIMITS['file_bytes'] and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'invalid file identity')
    for sample in receipt['samples']:
        require(same_process(sample['before'], sample['after']), 'unstable process observation')
        require((sample['before']['pid'], sample['before']['start']) in identities, 'unknown sampled process')
        validate_environment(receipt['launch_environment'], sample['environment'], sample['package_root'], binding['python_loader'])
        rows = parse_maps(sample['raw_maps'].encode()); raw_bytes += len(sample['raw_maps'].encode())
        require(len(rows) == len(sample['observed']), 'mapping result count')
        executable_files = set()
        for row, item in zip(rows, sample['observed']):
            require(item['category'] in ('ELF', 'non-ELF', 'anonymous', 'kernel'), 'unresolved mapping')
            require((row['category'] == 'file') == (item['category'] in ('ELF', 'non-ELF')), 'mapping category mismatch')
            if item['category'] == 'non-ELF':
                dev, ino, *_ = item['identity']
                require(row['device'] == [os.major(dev), os.minor(dev)] and row['inode'] == ino, 'non-ELF backing identity')
            if item['category'] != 'ELF': continue
            used.add(item['file']); value = receipt['files'][item['file']]; dev, ino, size, _, _ = value['identity']
            require(row['device'] == [os.major(dev), os.minor(dev)] and row['inode'] == ino and value['size'] == size and row['path'] == value['path'], 'backing identity mismatch')
            origin = package_origin(row['path'], value, binding, sample['package_root'])
            if value['origin']['kind'] == 'owned-driver':
                require((sample['before']['pid'], sample['before']['start']) == anchor and phase.startswith('native'), 'unowned driver')
            else: require(value['origin'] == origin, 'origin mismatch')
            if value['origin']['kind'] == 'system':
                require(value['owner']['phase'] == phase and value['owner']['versions'] and value['owner']['official_archive_byte_origin'] is False, 'system owner phase mismatch')
            observed_members.update(origin['members'])
            if ino == sample['before']['executable'][1] and dev == sample['before']['executable'][0]: executable_files.add(item['file'])
        require(set(sample['executable']) == executable_files and executable_files, 'executable mapping mismatch')
        for key in executable_files:
            value = receipt['files'][key]
            if MAIN in value['origin']['members']: roles.add('desktop')
            if value['origin']['kind'] == 'owned-driver': roles.add('driver')
            if value['origin']['kind'] in ('system', 'package') and Path(value['path']).name in ('WebKitWebProcess', 'WebKitNetworkProcess'): roles.add(Path(value['path']).name)
    sampled = {(sample['before']['pid'], sample['before']['start']) for sample in receipt['samples']}
    require(sampled == set(identities), 'retained process identity was not sampled')
    require(used == set(receipt['files']), 'unreferenced file observation')
    require(raw_bytes == receipt['raw_bytes'] and raw_bytes <= LIMITS['raw_bytes'], 'raw evidence budget mismatch')
    require({'desktop', 'WebKitWebProcess', 'WebKitNetworkProcess'} <= roles, 'missing desktop/helper observation')
    require(not phase.startswith('native') or 'driver' in roles, 'missing native anchor observation')
    return dict(phase=phase, sampled_backing_files_verified=True, observed_members=sorted(observed_members),
                tls='observed' if any(Path(v['path']).name == 'libgiognutls.so' for v in receipt['files'].values()) else 'not_observed', **FALSE_CLAIMS)
def verify_directory(binding, directory, expected):
    for key, value in expected.items(): require(binding[key] == value, 'trusted ' + key + ' mismatch')
    require(binding['schema'] == 'linux-installed-binding-v1' and binding['profile'] == 'linux-engineering-packages-v1', 'binding profile')
    names = [(f'startup-{case}/runtime-provenance.json', f'startup-{case}') for case in
             ('missing-bus', 'unlocked-keyring', 'split-session-bus', 'safe-mode')]
    names += [(f'runtime-provenance-{i}.json', f'native-{i}') for i in (1, 2)]
    results, byte_count, raw_count, hash_count = [], 0, 0, 0
    for name, phase in names:
        raw = bounded(Path(directory) / name, LIMITS['evidence_bytes']); byte_count += len(raw)
        receipt = decode(raw); raw_count += receipt['raw_bytes']; hash_count += receipt['hash_bytes']
        require(byte_count <= LIMITS['evidence_bytes'] and raw_count <= LIMITS['raw_bytes'] and hash_count <= LIMITS['hash_bytes'], 'matrix runtime budget')
        results.append(verify_receipt(receipt, binding, phase))
    return dict(schema=SCHEMA, sessions=results, sampled_backing_files_verified=True, **FALSE_CLAIMS)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['verify'])
    for key in ('binding', 'directory', 'output'): parser.add_argument('--' + key, required=True, type=Path)
    for key in ('source', 'run-id', 'run-attempt', 'os', 'kind'): parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    result = verify_directory(decode(bounded(args.binding, 2*1024**2)), args.directory,
        dict(source_sha=args.source, run_id=args.run_id, run_attempt=args.run_attempt, os=args.os, kind=args.kind))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
