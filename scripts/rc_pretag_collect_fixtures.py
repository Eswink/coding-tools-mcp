"""Hermetic pre-tag fixture: real Git, reviewed source and real bundle validators.

Every payload is synthetic data. No remote request, release or native run occurs.
The only source-gate seam supplies its existing isolated-fixture baseline.
"""
from contextlib import contextmanager
import copy
from email.message import Message
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
import urllib.error

import rc_consumer_snapshot as snapshot
from rc_consumer_fixtures import ConsumerFixture, write_json, write_lock
from rc_consumer_plan_tests import API as BundleAPI, zip_bytes
from rc_consumer_transport_tests import Opener, Response, URL
import rc_pretag_admission as admission
import rc_pretag_types as types
from source_provenance_gate_tests import command, commit

WORKFLOW = '.github/workflows/rc-pretag-evidence.yml'
JOB_NAME = 'Collect pre-tag FINAL evidence (release remains blocked)'
OWN_RUN, OWN_ATTEMPT, OWN_JOB, OWN_WORKFLOW = 900, 3, 9001, 20
FINAL_BRANCH = 'release/full-rc-candidate-fixture'

def git_environment(env=None):
    """Child-only Git isolation; preserve explicit empty input and non-Git keys."""
    clean = {key: value for key, value in (os.environ if env is None else env).items()
             if not key.startswith('GIT_')}
    clean.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                 GIT_CONFIG_NOSYSTEM='1', GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0')
    return clean


class OwnedGitScope:
    """Scoped fixture launch discipline, not containment of arbitrary Python code."""
    def __init__(self, temporary):
        self.roots = {}
        self.temporary_factory = tempfile.TemporaryDirectory
        self.executable = str(Path(shutil.which('git', path=os.defpath)).resolve())
        self.register(temporary)

    def register(self, temporary):
        root = Path(temporary.name).absolute()
        source = Path(__file__).resolve().parents[1]
        if (not isinstance(temporary, self.temporary_factory) or not temporary._finalizer.alive
                or root != root.resolve() or source.is_relative_to(root) or root.is_relative_to(source)
                or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid()):
            raise ValueError('fixture root is not an owned private temporary directory')
        self.roots[root] = (temporary, root.stat().st_dev, root.stat().st_ino)
        return temporary

    def temporary_directory(self, *args, **kwargs):
        return self.register(self.temporary_factory(*args, **kwargs))

    def __enter__(self):
        self.launch = subprocess.Popen
        outer = getattr(self.launch, '__self__', None)
        if isinstance(outer, OwnedGitScope):
            self.roots.update(outer.roots)
            self.launch = outer.launch
        self.patch = patch.object(subprocess, 'Popen', self._launch)
        self.patch.start()
        return self

    def __exit__(self, *error):
        self.patch.stop()

    def _cwd(self, cwd, initializing):
        if cwd is None:
            raise ValueError('fixture Git requires an explicit owned cwd')
        root = Path(cwd).absolute()
        owner = next((base for base in self.roots if root.is_relative_to(base)), None)
        if owner is None or root != root.resolve():
            raise ValueError('fixture Git cwd escaped ownership')
        temporary, device, inode = self.roots[owner]
        if not temporary._finalizer.alive or (owner.stat().st_dev, owner.stat().st_ino) != (device, inode):
            raise ValueError('fixture Git root lifetime ended')
        repository = next((p for p in (root, *root.parents) if p.is_relative_to(owner)
                           and ((p / '.git').exists() or (p / '.git').is_symlink())), None)
        if repository is None:
            if initializing:
                return root
            raise ValueError('fixture Git requires an independent repository')
        metadata = repository / '.git'
        if (not metadata.is_dir() or metadata.is_symlink()
                or any((metadata / p).exists() for p in ('commondir', 'objects/info/alternates'))
                or any(p.is_symlink() or (p.is_file() and p.stat().st_nlink != 1)
                       for p in metadata.rglob('*'))):
            raise ValueError('fixture Git metadata is shared or redirected')
        config = (metadata / 'config').read_text()
        if any(word in config.lower() for word in ('worktree', '[include', 'fsmonitor')):
            raise ValueError('fixture Git local configuration redirects context')
        return root

    def _launch(self, args, *positional, **kwargs):
        first = args[0] if isinstance(args, (list, tuple)) and args else args
        name = os.fsdecode(first).split()[0] if isinstance(first, (str, bytes, os.PathLike)) else ''
        override = Path(os.fsdecode(kwargs.get('executable') or '')).name
        if Path(name).name not in ('git', 'git.exe') and override not in ('git', 'git.exe'):
            return self.launch(args, *positional, **kwargs)
        if (positional or not isinstance(args, (list, tuple)) or kwargs.get('shell')
                or kwargs.get('executable') is not None or str(first) not in ('git', self.executable)):
            raise ValueError('ambiguous fixture Git launch')
        argv = [os.fspath(value) for value in args[1:]]
        cwd, config = kwargs.get('cwd'), []
        while argv and argv[0] in ('-C', '-c'):
            option, value, *argv = argv
            if option == '-C':
                cwd = Path(cwd or os.getcwd()) / value
            elif value.partition('=')[0] in ('user.name', 'user.email'):
                config.extend((option, value))
            else:
                raise ValueError('fixture Git configuration redirection')
        allowed = {'init', 'add', 'commit', 'tag', 'checkout', 'rev-parse', 'ls-files', 'ls-tree',
                   'status', 'diff', 'diff-tree', 'show', 'cat-file', 'merge-base', 'show-ref',
                   'rev-list', 'hash-object', 'mktree', 'commit-tree',
                   'read-tree', 'update-index', 'write-tree'}
        forbidden = ('--git-dir', '--work-tree', '--config-env', '--namespace', '--exec-path',
                     '--output', '--index-output', '--separate-git-dir', '--shared', '--template', '--ext-diff')
        if (not argv or argv[0] not in allowed or any(value.startswith(forbidden) for value in argv)
                or (argv[0] == 'init' and any(value not in ('-q', '--quiet') for value in argv[1:]))):
            raise ValueError('unreviewed fixture Git command')
        kwargs['cwd'] = str(self._cwd(cwd, argv[0] == 'init'))
        kwargs['env'] = git_environment(kwargs.get('env'))
        fixed = ['-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false']
        return self.launch([self.executable, *config, *fixed, *argv], **kwargs)


owned_git_scope = OwnedGitScope

def fixture_git_hostile(root):
    """Adversarial inherited inputs; all destinations are disposable sentinel data."""
    metadata = str(root / '.git')
    return dict(GIT_DIR=metadata, GIT_WORK_TREE=str(root), GIT_COMMON_DIR=metadata,
        GIT_INDEX_FILE=metadata + '/index', GIT_OBJECT_DIRECTORY=metadata + '/objects',
        GIT_ALTERNATE_OBJECT_DIRECTORIES=metadata + '/objects', GIT_CONFIG=metadata + '/config',
        GIT_CONFIG_GLOBAL=metadata + '/config', GIT_CONFIG_SYSTEM=metadata + '/config',
        GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0=str(root),
        GIT_CONFIG_KEY_1='core.hooksPath', GIT_CONFIG_VALUE_1=str(root),
        GIT_CONFIG_PARAMETERS="'core.bare=true'", GIT_CONFIG_NOSYSTEM='0',
        GIT_OPTIONAL_LOCKS='1', GIT_NO_REPLACE_OBJECTS='0', GIT_TEMPLATE_DIR=str(root))


class PreTagAPI(BundleAPI):
    """Exact-route deep-copy fake; unknown routes fail rather than contact a host."""
    def __init__(self, fixture, data):
        super().__init__(fixture, data)
        self.data['/']['id'] = types.REPOSITORY_ID
        artifact = self.data['/actions/artifacts/13']
        artifact['workflow_run'].update(repository_id=types.REPOSITORY_ID,
                                        head_repository_id=types.REPOSITORY_ID)
        self.data.pop('/git/ref/tags/v' + fixture.version)
        del self.candidate  # Never manufacture a post-tag consumer identity.
        self.tag_status, self.tag_response, self.tag_error = 404, None, None
        self.tag_bodies = []
        self.source, self.ref = fixture.sha, fixture.env['GITHUB_REF']
        repo = copy.deepcopy(self.data['/'])
        for branch in (self.ref.removeprefix('refs/heads/'), FINAL_BRANCH):
            self.data['/git/ref/heads/' + branch] = dict(
                ref='refs/heads/' + branch, object=dict(type='commit', sha=fixture.sha))
        self.data['/git/commits/' + fixture.sha] = dict(sha=fixture.sha, tree=dict(sha=fixture.tree))
        self.data['/actions/workflows/rc-pretag-evidence.yml'] = dict(
            id=OWN_WORKFLOW, path=WORKFLOW, state='active')
        run = dict(id=OWN_RUN, run_attempt=OWN_ATTEMPT, run_number=30, workflow_id=OWN_WORKFLOW,
            path=WORKFLOW, head_sha=fixture.sha, event='push',
            head_branch=self.ref.removeprefix('refs/heads/'), status='in_progress', conclusion=None,
            repository=repo, head_repository=copy.deepcopy(repo), created_at='2026-10-01T00:03:00Z',
            run_started_at='2026-10-01T00:03:01Z', updated_at='2026-10-01T00:04:00Z')
        self.data[self.own_run_path()] = run
        self.data[self.own_attempt_path()] = copy.deepcopy(run)
        job = dict(id=OWN_JOB, name=JOB_NAME, run_id=OWN_RUN, run_attempt=OWN_ATTEMPT,
            head_sha=fixture.sha, status='in_progress', conclusion=None,
            started_at='2026-10-01T00:03:02Z', completed_at=None)
        self.data[self.own_jobs_path()] = dict(total_count=1, jobs=[job])

    @staticmethod
    def own_run_path():
        return f'/actions/runs/{OWN_RUN}'

    @staticmethod
    def own_attempt_path():
        return f'/actions/runs/{OWN_RUN}/attempts/{OWN_ATTEMPT}'

    @staticmethod
    def own_jobs_path():
        return f'/actions/runs/{OWN_RUN}/attempts/{OWN_ATTEMPT}/jobs?per_page=100&page=1'

    def tag_get(self, suffix):
        assert suffix == '/git/ref/tags/v' + self.expected['rc_version']
        self.calls.append(suffix)
        if self.tag_error is not None:
            raise self.tag_error
        if self.tag_response is not None:
            return copy.deepcopy(self.tag_response)
        body = io.BytesIO(b'SYNTHETIC-ERROR-BODY-MUST-NOT-LEAK')
        self.tag_bodies.append(body)
        raise urllib.error.HTTPError('https://api.github.com/synthetic', self.tag_status,
                                      'SYNTHETIC-REASON', Message(), body)


class PreTagFixture:
    """Real complete source plus synthetic API/ZIP suitable for collect()."""
    def __init__(self, base):
        self.base = Path(base)
        self.f = ConsumerFixture(self.base)
        self.root, self.version = self.f.root, self.f.version
        name = snapshot.gate.rc.PACKAGE
        write_json(self.root / 'package.json', dict(name=name, version=self.version))
        lock = json.loads((self.root / 'package-lock.json').read_text())
        lock.update(name=name, version=self.version)
        lock['packages'][''] = dict(name=name, version=self.version)
        write_json(self.root / 'package-lock.json', lock)
        (self.root / 'src-tauri/Cargo.toml').write_text(
            f'[package]\nname="{name}"\nversion="{self.version}"\n')
        self.f.noncloud_locks['desktop']['package'].append(dict(name=name, version=self.version))
        write_lock(self.root / 'src-tauri/Cargo.lock', self.f.noncloud_locks['desktop'])
        write_json(self.root / 'src-tauri/tauri.conf.json', dict(version=self.version))
        for workflow in (WORKFLOW, snapshot.CONSUMER_WORKFLOW):
            path = self.root / workflow
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('name: Synthetic source identity fixture\non: push\n')
        self.baseline = commit(self.root)
        write_json(self.root / snapshot.gate.reviewed.MANIFEST, dict(schema=1,
            base_commit=self.baseline, version=self.version,
            review_reference='Isolated synthetic pre-tag fixture; never approval', entries=[]))
        self.sha = self.source = commit(self.root)
        self.tree = command(self.root, 'rev-parse', 'HEAD^{tree}')
        self.ref = 'refs/heads/release/rc-pretag-' + self.version + '-Fixture01'
        self.runner_temp = self.base / 'runner-temp'
        self.runner_temp.mkdir(mode=0o700)
        self.control = self.runner_temp / 'github-output'
        self.control.touch(mode=0o600)
        self.env = dict(GITHUB_ACTIONS='true', RUNNER_OS='Linux', GITHUB_JOB='collect',
            GITHUB_EVENT_NAME='push', GITHUB_REPOSITORY=types.REPOSITORY,
            GITHUB_REPOSITORY_ID=str(types.REPOSITORY_ID), GITHUB_SHA=self.sha,
            GITHUB_WORKFLOW_SHA=self.sha, GITHUB_WORKFLOW_REF=types.REPOSITORY + '/' + WORKFLOW + '@' + self.ref,
            GITHUB_REF=self.ref, GITHUB_RUN_ID=str(OWN_RUN), GITHUB_RUN_ATTEMPT=str(OWN_ATTEMPT),
            RUNNER_TEMP=str(self.runner_temp), GITHUB_OUTPUT=str(self.control))
        self.f.sha, self.f.tree = self.sha, self.tree
        self.f.producer.source_sha, self.f.producer.source_tree = self.sha, self.tree
        self.f.producer.repository_id = types.REPOSITORY_ID
        self.f.expected.update(source_sha=self.sha, source_tree=self.tree)
        self.f.integration['run']['head_sha'] = self.sha
        self.f.integration_proof['source_sha'] = self.sha
        for job in self.f.integration['jobs']:
            job['head_sha'] = self.sha
        write_json(self.f.contracts / 'integration.json', self.f.integration_proof)
        write_json(self.f.cloud / 'integration.json', self.f.integration_proof)
        self.f.build_cloud()
        self.f.build_noncloud()
        self.f.build_installers()
        self.f.refresh_reports()
        self.data = zip_bytes(self.f.bundle)
        self.api = PreTagAPI(self, self.data)

    @property
    def integration(self):
        return self.f.integration

    @contextmanager
    def reviewed(self):
        original = snapshot.gate.reviewed.verify
        with patch.object(snapshot.gate.reviewed, 'verify', side_effect=lambda root, source:
                original(root, source, baseline=self.baseline)), \
             patch.object(snapshot.gate.GitHub, 'get', autospec=True,
                          side_effect=lambda api, suffix: api.tag_get(suffix)):
            yield self

    def opener(self, data=None):
        body = self.data if data is None else data
        return Opener(Response(302, headers=[('Location', URL)]),
                      Response(200, body, [('Content-Length', str(len(body)))]))

    def admit(self):
        with self.reviewed():
            return admission.admit(self.root, self.env, self.api)

    def capture(self):
        admitted = self.admit()
        expected = admission.discover(self.api, admitted)
        selection = snapshot._select_source_runs_for_identity(
            self.api, self.sha, types.REPOSITORY_ID, expected)
        metadata = snapshot.authenticate_bundle_metadata(self.api, selection, expected['artifact_id'])
        projection = dict(source_sha=self.sha, source_tree=self.tree, version=self.version)
        producer = snapshot.derive_final_producer(projection, selection, metadata)
        return admitted, expected, selection, metadata, producer

    def revalidate(self, captured):
        with self.reviewed():
            return admission.revalidate(self.api, self.root, self.env, *captured)
