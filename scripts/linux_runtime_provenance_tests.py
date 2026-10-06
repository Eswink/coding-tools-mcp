"""Backing-file fixtures and lifecycle controls; fixtures are not installed GUI evidence."""
import ast
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import linux_runtime_provenance as runtime
import linux_startup_candidate as startup
import exclusive_native_acceptance as native

gui, adapter = native.gui, native.adapter
from linux_package_binding_tests import binding, python_loader, identity, row, query_group_fixture
import linux_package_binding_tests as shared
class RuntimeMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name)
        cls.app = cls.root / runtime.MAIN; cls.app.parent.mkdir(parents=True)
        cls.lib = cls.root / 'usr/lib/late module.so'; cls.lib.parent.mkdir()
        (cls.root/'main.c').write_text('#include <stdio.h>\n#include <dlfcn.h>\nint main(int n,char**v){puts("ready");fflush(stdout);getchar();void*p=dlopen(v[1],RTLD_NOW);puts(p?"loaded":"failed");fflush(stdout);getchar();return p?0:2;}')
        (cls.root/'late.c').write_text('int late_value(void){return 42;}')
        subprocess.run(['/usr/bin/cc', '-shared', '-fPIC', str(cls.root/'late.c'), '-o', str(cls.lib)], check=True, capture_output=True)
        subprocess.run(['/usr/bin/cc', str(cls.root/'main.c'), '-ldl', '-o', str(cls.app)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setUp(self):
        self.out = tempfile.TemporaryDirectory(); self.addCleanup(self.out.cleanup)
        members = [dict(path=str(p.relative_to(self.root)), size=p.stat().st_size,
                        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (self.app, self.lib)]
        self.binding = binding(members, kind='deb')
        self.binding['members'] = [{**m, 'path':str(self.root / m['path']).lstrip('/')} for m in members]
        self.observer = runtime.Observer(self.binding, Path(self.out.name)/'receipt.json', 'startup-fixture', {'PATH':'/usr/bin:/bin'})
        self.observer.process = SimpleNamespace(pid=-1)

    def launch(self):
        self.assertNotEqual(os.getuid(), 0, 'the real mapping fixture must be ordinary-user')
        process = subprocess.Popen([str(self.app), str(self.lib)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   env={'PATH': '/usr/bin:/bin'}, text=True)
        self.assertEqual(process.stdout.readline(), 'ready\n')
        def close():
            if process.poll() is None: process.terminate(); process.wait(timeout=5)
            process.stdin.close(); process.stdout.close()
        self.addCleanup(close)
        self.observer.process = process
        self.observer.anchor = runtime.process_identity(process.pid)
        self.observer.processes[process.pid] = self.observer.anchor
        return process

    def test_maps_parsing_preserves_spaces_ranges_offsets_devices_and_inodes(self):
        parsed = runtime.parse_maps(b'1000-2000 r-xp 00001000 08:02 123 /a path/lib.so\n')[0]
        self.assertEqual(parsed, dict(start=4096, end=8192, permissions='r-xp', offset=4096,
                                    device=[8, 2], inode=123, path='/a path/lib.so', category='file'))

    def test_truncated_overlapping_invalid_or_oversized_maps_reject(self):
        line = b'1000-2000 r-xp 0 08:02 1 /lib.so\n'
        for raw in (line[:-1], line+line, b'broken\n', b'x'*1048577, line.replace(b'/lib.so', b'/' + b'a'*4097)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError): runtime.parse_maps(raw)
        with patch.dict(runtime.LIMITS, rows=0), self.assertRaises(ValueError): runtime.parse_maps(line)

    def test_unprivileged_live_elf_mapping_is_hashed_from_actual_descriptor(self):
        process = self.launch(); opened = []
        real_open = os.open
        def observe(path, flags, *args, **kwargs): opened.append(str(path)); return real_open(path, flags, *args, **kwargs)
        with patch.object(runtime.os, 'open', side_effect=observe): self.observer._sample(process.pid, 'real-live')
        actual = [v for v in self.observer.files.values() if v['sha256'] == identity(self.app)['sha256']]
        self.assertEqual(actual[0]['identity'], identity(self.app)['identity'])
        self.assertIn(f'/proc/{process.pid}/root{self.app}', opened)
        self.assertTrue(any(v['origin']['members'] == [str(self.app).lstrip('/')] for v in actual))
        self.assertNotIn('map_files', '\n'.join(opened))
        self.assertTrue(all(error == 'unresolved system owner' for error in self.observer.errors), self.observer.errors)

    def test_later_dlopen_module_is_observed_without_loader_injection(self):
        process = self.launch(); self.observer._sample(process.pid, 'before-dlopen')
        digest = identity(self.lib)['sha256']
        self.assertFalse(any(v['sha256'] == digest for v in self.observer.files.values()))
        process.stdin.write('\n'); process.stdin.flush(); self.assertEqual(process.stdout.readline(), 'loaded\n')
        self.observer._sample(process.pid, 'after-dlopen')
        self.assertTrue(any(v['sha256'] == digest for v in self.observer.files.values()))
        self.assertNotIn('LD_PRELOAD', self.observer.samples[-1]['environment'])

    def test_bundled_mapping_matches_final_package_member_not_path_prefix(self):
        value = identity(self.lib); root = dict(path=str(self.root), identity=[self.root.stat().st_dev, self.root.stat().st_ino])
        expected = binding([dict(path='usr/lib/late module.so',size=value['size'],sha256=value['sha256'])])
        bundled = runtime.package_origin(str(self.lib), value, expected, root)
        self.assertEqual(bundled['kind'], 'package')
        host = runtime.package_origin('/usr/lib/late module.so', value, expected, root)
        self.assertEqual(host['kind'], 'system'); self.assertTrue(host['equivalent_members'])
        with self.assertRaises(ValueError): runtime.package_origin(str(self.lib), {**value, 'sha256':'f'*64}, expected, root)
        self.assertEqual(runtime.package_origin(str(self.lib), value, expected)['kind'], 'system')

    def test_same_path_with_different_device_inode_or_bytes_rejects(self):
        for field, value in [('inode', 1), ('device', [0, 1])]:
            with self.subTest(field=field), self.assertRaises(ValueError): self.observer._file(os.getpid(), {**row(self.lib), field:value})
        expected = {**self.binding, 'kind':'deb', 'members':[dict(path=str(self.lib).lstrip('/'), size=1, sha256='0'*64)]}
        with self.assertRaises(ValueError): runtime.package_origin(str(self.lib), identity(self.lib), expected)

    def test_namespace_path_must_match_observed_backing_file_identity(self):
        original = row(self.lib); wrong = dict(original, path=str(self.app))
        with self.assertRaisesRegex(ValueError, 'namespace backing'): self.observer._file(os.getpid(), wrong)
        with patch.object(runtime.os, 'open', side_effect=PermissionError), self.assertRaises(PermissionError):
            self.observer._file(os.getpid(), original)

    def test_descriptor_or_mapping_change_during_hash_is_incomplete(self):
        copy_path = Path(self.out.name)/'changed.so'; copy_path.write_bytes(self.lib.read_bytes())
        real_read = os.read; changed = False
        def mutate(fd, size):
            nonlocal changed
            raw = real_read(fd, size)
            if not changed: changed = True; copy_path.write_bytes(copy_path.read_bytes()+b'x')
            return raw
        with patch.object(runtime.os, 'read', side_effect=mutate), self.assertRaises(ValueError):
            self.observer._file(os.getpid(), row(copy_path))
        process = self.launch(); original = runtime.bounded
        calls = 0
        def changed_maps(path, limit):
            nonlocal calls
            raw = original(path, limit)
            if str(path).endswith('/maps'):
                calls += 1
                if calls == 2: return b'1000-2000 rw-p 0 00:00 0\n'
            return raw
        with patch.object(runtime, 'bounded', side_effect=changed_maps), self.assertRaisesRegex(ValueError, 'mapping changed'):
            self.observer._sample(process.pid, 'raced')
        self.assertEqual(self.observer.samples[-1]['status'],'unknown')
        self.assertTrue(self.observer.samples[-1]['raw_maps']); self.assertTrue(self.observer.samples[-1]['raw_after'])
        calls = 0
        with patch.object(runtime,'bounded',side_effect=changed_maps): self.observer._checkpoint('finite-retry')
        self.assertEqual([s['status'] for s in self.observer.samples[-2:]],['retry','complete'])
        self.assertEqual([s['attempt'] for s in self.observer.samples[-2:]],[0,1])
        self.assertEqual(self.observer.raw_bytes,sum(len(s[k].encode()) for s in self.observer.samples for k in ('raw_maps','raw_after')))
        self.assertEqual(self.observer.hash_bytes,sum(r['bytes'] for r in self.observer.hash_reads))
        self.assertTrue(any(not r['complete'] for r in self.observer.hash_reads))
        self.assertEqual(set(self.observer.files),{i['file'] for s in self.observer.samples for i in s['observed'] if i['category']=='ELF'})
        def churn(path, limit):
            nonlocal calls
            if str(path).endswith('/maps'):
                calls += 1
                if calls % 2 == 0: return b'1000-2000 rw-p 0 00:00 0\n'
            return original(path,limit)
        calls = 0
        with patch.object(runtime,'bounded',side_effect=churn): self.observer._checkpoint('exhausted-retry')
        self.assertEqual([s['status'] for s in self.observer.samples[-2:]],['retry','unknown'])
        self.assertEqual(calls,4); self.assertIn('mapping changed during hash',self.observer.errors)

    def test_pid_start_time_reuse_and_executable_replacement_reject(self):
        process = self.launch(); before = runtime.process_identity(process.pid)
        self.observer.processes[process.pid]['start'] -= 1
        with self.assertRaisesRegex(ValueError, 'PID reused'): self.observer._sample(process.pid, 'reused')
        self.observer.processes[process.pid]['start'] += 1
        replaced = copy.deepcopy(before); replaced['executable'][1] += 1
        with patch.object(runtime, 'process_identity', side_effect=[before, replaced]), self.assertRaisesRegex(ValueError, 'executable changed'):
            self.observer._sample(process.pid, 'exec-race')

    def test_deleted_unreadable_ambiguous_and_anonymous_entries_are_distinct(self):
        paths = [('/a (deleted)', 'deleted'), ('/a\\012b', 'ambiguous'), ('', 'anonymous'), ('[vdso]', 'kernel')]
        for path, category in paths:
            self.assertEqual(runtime.parse_maps(f'1000-2000 r-xp 0 00:01 1 {path}\n'.encode())[0]['category'], category)
        for name in ('/SYSV00000000 (deleted)', '/memfd:WebKitSharedMemory (deleted)'):
            for permissions in ('r--s','rw-s'):
                raw = f'1000-2000 {permissions} 0 00:01 1 {name}\n'.encode()
                self.assertEqual(runtime.parse_maps(raw)[0]['category'],'shared-memory')
                for old, new in ((permissions,'r-xs'),(permissions,'rw-p'),('00:01','00:02'),(name,'/other (deleted)'),(name,name+'x')):
                    with self.subTest(name=name,mutation=new):
                        self.assertNotEqual(runtime.parse_maps(raw.replace(old.encode(),new.encode()))[0]['category'],'shared-memory')
        process = self.launch()
        with patch.object(self.observer, '_file', side_effect=PermissionError): self.observer._checkpoint('unreadable')
        self.assertIn('unresolved backing mapping', self.observer.errors)
        self.assertFalse(any(s['status']=='complete' for s in self.observer.samples))
        self.assertTrue(any(i.get('reason')=='PermissionError' for s in self.observer.samples for i in s['observed']))

    def test_descendant_threads_grandchildren_and_seen_reparenting_are_bound(self):
        self.observer.processes = {10:dict(pid=10, start=100, parent=1)}
        rows = {10:dict(pid=10,start=100,parent=1), 20:dict(pid=20,start=200,parent=10), 30:dict(pid=30,start=300,parent=20)}
        for pid,value in rows.items(): value.update(executable=[2049,pid,10,1,1],executable_path='/fixture/'+str(pid))
        def children(path, limit): return {'/proc/10/task/11/children':b'20', '/proc/20/task/20/children':b'30'}.get(str(path), b'')
        def tasks(path): return [Path(str(path))/('11' if str(path).startswith('/proc/10/') else path.parts[2])]
        with patch.object(runtime, 'process_identity', side_effect=lambda pid:rows[pid]), patch.object(runtime, 'bounded', side_effect=children), patch.object(Path, 'iterdir', tasks):
            self.observer._discover(); rows[20]['parent'] = 1; self.observer._discover()
        self.assertEqual(self.observer.processes[20]['ancestor'], [10,100])
        self.assertEqual(self.observer.processes[30]['ancestor'], [20,200])
        self.assertEqual(set(self.observer.processes), {10,20,30})
        self.observer.bootstrap = []; self.observer.discovery = []; self.observer.processes = {10:rows[10]}; rows[20]['parent'] = 10; seen = set()
        def transient(pid):
            if pid == 20 and pid in seen: raise FileNotFoundError()
            seen.add(pid); return copy.deepcopy(rows[pid])
        with patch.object(runtime,'process_identity',side_effect=transient),patch.object(runtime,'bounded',side_effect=children),patch.object(Path,'iterdir',tasks): self.observer._discover()
        self.assertTrue(any(p['pid']==20 for p in self.observer.bootstrap)); self.assertEqual(self.observer.errors,[])

    def test_driver_name_or_group_cannot_substitute_for_product_identity(self):
        value = identity(self.app)
        self.assertEqual(runtime.package_origin('/tmp/coding-tools-mcp-desktop', value, self.binding)['kind'], 'system')
        self.assertEqual(runtime.package_origin('/usr/bin/tauri-driver', value, self.binding)['members'], [])
        self.assertNotIn('getpgid', inspect.getsource(runtime.Observer._discover))

    def test_only_bounded_loader_environment_projection_is_retained(self):
        projection = runtime.environment_projection(environment={'PASSWORD':'secret', 'TOKEN':'secret', 'LD_LIBRARY_PATH':'/bundle:/inherited', 'APPDIR':'/bundle'})
        self.assertEqual(projection, {'LD_LIBRARY_PATH':'/bundle:/inherited','APPDIR':'/bundle'})
        with self.assertRaises(ValueError): runtime.environment_projection(environment={'GTK_PATH':'x'*4097})
        self.assertNotIn('cmdline', inspect.getsource(runtime))
        with patch.dict(os.environ, {'LD_LIBRARY_PATH':'/opt/hostedtoolcache/Python/3.12.14/x64/lib'}, clear=True):
            explicit = runtime.Observer(binding(), Path(self.out.name)/'explicit.json', 'fixture', {})
            inherited = runtime.Observer(binding(), Path(self.out.name)/'inherited.json', 'fixture')
        self.assertEqual(explicit.launch_environment, {})
        self.assertEqual(inherited.launch_environment, {'LD_LIBRARY_PATH':'/opt/hostedtoolcache/Python/3.12.14/x64/lib'})
        for path in (Path(runtime.__file__),Path(inspect.getmodule(runtime.validate_environment).__file__)):
            ast.parse(path.read_text(),feature_version=(3,10))
        isolated = """import builtins,sys
sys.path.insert(0,SCRIPTS)
original = builtins.__import__
def restricted(name,*args,**kwargs):
    if name in ('tomllib','linux_package_provenance_contract','desktop_glib_build_contract'):
        raise AssertionError('system Python import reached compiler-only dependency: '+name)
    return original(name,*args,**kwargs)
builtins.__import__ = restricted
import linux_runtime_provenance as runtime
runtime.validate_environment({}, {}, None, None, RECORD)
""".replace('SCRIPTS',repr(str(Path(runtime.__file__).parent))).replace('RECORD',repr(binding()['python_loader_omission']))
        result = subprocess.run([sys.executable,'-I','-B','-c',isolated],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_system_owner_is_phase_specific_and_not_official_byte_origin(self):
        path = '/usr/lib/x86_64-linux-gnu/libc.so.6'; version = '1'
        def dpkg(args, **kwargs):
            raw = ('libc6:amd64: ' + path + '\n') if '-S' in args else ('libc6:amd64\t'+version+'\tamd64\tglibc\t'+version+'\n')
            kwargs['stdout'].write(raw.encode()); return SimpleNamespace(returncode=0)
        with patch.object(runtime.subprocess,'run',side_effect=dpkg):
            first = runtime.package_owner(path, 'startup-fixture'); version = '2'
            second = runtime.package_owner(path, 'native-1')
        self.assertNotEqual(first['versions'], second['versions'])
        self.assertEqual(first['phase'], 'startup-fixture'); self.assertEqual(second['phase'], 'native-1')
        self.assertIn('libc6', first['ownership']); self.assertFalse(first['official_archive_byte_origin'])
        paths = ['/opt/fixture/a.so','/opt/fixture/b.so']; calls = []
        def batch(args,**kwargs):
            calls.append(args); raw = ''.join('fixture: '+p+'\n' for p in paths) if '-S' in args else 'fixture\t1\tamd64\tfixture\t1\n'
            kwargs['stdout'].write(raw.encode()); return SimpleNamespace(returncode=0)
        with patch.object(runtime.subprocess,'run',side_effect=batch): owners = runtime.package_owner(paths,'native-2')
        self.assertEqual(len(calls),2); self.assertEqual(set(calls[0][2:]),set(paths)); self.assertEqual(set(owners),set(paths))
        self.assertTrue(all(v['phase']=='native-2' and not v['official_archive_byte_origin'] for v in owners.values()))
        for failed in ('owner','version','output','owner-error','owner-signal'):
            def failure(args,**kwargs):
                if failed in ('owner-error','owner-signal'):
                    result = batch(args,**kwargs); result.returncode = (2 if failed=='owner-error' else -15) if '-S' in args else 0; return result
                if failed=='output': kwargs['stdout'].write(b'x'*65537); return SimpleNamespace(returncode=0)
                if (failed=='owner') == ('-S' in args): return SimpleNamespace(returncode=1)
                return batch(args,**kwargs)
            with patch.object(runtime.subprocess,'run',side_effect=failure),self.assertRaises(ValueError): runtime.package_owner(paths,'native-2')
        with patch.object(runtime.subprocess,'run',side_effect=AssertionError('capture must not query dpkg')):
            self.observer._file(os.getpid(),row(self.lib))

    def test_process_file_time_and_total_byte_limits_latch_incomplete(self):
        process = self.launch()
        for key, value in [('file_bytes',1), ('hash_bytes',1), ('files',0)]:
            with patch.dict(runtime.LIMITS, {key:value}), self.assertRaises(ValueError): self.observer._file(process.pid, row(self.app))
        tiny = Path(self.out.name)/'tiny'; tiny.write_bytes(b'\x7fELF')
        with patch.dict(runtime.LIMITS,hash_bytes=1),self.assertRaises(ValueError): self.observer._file(process.pid,row(tiny))
        with patch.dict(runtime.LIMITS, raw_bytes=1): self.observer._checkpoint('raw-limit')
        self.assertIn('raw evidence limit', self.observer.errors)
        self.observer.started -= 901; self.observer._checkpoint('deadline')
        self.assertIn('observation time limit', self.observer.errors); self.assertTrue(self.observer.stopped)
        self.observer.started = time.monotonic()
        self.observer.processes = {10:dict(pid=10,start=1)}
        with patch.dict(runtime.LIMITS, processes=1), patch.object(runtime,'process_identity',return_value=dict(pid=10,start=1)), patch.object(Path,'iterdir',return_value=[Path('/proc/10/task/10')]), patch.object(runtime,'bounded',return_value=b'20'):
            self.observer._discover()
        self.assertIn('process limit', self.observer.errors)
        with self.assertRaisesRegex(ValueError,'observation time limit'):
            runtime.package_owner('/usr/lib/example.so','native-1',time.monotonic()-1)
        with patch.dict(runtime.LIMITS,evidence_bytes=1),self.assertRaisesRegex(ValueError,'runtime evidence limit'): self.observer._receipt_bytes()
        with self.assertRaisesRegex(ValueError,'dpkg argument limit'): runtime.package_owner(['/opt/'+('x'*65536)],'native-1')

    def test_unobserved_tls_and_transient_lifetime_coverage_cannot_be_promoted(self):
        self.assertFalse(runtime.FALSE_CLAIMS['tls_runtime_closure'])
        self.assertFalse(runtime.FALSE_CLAIMS['complete_lifetime_closure'])
        self.assertFalse(runtime.FALSE_CLAIMS['atomic_snapshot'])
        self.observer.processes = {10:dict(pid=10,start=1)}; self.observer.required = {(10,1)}; self.observer.ready = 'first-window'
        with patch.object(runtime, 'process_identity', side_effect=FileNotFoundError): self.observer._discover()
        self.assertIn('transient process not sampled', self.observer.errors)
        self.observer.errors.clear()
        with patch.object(runtime, 'process_identity', side_effect=FileNotFoundError): self.observer._checkpoint('before-cleanup')
        self.assertIn('transient process not sampled', self.observer.errors)

class RuntimeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.trace = []; self.observer = Mock()
        self.observer.checkpoint.side_effect = lambda stage:self.trace.append(stage)
        self.observer.finish.side_effect = lambda clean:self.trace.append(('finish',clean))
        self.process = Mock(pid=12345); self.process.poll.return_value = None

    def session(self):
        session = gui.NativeSession.__new__(gui.NativeSession)
        session.observer = self.observer; session.process = self.process; session.session = 'session'; session.base = 'http://127.0.0.1:1'; session.log = Mock()
        session.execute = Mock(side_effect=lambda *args:self.trace.append('quit'))
        return session

    def startup_environment(self):
        (self.root/'.linux-startup-disposable').touch()
        env = {key:str(self.root) for key in ('HOME','XDG_CONFIG_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR')}
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/fixture-bus'
        argv = ['startup','--app','/usr/bin/true','--output',str(self.root),'--case','diagnose-no-bus','--seconds','1']
        return env, argv

    def test_native_observer_attaches_before_webdriver_starts_product(self):
        self.observer.attach.side_effect = lambda process:self.trace.append(('attach',process))
        def request(url, *args, **kwargs):
            self.trace.append(url.rsplit('/',1)[-1]); return {'value':{'sessionId':'s'}}
        with patch.object(gui.subprocess,'Popen',return_value=self.process), patch.object(gui,'wait_for'), patch.object(gui,'request',side_effect=request), patch.object(gui.NativeSession,'call'):
            session = gui.NativeSession(Path('app'),Path('driver'),self.root,1,observer=self.observer)
        self.assertEqual(self.trace[:2], [('attach',self.process),'session']); session.log.close()

    def test_constructor_failure_closes_observer_and_preserves_original_error(self):
        with patch.object(gui.subprocess,'Popen',return_value=self.process), patch.object(gui,'wait_for',side_effect=ValueError('original constructor')), patch.object(gui.os,'killpg',side_effect=OSError('cleanup')):
            with self.assertRaisesRegex(ValueError, 'original constructor') as caught:
                gui.NativeSession(Path('app'),Path('driver'),self.root,1,observer=self.observer)
        self.observer.finish.assert_called_once_with(False)
        self.assertIn('cleanup failed', caught.exception.__notes__[0])
        self.observer.reset_mock(); self.observer.attach.side_effect = KeyboardInterrupt()
        with patch.object(gui.subprocess,'Popen',return_value=self.process), patch.object(gui.os,'killpg') as kill:
            with self.assertRaises(KeyboardInterrupt): gui.NativeSession(Path('app'),Path('driver'),self.root,2,observer=self.observer)
        kill.assert_called_once_with(self.process.pid,signal.SIGTERM)
        self.observer.finish.assert_called_once_with(True)

    def test_term_kill_and_webdriver_cleanup_order_is_preserved(self):
        session = self.session()
        self.process.wait.side_effect = [subprocess.TimeoutExpired('driver',5), None]
        with patch.object(gui.time,'sleep'), patch.object(gui,'request',side_effect=lambda *a,**k:self.trace.append(k['method'])), patch.object(gui.os,'killpg',side_effect=lambda pid,sig:self.trace.append(sig)):
            session.close()
        self.assertEqual(self.trace, ['before-cleanup','quit','DELETE',signal.SIGTERM,signal.SIGKILL,('finish',True)])
        session.log.close.assert_called_once()

    def test_already_exited_process_never_authorizes_reused_pid_cleanup(self):
        session = self.session(); self.process.poll.return_value = 0
        with patch.object(gui.os,'killpg') as kill: session.close()
        kill.assert_not_called()
        observer = runtime.Observer(binding(),self.root/'r.json','native-1')
        observer.attach(self.process); self.assertIn('anchor already exited',observer.errors)
        self.assertIsNone(observer.worker)
        leader = subprocess.Popen([sys.executable,'-c','import subprocess; p=subprocess.Popen(["/usr/bin/sleep","30"]); print(p.pid,flush=True)'],start_new_session=True,stdout=subprocess.PIPE,text=True)
        child = int(leader.stdout.readline()); leader.stdout.close(); leader.wait(timeout=5)
        env, argv = self.startup_environment()
        try:
            with patch.object(startup.subprocess,'Popen',return_value=leader), patch.object(runtime,'configured',return_value=None), patch.dict(os.environ,env), patch.object(sys,'argv',argv):
                with self.assertRaises(SystemExit): startup.main()
            shared.wait_for_fixture_exit(child)
            with self.assertRaises((FileNotFoundError,ProcessLookupError)): runtime.process_identity(child)
        finally:
            try: os.kill(child,signal.SIGKILL)
            except ProcessLookupError: pass

    def test_final_mapping_precedes_appimage_mount_teardown(self):
        session = self.session()
        with patch.object(gui.time,'sleep'), patch.object(gui,'request'), patch.object(gui.os,'killpg',side_effect=lambda *a:self.trace.append('mount-teardown')):
            session.close()
        self.assertLess(self.trace.index('before-cleanup'), self.trace.index('quit'))
        self.assertLess(self.trace.index('before-cleanup'), self.trace.index('mount-teardown'))

    def test_first_session_finalizes_before_second_session_attaches(self):
        first = self.session()
        with patch.object(gui.time,'sleep'), patch.object(gui,'request'), patch.object(gui.os,'killpg'): first.close()
        self.trace.append('attach-second')
        self.assertLess(self.trace.index(('finish',True)),self.trace.index('attach-second'))
        source = inspect.getsource(native.run)
        self.assertLess(source.index('session.close(); session = None'),source.index("'runtime-provenance-2.json'"))

    def test_optional_observer_preserves_historical_linux_and_windows_calls(self):
        for system in ('linux','win32'):
            with patch.object(adapter.sys,'platform',system), patch.object(adapter.gui,'NativeSession') as linux, patch.object(adapter,'WindowsNativeSession') as windows:
                factory = linux if system == 'linux' else windows
                adapter.session('app','driver','out',1); factory.assert_called_once_with('app','driver','out',1)
                factory.reset_mock(); adapter.session('app','driver','out',2,observer=self.observer)
                expected = {'observer':self.observer} if system == 'linux' else {}
                factory.assert_called_once_with('app','driver','out',2,**expected)

    def test_cleanup_uncertainty_is_sticky_and_blocks_provenance_success(self):
        observer = runtime.Observer(binding(),self.root/'receipt.json','native-1')
        observer.finish(False); observer.finish(True)
        receipt = json.loads((self.root/'receipt.json').read_text())
        self.assertFalse(receipt['cleanup_completed']); self.assertIn('cleanup uncertain',receipt['errors'])
        with self.assertRaisesRegex(ValueError,'incomplete'): runtime.verify_receipt(receipt,binding(),'native-1')

    def test_timeout_signal_and_cancellation_join_observer_and_close_descriptors(self):
        process = subprocess.Popen(['/usr/bin/sleep','30'])
        self.addCleanup(lambda: process.poll() is None and (process.terminate(),process.wait(timeout=5)))
        observer = runtime.Observer(binding(),self.root/'receipt.json','startup-fixture')
        observer.attach(process); observer.checkpoint('before-cleanup')
        self.assertIsNone(observer.worker)
        process.terminate(); process.wait(timeout=5); observer.finish(True)
        self.assertTrue(observer.finished); self.assertTrue(observer.stopped)
        stalled = runtime.Observer(binding(), self.root/'stalled.json','native-1')
        worker = Mock(pid=999,exitcode=-15); stalled.worker = worker; worker.is_alive.return_value = False
        with patch.object(runtime,'wait_for_worker',return_value=[]), patch.object(os,'getpgid',return_value=999), patch.object(os,'killpg') as kill:
            stalled._stop_worker()
        self.assertEqual([call.args for call in kill.call_args_list],[(999,signal.SIGTERM),(999,signal.SIGKILL)])
        worker.close.assert_called_once(); worker.join.assert_called_once_with(timeout=2)
        self.assertIn('observer cleanup timeout',stalled.errors)
        context = runtime.multiprocessing.get_context('spawn'); receiver, sender = context.Pipe(False)
        partial = runtime.Observer(binding(),self.root/'partial.json','native-1',{})
        product = subprocess.Popen(['/usr/bin/sleep','30'],env={'PATH':'/usr/bin:/bin'}); self.addCleanup(lambda: product.poll() is None and (product.terminate(),product.wait(timeout=5)))
        anchor = runtime.process_identity(product.pid); partial.process = product
        partial.worker = context.Process(target=shared.signal_partial_fixture,args=(binding(),partial.output,partial.phase,{},None,anchor,partial.started,receiver))
        partial.worker.start(); receiver.close(); partial.control = sender
        sender.send_bytes(json.dumps(['native-ready',time.monotonic()]).encode())
        deadline = time.monotonic()+5
        while not partial.output.with_suffix('.sampling').exists() and time.monotonic()<deadline: time.sleep(.01)
        self.assertTrue(partial.output.with_suffix('.sampling').exists())
        wait = runtime.wait_for_worker; started = time.monotonic()
        with patch.object(runtime,'wait_for_worker',side_effect=lambda handles,timeout:wait(handles,.05 if timeout==10 else timeout)): partial._stop_worker()
        self.assertLess(time.monotonic()-started,6); product.terminate(); product.wait(timeout=5); partial.finish(True)
        receipt = json.loads(partial.output.read_text()); self.assertTrue(receipt['samples']); self.assertTrue(receipt['progress'])
        progress = json.loads(partial.output.with_suffix('.progress').read_text()); self.assertFalse(progress['complete']); self.assertEqual(progress['progress'],receipt['progress']); self.assertLess(partial.output.with_suffix('.progress').stat().st_size,65536)
        self.assertIn('observer cleanup timeout',receipt['errors']); self.assertIn('observer exited without final capture',receipt['errors'])
        self.assertLess(partial.output.stat().st_size,runtime.LIMITS['evidence_bytes']); self.assertEqual(receipt['progress']['pid'],product.pid)
        self.assertTrue(receipt['cleanup_completed'])
        with self.assertRaisesRegex(ValueError,'incomplete'): runtime.verify_receipt(receipt,binding(),'native-1')

        context = runtime.multiprocessing.get_context('spawn'); receiver, sender = context.Pipe(False)
        grouped = runtime.Observer(binding(),self.root/'grouped.json','native-1')
        grouped.worker = context.Process(target=query_group_fixture,args=(sender,)); grouped.worker.start(); sender.close()
        self.assertTrue(receiver.poll(5)); query_pid = receiver.recv(); receiver.close()
        original_wait = runtime.wait_for_worker
        try:
            with patch.object(runtime,'wait_for_worker',side_effect=lambda handles,timeout:original_wait(handles,min(timeout,.05))): grouped._stop_worker()
            self.assertIsNone(grouped.worker)
            with self.assertRaises((FileNotFoundError,ProcessLookupError)): runtime.process_identity(query_pid)
        finally:
            try: os.kill(query_pid,signal.SIGKILL)
            except ProcessLookupError: pass
        for operation in (KeyboardInterrupt(),SystemExit(143)):
            session = self.session(); session.execute.side_effect = operation
            with patch.object(gui.os,'killpg'), self.assertRaises(type(operation)): session.close()
            self.observer.finish.assert_called_with(True)
        session = self.session(); self.process.wait.side_effect = TimeoutError()
        with patch.object(gui.time,'sleep'), patch.object(gui,'request'), patch.object(gui.os,'killpg'), self.assertRaises(TimeoutError): session.close()
        self.observer.finish.assert_called_with(False)
        fixture = self.root/'signal_fixture.py'
        fixture.write_text(shared.SIGNAL_LIFECYCLE_FIXTURE.replace('SCRIPTS',repr(str(Path(runtime.__file__).parent))))
        for mode in ('sleep','default-join','custom-join'):
            receipt = self.root/(mode+'.json')
            child = subprocess.Popen([sys.executable,str(fixture),mode,str(receipt)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline(),'ready\n')
                if mode == 'sleep': child.send_signal(signal.SIGTERM)
                out, error = child.communicate(timeout=20)
                self.assertEqual(child.returncode,42 if mode == 'custom-join' else -signal.SIGTERM,error)
                self.assertTrue(all(json.loads(receipt.with_suffix('.state').read_text()).values()))
                self.assertTrue(json.loads(receipt.read_text())['cleanup_completed'])
            finally:
                if child.poll() is None: child.kill(); child.wait(timeout=5)
                child.stdout.close(); child.stderr.close()

    def test_runtime_receipt_failure_does_not_replace_behavior_failure(self):
        self.observer.checkpoint.side_effect = OSError('observer failure')
        session = self.session(); session.execute.side_effect = AssertionError('behavior failure')
        with patch.object(gui.os,'killpg'), self.assertRaisesRegex(AssertionError,'behavior failure'): session.close()
        self.observer.fail.assert_called_once()
        observer = runtime.Observer(binding(),self.root/'absent'/'receipt.json','native-1')
        observer.finish(True); self.assertIn('FileNotFoundError',observer.errors)
        self.observer.checkpoint.side_effect = KeyboardInterrupt('cancel during observer stop')
        session = self.session()
        with patch.object(gui.os,'killpg') as kill, self.assertRaisesRegex(KeyboardInterrupt,'cancel during observer stop'): session.close()
        kill.assert_called_once_with(self.process.pid,signal.SIGTERM)
        session.log.close.assert_called_once(); self.observer.finish.assert_called_with(True)

    def test_stage_checkpoint_failure_does_not_replay_or_skip_native_actions(self):
        tree = ast.parse(inspect.getsource(native.run)); node = next(n for n in tree.body[0].body if isinstance(n,ast.FunctionDef) and n.name=='passed')
        scope = dict(evidence={'tests':[]},TEST_NAMES=['one','two'],runtime=runtime,observer=self.observer)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual passed hook>','exec'),scope)
        self.observer.checkpoint.side_effect = OSError('observer failure')
        scope['passed'](0); scope['passed'](1)
        self.assertEqual(scope['evidence']['tests'],[dict(name='one',passed=True),dict(name='two',passed=True)])
        self.assertEqual(self.observer.checkpoint.call_count,2)

    def test_startup_observer_attaches_to_live_popen_before_observation_loop(self):
        source = inspect.getsource(startup.main)
        self.assertLess(source.index('process = subprocess.Popen'),source.index("'attach', process"))
        self.assertLess(source.index("'attach', process"),source.index('while time.monotonic() - start'))
        self.assertLess(source.index("'before-cleanup'"),source.index('os.killpg(process.pid, signal.SIGTERM)'))
        self.assertIn("'finish', cleanup_completed",source)
        env, argv = self.startup_environment()
        with patch.object(startup.subprocess,'Popen') as launch, patch.object(runtime,'configured',side_effect=ValueError('projection rejected')), patch.dict(os.environ,env), patch.object(sys,'argv',argv), patch.object(startup.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'projection rejected'): startup.main()
        launch.assert_not_called(); kill.assert_not_called(); self.process.wait.assert_not_called()
        self.observer.attach.side_effect = KeyboardInterrupt('during attach')
        with patch.object(startup.subprocess,'Popen',return_value=self.process), patch.object(runtime,'configured',return_value=self.observer), patch.dict(os.environ,env), patch.object(sys,'argv',argv), patch.object(startup.os,'killpg') as kill:
            with self.assertRaisesRegex(KeyboardInterrupt,'during attach'): startup.main()
        self.assertEqual([call.args for call in kill.call_args_list],[(self.process.pid,signal.SIGTERM),(self.process.pid,signal.SIGKILL)])
        self.process.wait.assert_called_once_with(timeout=5)

if __name__ == '__main__': unittest.main(verbosity=2)
