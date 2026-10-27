"""Current-source ownership faults are synthetic; no fake fd reaches the kernel."""
import ast
import asyncio
from contextlib import ExitStack, nullcontext, redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).absolute().parents[1]
SECRET = 'synthetic-secret-/private/path'
CANCELLATIONS = (KeyboardInterrupt, SystemExit, asyncio.CancelledError)


class SyntheticOS:
    """Close attempts, modeled release and numeric reuse are separate facts."""
    def __init__(self):
        self.calls, self.attempts, self.released = [], [], []
        self.live, self.open_faults, self.close_faults, self.identity_faults = {}, {}, {}, {}
        self.next_fd, self.opens, self.foreign_closed = 100, 0, False
        self.close_hook = lambda fd: None
        self.path = SimpleNamespace(commonpath=os.path.commonpath, normpath=os.path.normpath, realpath=lambda p: p)
        self.fspath, self.geteuid = os.fspath, lambda: 501
        for name in dir(os):
            if name.startswith('O_'):
                setattr(self, name, getattr(os, name))

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        self.calls.append(('open', path, flags, mode, dir_fd))
        index, self.opens = self.opens, self.opens + 1
        if index in self.open_faults:
            raise self.open_faults[index]
        if not flags & self.O_DIRECTORY:
            raise AssertionError('leaf file or callback reached')
        if dir_fd is not None and dir_fd not in self.live:
            raise AssertionError('unowned synthetic parent')
        fd, self.next_fd = self.next_fd, self.next_fd + 1
        self.live[fd] = 'owned'
        return fd

    def close(self, fd):
        self.calls.append(('close', fd))
        self.attempts.append(fd)
        self.close_hook(fd)
        error, release, reuse = self.close_faults.pop(fd, (None, True, False))
        if release:
            self.foreign_closed |= self.live.pop(fd, None) == 'foreign'
            self.released.append(fd)
        if reuse:
            self.live[fd] = 'foreign'
        if error is not None:
            raise error

    def mkdir(self, name, mode, *, dir_fd):
        self.calls.append(('mkdir', name, mode, dir_fd))

    def fstat(self, fd):
        self.calls.append(('identity', fd))
        if fd in self.identity_faults:
            raise self.identity_faults[fd]
        return SimpleNamespace(st_dev=1, st_ino=fd, st_uid=501, st_mode=0o40700, st_nlink=1, st_size=0)


def load_current(model=None):
    path = ROOT / 'scripts/rc_consumer_io.py'
    module = ModuleType('private_current_ownership_io')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    module.os = model if model is not None else SyntheticOS()
    module.secrets = SimpleNamespace(token_hex=lambda n: 'a' * (n * 2))
    return module


class DirectoryOwnershipTests(unittest.TestCase):
    def fresh(self, created=False):
        module = load_current()
        root = module.PrivateRoot.__new__(module.PrivateRoot)
        root.fd, root.path, root._files = 900, Path('/owned'), {}
        root._dirs = {'a': (1, 101)} if created == 'mixed' else {} if created else {
            'a': (1, 101), 'a/b': (1, 102), 'a/b/c': (1, 103)}
        root._root = lambda: module.os.open('/', module.DIR_FLAGS)
        return module, module.os, root

    def failure(self, call, expected=None):
        with self.assertRaises(BaseException) as caught:
            call()
        if expected is not None:
            self.assertIs(caught.exception, expected)
        return caught.exception

    def handoff(self, parent=False, created=False, release=False, reuse=False, depth=0, error=None, cleanup=None):
        module, model, root = self.fresh(created)
        error = error or OSError(SECRET)
        model.close_faults[100 + depth] = (error, release, reuse)
        if cleanup is not None:
            model.close_faults[101 + depth] = (cleanup, release, False)
        call = (lambda: root._parent('a/b/c/leaf', create=created)) if parent else lambda: module._directory('/a/b/c')
        caught = self.failure(call, cleanup or error)
        self.assertEqual(model.attempts, list(range(100, 102 + depth)))
        self.assertEqual(model.opens, depth + 2)
        self.assertFalse(model.foreign_closed)
        self.assertEqual(model.live.get(100 + depth), 'foreign' if reuse else None if release else 'owned')
        if cleanup is not None:
            self.assertIs(caught.__context__, error)
        return module, model, root

    def constructor(self, identity=None, faults=None):
        module = load_current()
        model, root = module.os, module.PrivateRoot.__new__(module.PrivateRoot)
        if identity is not None:
            model.identity_faults[101] = identity
        model.close_faults.update(faults or {})
        return module, model, root, lambda: module.PrivateRoot.__init__(root, '/', source_root='/source')

    def constructor_failure(self, identity=None, faults=None, attempts=(101, 100), expected=None):
        module, model, root, call = self.constructor(identity, faults)
        error = self.failure(call)
        self.assertEqual(model.attempts, list(attempts))
        self.assertIsNone(root.fd)
        self.assertFalse(model.foreign_closed)
        if expected is not None:
            self.assertIs(error, expected)
        else:
            self.assertIsInstance(error, module.ConsumerError)
            self.assertEqual(error.code, 'unsafe_root_parent')
        return error, model

    def test_directory_root_returns_owner(self):
        module = load_current()
        self.assertEqual(module._directory('/'), 100)
        self.assertEqual(module.os.attempts, [])
        self.assertEqual(module.os.live, {100: 'owned'})

    def test_directory_nested_success(self):
        module = load_current()
        self.assertEqual(module._directory('/a/b'), 102)
        self.assertEqual(module.os.attempts, [100, 101])
        self.assertEqual(module.os.live, {102: 'owned'})

    def test_directory_root_open_failure(self):
        module = load_current(); error = OSError(SECRET)
        module.os.open_faults[0] = error
        self.failure(lambda: module._directory('/a'), error)
        self.assertEqual((module.os.attempts, module.os.live), ([], {}))

    def test_directory_child_open_failure(self):
        module = load_current(); error = OSError(SECRET)
        module.os.open_faults[1] = error
        self.failure(lambda: module._directory('/a'), error)
        self.assertEqual(module.os.attempts, [100])

    def test_directory_close_failure_before_release(self):
        self.handoff()

    def test_directory_close_failure_after_release(self):
        self.handoff(release=True)

    def test_directory_close_failure_reused_number(self):
        self.handoff(release=True, reuse=True)

    def test_directory_deep_close_failure(self):
        for depth in (1, 2):
            self.handoff(depth=depth)

    def test_directory_baseexception_preserved(self):
        for kind in CANCELLATIONS:
            self.handoff(error=kind(SECRET))

    def test_directory_cleanup_close_failure(self):
        for release in (False, True):
            self.handoff(release=release, cleanup=RuntimeError('cleanup'))

    def test_parent_existing_success(self):
        _, model, root = self.fresh()
        self.assertEqual(root._parent('a/b/leaf'), (102, 'leaf'))
        self.assertEqual(model.attempts, [100, 101])
        self.assertEqual(model.live, {102: 'owned'})

    def test_parent_created_success(self):
        module, model, root = self.fresh(True)
        self.assertEqual(root._parent('a/leaf', create=True), (101, 'leaf'))
        self.assertEqual(root._dirs, {'a': (1, 101)})
        self.assertEqual(model.calls[1:], [('mkdir', 'a', 0o700, 100),
            ('open', 'a', module.DIR_FLAGS, 0o777, 100), ('identity', 101), ('close', 100)])

    def test_parent_close_failure_before_release(self):
        for created in (False, True):
            self.handoff(parent=True, created=created)

    def test_parent_close_failure_after_release(self):
        for created in (False, True):
            self.handoff(parent=True, created=created, release=True)

    def test_parent_close_failure_reused_number(self):
        for created in (False, True):
            self.handoff(parent=True, created=created, release=True, reuse=True)

    def test_parent_deep_close_failure(self):
        for created in (False, True, 'mixed'):
            self.handoff(parent=True, created=created, depth=2)

    def test_parent_child_open_failure(self):
        for created in (False, True):
            _, model, root = self.fresh(created); error = OSError(SECRET)
            model.open_faults[1] = error
            self.failure(lambda: root._parent('a/leaf', create=created), error)
            self.assertEqual(model.attempts, [100])

    def test_parent_existing_identity_failure(self):
        module, model, root = self.fresh()
        error = module.ConsumerError('private_directory_replaced')
        model.identity_faults[101] = error
        self.failure(lambda: root._parent('a/leaf'), error)
        self.assertEqual(model.attempts, [101, 100])

    def test_parent_baseexception_preserved(self):
        for created in (False, True):
            for kind in CANCELLATIONS:
                self.handoff(parent=True, created=created, error=kind(SECRET))

    def test_parent_cleanup_close_failure(self):
        for created in (False, True):
            self.handoff(parent=True, created=created, cleanup=RuntimeError('cleanup'))

    def test_public_reader_errors_are_sanitized(self):
        for name in ('read_bytes', 'read_prefix', 'hash_file', 'json_file', 'assert_private_tree'):
            module = load_current(); module.os.close_faults[100] = (OSError(SECRET), False, False)
            error = self.failure(lambda: getattr(module, name)('/a/leaf'))
            self.assertEqual(str(error), 'unsafe_private_io' if name == 'assert_private_tree' else 'unsafe_file_io')
            self.assertEqual(module.os.attempts, [100, 101])

    def test_public_private_errors_are_sanitized(self):
        for name in ('mkdir', 'read', 'write', 'copy'):
            module, model, root = self.fresh()
            module.open_file = lambda _: nullcontext(io.BytesIO(b'data'))
            model.close_faults[100] = (OSError(SECRET), False, False)
            args = ('a/leaf', b'data') if name == 'write' else ('a/leaf', '/source') if name == 'copy' else ('a/leaf',)
            error = self.failure(lambda: getattr(root, name)(*args))
            self.assertEqual(str(error), 'unsafe_private_io')
            self.assertEqual(model.attempts, [100, 101])

    def test_failed_handoff_never_reaches_file_or_callback(self):
        for private in (False, True):
            module, model, root = self.fresh(); body = Mock()
            model.close_faults[100] = (OSError(SECRET), True, True)
            def enter():
                with root.open('a/leaf') if private else module.open_file('/a/leaf'):
                    body()
            self.failure(enter)
            body.assert_not_called()
            self.assertEqual(model.opens, 2)
            self.assertFalse(model.foreign_closed)

    def test_returned_owner_and_root_close_are_consume_once(self):
        module, model, root = self.fresh()
        root.fd = module._directory('/')
        model.close_faults[100] = (OSError(SECRET), True, True)
        self.failure(root.close)
        self.assertIsNone(root.fd)
        root.close()
        self.assertEqual(model.attempts, [100])
        self.assertEqual(model.live, {100: 'foreign'})

    def test_parent_created_identity_failure_closes_child_then_parent(self):
        for kind in (ValueError, OSError, *CANCELLATIONS):
            module, model, root = self.fresh(True)
            error = module.ConsumerError('unsafe_private_directory') if kind is ValueError else kind(SECRET)
            model.identity_faults[101] = error
            self.failure(lambda: root._parent('a/leaf', create=True), error)
            self.assertEqual(model.attempts, [101, 100])
            self.assertEqual(root._dirs, {})
            self.assertEqual(model.opens, 2)

    def test_parent_created_identity_cleanup_failure_still_attempts_parent(self):
        for release in (False, True):
            for both, public in ((False, False), (True, False), (False, True)):
                module, model, root = self.fresh(True)
                identity, child, parent = ValueError('identity'), OSError(SECRET), RuntimeError('parent')
                model.identity_faults[101] = identity
                model.close_faults[101] = (child, release, release)
                if both: model.close_faults[100] = (parent, release, release)
                call = (lambda: root.mkdir('a')) if public else lambda: root._parent('a/leaf', create=True)
                error = self.failure(call, None if public else parent if both else child)
                if public: self.assertEqual(str(error), 'unsafe_private_io')
                self.assertIs(error.__context__, child if public or both else identity)
                self.assertEqual(model.attempts, [101, 100])
                self.assertFalse(model.foreign_closed)

    def test_constructor_success_publishes_root_after_parent_close(self):
        module, model, root, call = self.constructor()
        def observe(fd):
            self.assertIsNone(root.fd)
            self.assertEqual(root._dirs, {'': (1, 101)})
        model.close_hook = observe
        call()
        self.assertEqual((model.attempts, root.fd), ([100], 101))
        model.close_hook = lambda fd: None
        root.close(); root.close()
        self.assertEqual(model.attempts, [100, 101])

    def test_constructor_pre_root_failures_close_only_acquired_parent(self):
        for stage in ('validation', 'parent_open', 'realpath', 'token', 'mkdir', 'root_open'):
            module, model, root, call = self.constructor()
            error = OSError(SECRET)
            if stage == 'validation': call = lambda: module.PrivateRoot.__init__(root, 'relative')
            elif stage == 'parent_open': model.open_faults[0] = error
            elif stage == 'realpath': model.path.realpath = Mock(side_effect=error)
            elif stage == 'token': module.secrets.token_hex = Mock(side_effect=error)
            elif stage == 'mkdir': model.mkdir = Mock(side_effect=error)
            else: model.open_faults[1] = error
            result = self.failure(call)
            self.assertEqual(result.code, 'unsafe_absolute_path' if stage == 'validation' else 'unsafe_root_parent')
            self.assertEqual(model.attempts, [] if stage in ('validation', 'parent_open') else [100])
            self.assertIsNone(root.fd)

    def test_constructor_identity_failure_closes_root_then_parent(self):
        for original in (ValueError('identity'), load_current().ConsumerError('unsafe_private_directory')):
            self.constructor_failure(identity=original, expected=original)

    def test_constructor_final_parent_close_failure_cleans_root_without_retry(self):
        for release, reuse in ((False, False), (True, False), (True, True)):
            self.constructor_failure(faults={100: (OSError(SECRET), release, reuse)}, attempts=(100, 101))

    def test_constructor_root_cleanup_failure_still_attempts_parent(self):
        for child in (OSError(SECRET), RuntimeError('root')):
            for parent in (None, OSError(SECRET), RuntimeError('parent')):
                for original in (KeyboardInterrupt('identity'), None):
                    if original is None and parent is None: continue
                    faults = {101: (child, original is None, original is None)}
                    if parent is not None: faults[100] = (parent, True, True)
                    terminal = (parent or child) if original is not None else child
                    error, _ = self.constructor_failure(original, faults,
                        attempts=(101, 100) if original is not None else (100, 101),
                        expected=None if isinstance(terminal, OSError) else terminal)
                    context = error.__context__ if isinstance(terminal, OSError) else error
                    self.assertIs(context, terminal)
                    self.assertIs(terminal.__context__, (child if parent else original) if original else parent)

    def test_constructor_parent_cleanup_failure_never_retries_root(self):
        for release, reuse in ((False, False), (True, False), (True, True)):
            self.constructor_failure(ValueError('identity'), {100: (OSError(SECRET), release, reuse)})

    def test_constructor_cancellation_cleans_both_owned_descriptors(self):
        for kind in CANCELLATIONS:
            original = kind(SECRET)
            self.constructor_failure(identity=original, expected=original)
            self.constructor_failure(faults={100: (original, True, True)}, attempts=(100, 101), expected=original)

    def test_constructor_public_codes_and_cleanup_precedence_are_bounded(self):
        import rc_artifact_consumer as consumer
        from rc_pretag_collection_result import Failure
        for faults in ({100: (OSError(SECRET), False, False)}, {101: (OSError(SECRET), False, False)}):
            identity = ValueError(SECRET) if 101 in faults else None
            module, model, root, call = self.constructor(identity, faults)
            error = self.failure(call)
            self.assertIsInstance(error, module.ConsumerError)
            self.assertEqual(str(error), 'unsafe_root_parent')  # M leaked raw final-parent OSError.
            output = io.StringIO()
            with patch.object(consumer, 'consume', side_effect=error), patch.object(consumer, 'ConsumerError', module.ConsumerError), \
                 patch.object(consumer.argparse.ArgumentParser, 'parse_args', return_value=SimpleNamespace()), \
                 patch.object(consumer.snapshot, 'GitHub'), redirect_stdout(output):
                self.assertEqual(consumer.main(), 1)
            for report in (output.getvalue(), Failure('output', error).encode().decode()):
                self.assertNotIn(SECRET, report)
                self.assertNotIn('Traceback', report)
                self.assertNotIn('__context__', report)


class HistoricalProofBoundaryTests(unittest.TestCase):
    def setUp(self):
        import rc_consumer_proof_fixtures as fixture
        import rc_consumer_default_worker_proof_tests as proof
        self.fixture, self.proof = fixture, proof

    def fixture_root(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); (root / 'scripts').mkdir()
        for name, data in self.fixture.read_buffers(ROOT).items():
            filename = self.fixture.FIXTURE if name == self.fixture.NAMES[0] else name + '.py'
            (root / 'scripts' / filename).write_bytes(data)
        return root

    def rejected_setup(self, root):
        case = unittest.TestCase(); case.h = SimpleNamespace(ROOT=root)
        with patch.object(self.fixture, 'TemporaryDirectory') as temporary, patch.object(Path, 'write_bytes') as write, \
             patch('builtins.compile') as compile_source:
            with self.assertRaises((OSError, ValueError)):
                self.fixture.install_historical(case)
            temporary.assert_not_called(); write.assert_not_called(); compile_source.assert_not_called()
        self.assertEqual(case.h.ROOT, root)

    def test_historical_fixture_requires_exact_io_bytes_before_execution(self):
        self.assertEqual(tuple(self.fixture.read_buffers(ROOT)), self.fixture.NAMES)
        for mutation in ('missing', 'truncated', 'over_limit', 'symlink', 'byte'):
            root = self.fixture_root(); path = root / 'scripts' / self.fixture.FIXTURE
            data = path.read_bytes(); path.unlink()
            if mutation == 'symlink': path.symlink_to(ROOT / 'scripts' / self.fixture.FIXTURE)
            elif mutation != 'missing': path.write_bytes(data[:-1] if mutation == 'truncated' else
                data + b'x' if mutation == 'over_limit' else b'!' + data[1:])
            self.rejected_setup(root)

    def test_historical_fixture_requires_c_transport_and_worker(self):
        for name in self.fixture.NAMES[1:]:
            root = self.fixture_root(); path = root / 'scripts' / (name + '.py')
            data = path.read_bytes(); path.write_bytes(b'!' + data[1:])
            self.rejected_setup(root)  # No earlier accepted buffer has been materialized.

    def test_historical_fixture_restores_root_and_modules(self):
        proof, fixture = self.proof, self.fixture
        saved = {n: sys.modules.get(n) for n in fixture.NAMES}
        case = proof.DefaultWorkerProofTests('test_01_import_and_discovery_are_inert')
        case.setUp(); owned = case.h.ROOT
        try:
            with case.production():
                sys.modules[fixture.NAMES[0]] = object()
        finally:
            case.doCleanups()
        self.assertEqual((case.h.ROOT, proof.ROOT), (ROOT, ROOT))
        self.assertFalse(owned.exists())
        self.assertEqual(saved, {n: sys.modules.get(n) for n in fixture.NAMES})
        for stage in ('temporary', 'write', 'patch', 'later'):
            case = proof.DefaultWorkerProofTests('test_01_import_and_discovery_are_inert')
            harness, owned = proof.load_harness(), []
            def temporary(**kwargs):
                result = tempfile.TemporaryDirectory(**kwargs); owned.append(Path(result.name)); return result
            with ExitStack() as stack:
                stack.enter_context(patch.object(proof, 'load_harness', return_value=harness))
                stack.enter_context(patch.object(fixture, 'TemporaryDirectory',
                    side_effect=OSError(SECRET) if stage == 'temporary' else temporary))
                if stage == 'write': stack.enter_context(patch.object(Path, 'write_bytes', side_effect=OSError(SECRET)))
                if stage == 'patch':
                    def fail_install():
                        harness.ROOT = Path('/partial-install')
                        raise OSError(SECRET)
                    patcher = Mock(); patcher.start.side_effect = fail_install
                    stack.enter_context(patch.object(fixture, 'patch', SimpleNamespace(object=lambda *a: patcher)))
                if stage == 'later': stack.enter_context(patch.object(proof.base64, 'b64decode', side_effect=OSError(SECRET)))
                result = unittest.TestResult(); case.run(result)
            self.assertEqual(len(result.errors), 1)
            self.assertEqual((harness.ROOT, proof.ROOT), (ROOT, ROOT))
            self.assertTrue(all(not path.exists() for path in owned))
            self.assertEqual(saved, {n: sys.modules.get(n) for n in fixture.NAMES})

    def test_historical_fixture_import_and_discovery_are_inert(self):
        path = ROOT / 'scripts/rc_consumer_proof_fixtures.py'; source = path.read_bytes()
        code = compile(source, str(path), 'exec'); module = ModuleType('inert_historical_fixture')
        with ExitStack() as stack:
            for target in ('builtins.open', 'os.open', 'tempfile.TemporaryDirectory', 'subprocess.Popen',
                           'socket.create_connection', 'http.client.HTTPSConnection', 'pathlib.Path.read_bytes'):
                stack.enter_context(patch(target, side_effect=AssertionError('unexpected I/O')))
            stack.enter_context(patch.object(os.environ, 'get', side_effect=AssertionError('environment')))
            stack.enter_context(patch.object(os.environ, 'pop', side_effect=AssertionError('credential')))
            exec(code, module.__dict__)
            self.assertEqual(unittest.defaultTestLoader.loadTestsFromModule(module).countTestCases(), 0)

    def test_historical24_test_bodies_are_preserved(self):
        tree = ast.parse((ROOT / 'scripts/rc_consumer_default_worker_proof_tests.py').read_bytes())
        methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
        digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
        self.assertEqual(len(methods), 24)
        self.assertEqual(digest('\n'.join(ast.dump(n) for n in methods)), '6f29e88208312c6173ecf26a9beccd8e99ee9f36015f79ac50bf207efe03c271')
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ROOT' for t in n.targets))
        self.assertEqual(digest(ast.dump(assignment)), '0937f4df7c88259d5f7c8c92af8f1b0837b65eedea1577fbe888a153bfc73125')
        production = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'production')
        self.assertEqual(digest(ast.dump(production)), '03c91fac639ccceec98adc431a10cbf806a07a14ea353550ef6a2395c83501e7')
        for path, expected in (('scripts/rc_consumer_default_worker_proof.py', '9adad4fc9e576889dea965424abcaea9b93b000e49908563d35753d480852f74'),
            ('.github/workflows/rc-artifact-default-worker-proof.yml', 'fa236d4a08d8641d90255c49fa7ac0e93707ebd35383d85f66f2e4f2923e8eef')):
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)

    def test_historical_loader_rejects_current_io(self):
        harness = self.proof.load_harness()
        buffers = {name: (ROOT / 'scripts' / (name + '.py')).read_bytes() for name in self.fixture.NAMES}
        self.assertNotEqual(hashlib.sha256(buffers['rc_consumer_io']).hexdigest(), harness.HASHES['rc_consumer_io'])
        with patch.dict(sys.modules):
            for name in self.fixture.NAMES: sys.modules.pop(name, None)
            with patch('builtins.exec') as execute, patch('subprocess.Popen') as worker, \
                 patch.object(harness, 'metadata_get') as api, patch('socket.create_connection') as network:
                with self.assertRaises(harness.ProofError) as caught: harness.load_production(buffers)
                self.assertEqual(caught.exception.code, 'source_rejected')
                for call in (execute, worker, api, network): call.assert_not_called()
            self.assertFalse(any(name in sys.modules for name in self.fixture.NAMES))


if __name__ == '__main__':
    unittest.main(verbosity=2)
