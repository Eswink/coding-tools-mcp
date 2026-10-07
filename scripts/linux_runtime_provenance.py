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
from AppImage入口配置v3 import (validate_runtime_environment as validate_environment, validate_harness_projection,
    SCHEMA, MAIN, BINDING_KEYS, LIMITS, FALSE_CLAIMS, require, same_process, parse_maps, package_origin, verify_receipt)

ENV_KEYS = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'LD_BIND_NOW',
            'GIO_EXTRA_MODULES', 'GIO_MODULE_DIR', 'GIO_USE_TLS', 'GIO_USE_VFS',
            'GTK_PATH', 'GTK_MODULES', 'GDK_BACKEND', 'APPIMAGE', 'APPDIR', 'APPIMAGE_EXTRACT_AND_RUN')
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
def package_owner(path, phase, deadline=None):
    paths = [path] if isinstance(path, str) else path
    def query(arguments):
        require(sum(len(a.encode()) + 1 for a in arguments) <= 65536, 'dpkg argument limit')
        remaining = 5 if deadline is None else min(5, deadline - time.monotonic())
        require(remaining > 0, 'observation time limit')
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(['/usr/bin/dpkg-query', *arguments], stdout=output, stderr=subprocess.DEVNULL,
                                    env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=remaining)
            require(output.tell() <= 65536, 'dpkg diagnostic limit')
            output.seek(0); return result.returncode, output.read().decode('utf-8', 'strict')
    aliases = {p: [p] for p in paths}
    for p in paths:
        if p.startswith('/usr/') and os.path.exists(p[4:]) and os.path.samestat(os.stat(p[4:]), os.stat(p)): aliases[p].append(p[4:])
    code, owners = query(['-S', *sorted({a for group in aliases.values() for a in group})]); require(code in (0, 1), 'unresolved system owner')
    records = {p: [line for line in owners.splitlines() if ': ' in line and line.rsplit(': ', 1)[1] in aliases[p]] for p in paths}
    packages = {p: sorted({line.rsplit(': ', 1)[0] for line in records[p]}) for p in paths}
    require(all(0 < len(v) <= 8 for v in packages.values()), 'unresolved system owner')
    code, versions = query(['-W', '-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n', *sorted({n for v in packages.values() for n in v})])
    require(code == 0, 'unresolved system version')
    result = {}
    for p in paths:
        rows = [line for line in versions.splitlines() if line.split('\t')[0] in packages[p]]
        require({line.split('\t')[0] for line in rows} == set(packages[p]) and all(len(line.split('\t')) == 5 for line in rows), 'unresolved system version')
        result[p] = dict(phase=phase, ownership='\n'.join(records[p]), versions='\n'.join(rows), official_archive_byte_origin=False)
    return result[path] if isinstance(path, str) else result

class Observer:
    def __init__(self, binding, output, phase, launch_environment=None):
        self.binding, self.output, self.phase = binding, Path(output), phase
        self.errors, self.processes, self.files, self.samples, self.cache = [], {}, {}, [], {}
        self.raw_bytes = self.hash_bytes = self.evidence_bytes = 0
        self.ready = self.ready_at = self.deadline = None; self.required = set(); self.bootstrap = []; self.discovery = []; self.requests = []; self.progress = {}; self.hash_reads = []
        self.started = time.monotonic(); self.stopped = False; self.commands = 0
        self.worker = self.control = self.process = None; self.finished = False; self.signal_handler = self.pending_signal = None
        self.launch_environment = environment_projection(environment=os.environ if launch_environment is None else launch_environment)
        self.harness_environment, self.projection = environment_projection(environment=os.environ), None

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
                self.launch_environment, self.projection, self.anchor, self.started, receiver))
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

    def _remember(self, identity):
        if self.ready: self.required.add((identity['pid'], identity['start']))
        if any(same_process(e, identity) and (e['monotonic'] >= (self.ready_at or float('inf'))) == bool(self.ready) for e in self.discovery): return
        require(len(self.discovery) < LIMITS['rows'], 'discovery identity limit')
        event = dict(identity, monotonic=time.monotonic()); self.discovery.append(event)
        if not self.ready: self.bootstrap.append(event)

    def _roles(self):
        result = set()
        for sample in self.samples:
            if sample['status'] != 'complete': continue
            for key in sample['executable']:
                value = self.files[key]
                if MAIN in value['origin']['members']: result.add('desktop')
                if value['origin']['kind'] == 'owned-driver': result.add('driver')
                if value['origin']['kind'] in ('system', 'package'): result.add(Path(value['path']).name)
        return result

    def _discover(self):
        pending = list(self.processes); threads = 0
        while pending:
            require(time.monotonic() - self.started <= LIMITS['seconds'], 'observation time limit')
            pid = pending.pop(0); known = self.processes[pid]
            try:
                current = process_identity(pid)
                require(current['start'] == known['start'], 'PID reused')
                self._remember(current)
                for task in Path(f'/proc/{pid}/task').iterdir():
                    threads += 1; require(threads <= LIMITS['rows'], 'thread discovery limit')
                    for item in bounded(task / 'children', 65536).split():
                        child = int(item)
                        if child in self.processes: continue
                        require(len(self.processes) < LIMITS['processes'], 'process limit')
                        identity = process_identity(child)
                        require(identity['parent'] == pid, 'child ancestry changed')
                        identity['ancestor'] = [pid, known['start']]
                        self.processes[child] = identity; self._remember(identity); pending.append(child)
                        if self.ready and not any(q['stage'] == 'before-cleanup' for q in self.requests):
                            if any(s['status'] == 'complete' and (s['before']['pid'], s['before']['start']) == (pid, known['start']) for s in self.samples):
                                self._checkpoint('discovery', [child])
            except (FileNotFoundError, ProcessLookupError):
                if (pid, known['start']) in self.required and not any(s.get('status') == 'complete' and s['pid'] == pid for s in self.samples): self.fail('transient process not sampled')
            except Exception as error: self.fail(error)

    def _file(self, pid, row, package_root=None):
        require(time.monotonic() - self.started <= LIMITS['seconds'], 'observation time limit')
        require(self.deadline is None or time.monotonic() < self.deadline, 'final capture deadline')
        self.progress.update(pid=pid, operation='backing-file')
        path = f'/proc/{pid}/root' + row['path']
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor); identity = metadata(before)
            require(stat.S_ISREG(before.st_mode), 'nonregular backing file')
            require([os.major(before.st_dev), os.minor(before.st_dev)] == row['device'] and before.st_ino == row['inode'], 'namespace backing identity mismatch')
            require(before.st_size <= LIMITS['file_bytes'], 'file limit')
            key = ':'.join(map(str, identity))
            if key not in self.cache:
                require(self.hash_bytes + min(4, before.st_size) <= LIMITS['hash_bytes'], 'total hash limit')
                first = os.read(descriptor, 4)
                if first != b'\x7fELF':
                    require(metadata(os.fstat(descriptor)) == identity, 'non-ELF descriptor changed')
                    return dict(category='non-ELF', identity=identity)
                require(len(self.files) < LIMITS['files'], 'ELF file limit')
                read = dict(identity=identity, bytes=4, complete=False, sha256=None); self.hash_reads.append(read); self.hash_bytes += 4
                require(self.hash_bytes <= LIMITS['hash_bytes'], 'total hash limit'); digest = hashlib.sha256(first)
                while chunk := os.read(descriptor, 1024**2):
                    read['bytes'] += len(chunk); self.hash_bytes += len(chunk)
                    require(read['bytes'] <= LIMITS['file_bytes'] and self.hash_bytes <= LIMITS['hash_bytes'], 'hash read limit')
                    require(time.monotonic() < min(self.started + LIMITS['seconds'], self.deadline or float('inf')), 'observation time limit')
                    digest.update(chunk)
                require(read['bytes'] == before.st_size, 'partial backing read')
                require(metadata(os.fstat(descriptor)) == identity and metadata(os.stat(path)) == identity, 'descriptor changed while hashing')
                read.update(complete=True, sha256=digest.hexdigest())
                self.cache[key] = dict(identity=identity, sha256=read['sha256'], size=read['bytes'])
            require(metadata(os.fstat(descriptor)) == identity and metadata(os.stat(path)) == identity, 'descriptor changed while hashing')
            value = dict(self.cache[key]); value['origin'] = package_origin(row['path'], value, self.binding, package_root)
            file_key = hashlib.sha256((key + row['path']).encode()).hexdigest()
            if file_key not in self.files:
                if value['origin']['kind'] == 'system' and pid == self.process.pid and self.phase.startswith('native') and identity[:2] == self.anchor['executable'][:2]:
                    value['origin'] = dict(kind='owned-driver', members=[], equivalent_members=[])
                self.evidence_bytes += len(json.dumps(value).encode()) + len(row['path'].encode()) + 100
                require(self.evidence_bytes <= LIMITS['evidence_bytes'] - 4*1048576, 'runtime evidence limit')
                self.files[file_key] = {**value, 'path': row['path']}
            return dict(category='ELF', file=file_key)
        finally: os.close(descriptor)

    def _sample(self, pid, stage, attempt=0):
        sample = dict(pid=pid, stage=stage, attempt=attempt, status='unknown', monotonic=time.monotonic(), wall=time.time(),
            before=None, after=None, raw_maps='', raw_after='', observed=[], executable=[], environment={}, package_root=None)
        self.samples.append(sample); self.progress = dict(stage=stage, pid=pid, operation='maps-before')
        try:
            before = process_identity(pid); sample['before'] = before
            require(before['start'] == self.processes[pid]['start'], 'PID reused')
            raw = bounded(f'/proc/{pid}/maps', LIMITS['maps']); self.raw_bytes += len(raw); sample['raw_maps'] = raw.decode(); rows = parse_maps(raw)
            require(self.raw_bytes <= LIMITS['raw_bytes'], 'raw evidence limit')
            environment = environment_projection(pid); sample['environment'] = environment
            root = None; appdir = environment.get('APPDIR')
            if appdir and self.binding['kind'] == 'appimage':
                require(appdir.startswith('/') and '..' not in Path(appdir).parts, 'ambiguous package root')
                info = os.stat(f'/proc/{pid}/root' + appdir); require(stat.S_ISDIR(info.st_mode), 'invalid package root')
                root = dict(kind='appimage', path=appdir.rstrip('/'), identity=[info.st_dev, info.st_ino]); sample['package_root'] = root
            for row in rows:
                item = dict(category=row['category'])
                if row['category'] == 'file':
                    try: item = self._file(pid, row, root)
                    except Exception as error:
                        item = dict(category='unresolved', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)
                        if not isinstance(error, (FileNotFoundError, ProcessLookupError)): self.fail(error)
                elif row['category'] == 'shared-memory': item['bytes_verified'] = False
                elif row['category'] in ('deleted', 'ambiguous'): self.fail(row['category'] + ' mapping')
                sample['observed'].append(item)
            self.progress['operation'] = 'maps-after'
            raw = bounded(f'/proc/{pid}/maps', LIMITS['maps']); self.raw_bytes += len(raw); sample['raw_after'] = raw.decode(); after_rows = parse_maps(raw)
            require(self.raw_bytes <= LIMITS['raw_bytes'], 'raw evidence limit')
            after = process_identity(pid); sample['after'] = after
            require(all(before[k] == after[k] for k in ('pid', 'start')), 'PID reused')
            require(same_process(before, after), 'process executable changed during sample')
            validate_environment(self.launch_environment, environment, root, self.binding['python_loader'], self.binding['python_loader_omission'])
            require(all(row in after_rows for row in rows if row['category'] == 'file'), 'mapping changed during hash')
            if root:
                info = os.stat(f'/proc/{pid}/root' + root['path']); require([info.st_dev, info.st_ino] == root['identity'], 'package root changed')
            require(all(i['category'] not in ('deleted', 'ambiguous', 'unresolved') for i in sample['observed']), 'unresolved backing mapping')
            sample['executable'] = sorted({i['file'] for row, i in zip(rows, sample['observed']) if i['category'] == 'ELF'
                and row['inode'] == before['executable'][1] and row['device'] == [os.major(before['executable'][0]), os.minor(before['executable'][0])]})
            require(sample['executable'], 'executable mapping unresolved'); sample['status'] = 'complete'
        except BaseException as error:
            sample['reason'] = str(error) if isinstance(error, ValueError) else type(error).__name__; raise
        finally:
            self.evidence_bytes += len(json.dumps(sample).encode())
            require(self.evidence_bytes <= LIMITS['evidence_bytes'] - 4*1048576, 'runtime evidence limit')

    def _run(self, control):
        next_map = 0
        try:
            while time.monotonic() - self.started <= LIMITS['seconds']:
                stages = []
                if control.poll(.25):
                    while True:
                        stage, stamp = decode(control.recv_bytes(128)); require(re.fullmatch('[a-z0-9-]{1,64}', stage) and type(stamp) in (int, float) and 0 < stamp <= time.monotonic(), 'invalid checkpoint')
                        stages.append(stage); self.requests.append(dict(stage=stage, monotonic=stamp)); require(len(self.requests) <= 64, 'checkpoint limit')
                        if stage == 'before-cleanup' or not control.poll(): break
                expected = 'native-ready' if self.phase.startswith('native') else 'first-window'
                if expected in stages and not self.ready: self.ready = expected; self.ready_at = time.monotonic()
                self._discover(); final = 'before-cleanup' in stages
                if final: self.deadline = min(self.started + LIMITS['seconds'], next(q['monotonic'] for q in self.requests if q['stage'] == 'before-cleanup') + 8)
                if self.ready and (stages or time.monotonic() >= next_map):
                    self._checkpoint('before-cleanup' if final else stages[-1] if stages else 'sample'); next_map = time.monotonic() + 1
                if final:
                    needed = {'desktop', 'WebKitWebProcess', 'WebKitNetworkProcess'} | ({'driver'} if self.phase.startswith('native') else set())
                    while self.ready and not needed <= self._roles() and time.monotonic() < self.deadline - 3:
                        time.sleep(min(.25, max(0, self.deadline - 3 - time.monotonic()))); self._discover(); self._checkpoint('before-cleanup')
                    require(needed <= self._roles(), 'missing desktop/helper observation')
                    self.progress['operation'] = 'ownership'
                    paths = sorted({v['path'] for v in self.files.values() if v['origin']['kind'] == 'system'})
                    owners = package_owner(paths, self.phase, self.deadline) if paths else {}
                    for value in self.files.values():
                        if value['origin']['kind'] == 'system':
                            require(metadata(os.stat(value['path'])) == value['identity'], 'owner backing changed')
                            value['owner'] = owners[value['path']]
                    self.progress['operation'] = 'captured'; return
            self.fail('observation time limit')
        except BaseException as error:
            self.fail(error)
            if not isinstance(error, Exception): raise
        finally:
            control.close()
            failure = dict(schema=SCHEMA, phase=self.phase, progress=self.progress, errors=self.errors, complete=False)
            progress = json.dumps(failure).encode(); require(len(progress) <= 65536, 'progress limit')
            with self.output.with_suffix('.progress').open('xb') as stream: stream.write(progress)
            with self.output.with_suffix('.partial').open('xb') as stream: stream.write(self._receipt_bytes())

    def _checkpoint(self, stage, pids=None):
        if time.monotonic() - self.started > LIMITS['seconds']:
            self.fail('observation time limit'); self.stopped = True; return
        for pid in list(self.processes) if pids is None else pids:
            known = self.processes[pid]
            if self.deadline is not None and time.monotonic() >= self.deadline: self.fail('final capture deadline'); break
            if self.ready and (pid, known['start']) not in self.required: continue
            for attempt in range(2):
                try: self._sample(pid, stage, attempt); break
                except (FileNotFoundError, ProcessLookupError):
                    sample = self.samples[-1]
                    if sample['before'] is None and any(s.get('status') == 'complete' and s['pid'] == pid for s in self.samples): sample['reason'] = 'exited-after-observation'
                    else: self.fail('transient process not sampled')
                    break
                except Exception as error:
                    if attempt == 0 and str(error) in ('process executable changed during sample', 'mapping changed during hash'):
                        self.samples[-1]['status'] = 'retry'; continue
                    self.fail(error); break

    def checkpoint(self, stage):
        if self.stopped: return
        try:
            require(re.fullmatch('[a-z0-9-]{1,64}', stage) and self.commands < 64, 'checkpoint limit')
            self.commands += 1
            if self.control: self.control.send_bytes(json.dumps([stage, time.monotonic()]).encode())
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
            projection=self.projection, harness_environment=self.harness_environment,
            launch_environment=self.launch_environment, host=dict(os_release=bounded('/etc/os-release',16384).decode(),
            kernel=platform.release(), architecture=platform.machine(), uid=os.getuid()), anchor=getattr(self,'anchor',None),
            processes=list(self.processes.values()), files=self.files, samples=self.samples, errors=self.errors,
            ready=self.ready, ready_at=self.ready_at, required=sorted(self.required), bootstrap=self.bootstrap, discovery=self.discovery, requests=self.requests, progress=self.progress, hash_reads=self.hash_reads,
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
def observe_worker(binding, output, phase, launch_environment, projection, anchor, started, control):
    os.setsid()  # Private observer/query group; never the product group.
    observer = Observer(binding, output, phase, launch_environment)
    signal.signal(signal.SIGTERM, observer._handle_term)
    observer.projection = projection
    observer.process = SimpleNamespace(pid=anchor['pid']); observer.anchor = anchor; observer.started = started
    observer.processes[anchor['pid']] = anchor; observer._remember(anchor)
    observer._run(control)
def notify(observer, method, *arguments):
    if observer is not None:
        try: return getattr(observer, method)(*arguments)
        except Exception as error: observer.fail(error)
def configured(output, phase, launch_environment=None):
    name = os.environ.get('LINUX_PACKAGE_PROVENANCE_BINDING')
    if not name: return None
    binding = decode(bounded(name, 2*1024**2))
    group = 'native' if phase in ('native-1', 'native-2') else phase
    projection = decode(bounded(Path(name).with_name(group + '-launch-projection.json'), 65536))
    observer = Observer(binding, output, phase, launch_environment)
    observer.projection = projection
    validate_harness_projection(projection, binding, group, observer.harness_environment, observer.launch_environment)
    return observer
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
