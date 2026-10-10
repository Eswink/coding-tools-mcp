"""Finite reap-safe process-group cleanup admission; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '13cd343d942b7a68912d42a8f9235c02ed647764'
M_TREE = 'f2be2e09cca27081cccad11d94ed29858b955df9'
M_PARENTS = ('649dc0fcb0bd299ebf7910e567e09c32b7962a9b', 'af5ca34eebe0a6c1c55153acdd1ef1855df037a9')
M_RAW = (1236, '7facd10b0d1d2bd44b1cecd637f99a9360acb404a8be5af86cd1731f36933e13')
PROFILE = 'scripts/rc_pretag_reap_safe_profile.py'
CASES = 'scripts/rc_pretag_reap_safe_cases.py'
DISPATCHER = 'scripts/rc_pretag_source_observation_profile.py'
WORKFLOW = '.github/workflows/issue88-publication-executor.yml'
CAPS = {
    '.github/workflows/issue88-publication-executor.yml': (197, 14),
    'docs/specs/issue88-reap-safe-group-cleanup/design.md': (36, 36),
    'docs/specs/issue88-reap-safe-group-cleanup/requirements.md': (35, 35),
    'docs/specs/issue88-reap-safe-group-cleanup/tasks.md': (9, 9),
    'scripts/Ubuntu原生验收v1.py': (409, 67),
    'scripts/linux_runtime_provenance.py': (462, 7),
    'scripts/rc_pretag_reap_safe_cases.py': (229, 229),
    'scripts/rc_pretag_reap_safe_profile.py': (143, 143),
    'scripts/rc_pretag_source_observation_cases.py': (353, 23),
    'scripts/rc_pretag_source_observation_profile.py': (188, 6),
}
BASE_PINS = {
    '.github/workflows/issue88-publication-executor.yml': ('100644', '34e98e1e96a7b512cc8d1ece398656801071f3f1', '1f189a8c69a2c074514d8872b486e7ea0bfcc5effb8a17e45aa8f1b5621c2e67', 16361, 187),
    'scripts/Ubuntu原生验收v1.py': ('100644', 'add9f36fdad5dbc8cc741036d7fcc79cec38f4c0', '54eaf719d486ddefd788e8e4c5cdfec49d911991d7e35e5774518e328e1f5c19', 19123, 358),
    'scripts/linux_runtime_provenance.py': ('100644', '2fce91a94a77ae9242c504792e64844453d8f6ba', 'f9c8be51aa9a0e449fada77059a2edf2cd22f9433871a8172463e0610b2bdf00', 30690, 457),
    'scripts/rc_pretag_source_observation_cases.py': ('100644', '59e60b91612fe9af4e58a0986885bbdba10a0c9c', '780d9beaddf8bc51ceebc7f89194a400d78e2dcf466dd0870164a3edb0deb9de', 31697, 352),
    'scripts/rc_pretag_source_observation_profile.py': ('100644', '17fff8168163360dbe72711a76aabc537f18f422', '4e8c449e65b41b8a84b5b8eca2ddfb850ad795fc156729fa7901c37f4e512a94', 90898, 182),
}
PRIOR_PINS = {
    '.github/workflows/issue88-publication-executor.yml': (('0bcc32d8c8cf8fe7ae1067bbb7b6cb7ea3fa686f', '7c04fe2a37ce4ad1f8e2dee685e71132ee9660b9acdd84beb678a7d35badefac'), ('2e287f38ffc6cbcdc9da82277bce9e1c25bc7a50', '377086ca7c6edb11fbace99c35340bb4147c2102123d96cd00ef3a3e196f0979'), ('6af82d85156eda76f2fd464a7bd72b1e78ea3e53', '451bbeffce17f243a9f3b02f7e91c03c847e92c62caa2c9d40a3062103354dac'), ('a61797b57dcba000d238dbd2c224247ec077cdbc', '28601d9ded709b55ccad36f966a106e2912d67c48ec47833b9b519e1524045dc'), ('a81e9404bae5e4a56599eb0455026c207acbdc27', 'ef64753deb51f2260812bf136ad4bca0d811bc84e61e601e80697fdef314181c'), ('c1deaabd33200ed0d4795f0e5380a9809192f39e', 'f072b9fd591b9990deb80d7f4d7e45750813f2bea62fd73d0d48b8b13c46d9d0'), ('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e'), ('d06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634'), ('e740760c079a8a831342b3f964f7430dd581002f', 'f0952d0a1238feee4d82f27ccdf725ca4e9cba87e6dedfd493fb2ea015234fd6'), ('e89d4431fa1490187c55970c8626d725c064e5f0', '4159a606e279f3e3b77814e0398f3dc36f302aa5d38f8aa5ca82af3dfca657df'), ('f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a'), ('f76a50f14444f1b1c5959fa27097a85d87bfe8b0', '1ba5c751af0b605efc3f6f8165aa9b97f13d3c93d973493b451cc7bca2c53cff')),
    'scripts/Ubuntu原生验收v1.py': (('02e6ab0b55df6cb6c64dee778d5eb8ed50a8b6a1', 'c90d86076546f8f9683c3616612668dcbaf8b89c4713ecd1ac4de789cfe3172b'), ('499c0154233e18f9ec8364d4e803d7ab519f874e', 'ea5f05ccb1e8dec38eb68d6423030e58417d5d642bc5224629af40534644500f'), ('73a9fd3d6b9bf0899b5a2fa78ebdc6d03110ebaa', '219f9cdb5c34e2c16710bd3df44257df597b7a68e10c2dad3578e69d376713fc'), ('89a473644901128c1322a518c0cc8c6539444c1c', 'fb11e355746a3d6567d7dec0093d87797cfb45e4ca42b2e6cbb1570071a7c551'), ('959b80cb833cc2dbf5d59a19d4e779b9b5e8c8bd', '29198d541e77b3e1706a8745fadb831fb7ad1c4feb1f2a5cc4003408ddd9e063'), ('9843382781c6bf228c5852828f8917eb3783e9f1', 'caed7d8e88adf4c6d3a5d4e32a01f61967d4c4af8ec219d154bc9881ea4ada41'), ('d6bfd083a16b537bf360254c444dfda0233b31a1', '85caa96a775000af07c4268a0e2758956fb1b2f86d3eeda20d3985ae77111c2c'), ('f2ed653f986fcc504d9933d9910d5414260fd9bf', '630112b1222c4d41567253ca295a77cef08fe2e52bb1efaed374edc5a87b058f')),
}
DELTA_LIMIT = 569
SOURCE_PINS = {
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'c1c4a6b8f8ac791d90738e457605f8726e850928', 'a962ff022b93166d358969de9d80a56ae54e27f4066d09915c5b110438f802ad', 17300, 197),
    'docs/specs/issue88-reap-safe-group-cleanup/design.md': ('100644', '11bda2d9b11fe05ad0616018a7893a6852eefa72', 'f604e9887d6f083dc6e7e2bb48a1d24220bdf43c67d61718601e96ddb3711f27', 2884, 36),
    'docs/specs/issue88-reap-safe-group-cleanup/requirements.md': ('100644', '291bfced8f2f0c7c49ba74b6e2596e82fe5d48e6', 'aea08726c8cbd0063f9cb72a63a3888383c493e1e397432952e76d3180da2c93', 2408, 35),
    'docs/specs/issue88-reap-safe-group-cleanup/tasks.md': ('100644', '1afadfb260333246719516148fc5e8598958211a', '24c61e9ec2532fb23183c19d6002241d2df950b40d68b0a44209fdfc93873d3e', 655, 9),
    'scripts/Ubuntu原生验收v1.py': ('100644', '66f0ba9e7ffdcc41512bf4707d70ec2a3faab100', '69d17739c54cc329e63e3d9ca8956e0b6770d688bf3d4c6d2e6f16d6601e93e8', 21367, 409),
    'scripts/linux_runtime_provenance.py': ('100644', 'a9fcb516fede2ae5a47e371cdf9a2d879bb87ff0', '168c36be6d8265138778ff6ff34a541c9b36a99b9748f0445a723190c4e1505b', 31190, 462),
    'scripts/rc_pretag_reap_safe_cases.py': ('100644', 'b178d4650680b9960effbe205b588335c9af5c67', 'b612689a25bb0ea6a4447c44c5cc04b6960095cac554ccf777c9572c2b4b4e6b', 12232, 229),
    'scripts/rc_pretag_source_observation_cases.py': ('100644', 'c07c66b53f43d3a86229010bc7d381b3c38736d7', 'cf129a6e729a89a3bddc4e00b7c7a4f2a711442adda78f8e125ab59db514170c', 32092, 353),
    'scripts/rc_pretag_source_observation_profile.py': ('100644', 'd1bb779787733af9696d7d12ba41b34c99394c8d', 'e25700106d9db2284bfe1bee8139744b6c412d6052213adaa83ea5db2b9c4cc5', 91224, 188),
}
FRAGMENTS = {
    '.github/workflows/issue88-publication-executor.yml': ((b"        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen four hundred twenty seven cases\n        shell: python\n", b"        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen four hundred thirteen cases\n        shell: python\n"), (b'              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_reap_safe_profile as profile; import rc_pretag_git_budget_cases as git_budget; import rc_pretag_windows_vm_cases as windows_vm\n              import rc_pretag_stage_retirement_cases as stage_retirement\n              import rc_pretag_source_observation_cases as source_observation\n              import rc_pretag_reap_safe_cases as reap_safe\n              import rc_pretag_integration_admission_cases as admission\n', b'              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_source_observation_profile as profile; import rc_pretag_git_budget_cases as git_budget; import rc_pretag_windows_vm_cases as windows_vm\n              import rc_pretag_stage_retirement_cases as stage_retirement\n              import rc_pretag_source_observation_cases as source_observation\n              import rc_pretag_integration_admission_cases as admission\n'), (b"              (evidence / 'source-before.json').write_text(json.dumps(binding, indent=2) + '\\n', encoding='utf-8')\n              names = reap_safe.inventory()\n              suite = unittest.defaultTestLoader.loadTestsFromNames(names)\n              loaded = [test.id() for test in c._flatten(suite)]\n              with (evidence / 'reap-safe-cases.log').open('w', encoding='utf-8') as output:\n                  result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=c.InventoryResult).run(suite)\n              receipt = {'loaded_ids': loaded, 'executed_ids': result.executed_ids, 'tests_run': result.testsRun,\n                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'reap-safe-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert reap_safe.execution_valid(loaded, result)\n              names = source_observation.inventory()\n", b"              (evidence / 'source-before.json').write_text(json.dumps(binding, indent=2) + '\\n', encoding='utf-8')\n              names = source_observation.inventory()\n")),
    'scripts/Ubuntu原生验收v1.py': ((b'            runtime.notify(observer, "checkpoint", "before-cleanup")\n            if self.session and self.process and leader_running(self.process):\n                try:\n', b'            runtime.notify(observer, "checkpoint", "before-cleanup")\n            if self.session and self.process and self.process.poll() is None:\n                try:\n'), (b'                    self.session = ""\n                    if self.process:\n                        # This process group was created by this test, never a disk-restored PID.\n                        stop_owned_group(self.process)\n                finally:\n', b'                    self.session = ""\n                    if self.process and self.process.poll() is None:\n                        # This process group was created by this test, never a disk-restored PID.\n                        os.killpg(self.process.pid, signal.SIGTERM)\n                        try:\n                            self.process.wait(timeout=5)\n                        except subprocess.TimeoutExpired:\n                            os.killpg(self.process.pid, signal.SIGKILL)\n                            self.process.wait(timeout=5)\n                finally:\n'), (b'                runtime.notify(observer, "finish", cleanup_completed)\n\n\ndef leader_running(process) -> bool:\n    """Non-reaping liveness check (WNOWAIT keeps an exited leader as a zombie)."""\n    return process.returncode is None and os.waitid(\n        os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None\n\n\ndef group_members(pgid: int) -> list[int]:\n    """Live (non-zombie) processes still in the group, other than the pinned leader."""\n    members = []\n    for entry in os.scandir("/proc"):\n        if not entry.name.isdigit() or int(entry.name) == pgid:\n            continue\n        try:\n            with open(f"/proc/{entry.name}/stat", "rb") as handle:\n                fields = handle.read().rsplit(b")", 1)[1].split()\n        except (FileNotFoundError, ProcessLookupError):\n            continue\n        if int(fields[2]) == pgid and fields[0] != b"Z":\n            members.append(int(entry.name))\n    return members\n\n\ndef stop_owned_group(process, term: float = 5.0, kill: float = 5.0) -> None:\n    """Signal the recorded group while the unreaped leader pins its id; reap the leader last."""\n    if process.returncode is not None:\n        # Already reaped: the group id may have been reused, so never signal it; never pass silently.\n        raise RuntimeError("native process group not cleanable: leader already reaped")\n    fd = os.pidfd_open(process.pid)\n    try:\n        def exited(budget: float) -> bool:\n            deadline = time.monotonic() + budget\n            while os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:\n                if time.monotonic() >= deadline:\n                    return False\n                time.sleep(0.05)\n            return True  # ChildProcessError above means someone else reaped it: fail closed.\n        if os.getpgid(process.pid) != process.pid:\n            raise RuntimeError("native leader does not own its process group")\n        for number, budget in ((signal.SIGTERM, term), (signal.SIGKILL, kill)):\n            try:\n                os.killpg(process.pid, number)  # SIGKILL always follows, reaching stragglers.\n            except ProcessLookupError:\n                pass\n            exited(budget)\n        if not exited(0):\n            raise RuntimeError("native process group cleanup timed out; leader left unreaped")\n        deadline = time.monotonic() + kill\n        while group_members(process.pid):\n            if time.monotonic() >= deadline:\n                raise RuntimeError("native process group members remain; leader left unreaped")\n            time.sleep(0.05)\n        process.wait(timeout=5)\n    finally:\n        os.close(fd)\n\n', b'                runtime.notify(observer, "finish", cleanup_completed)\n\n')),
    'scripts/linux_runtime_provenance.py': ((b'                self.launch_environment, self.projection, self.anchor, self.started, receiver))\n            try: self.worker.start(); self.worker_fd = os.pidfd_open(self.worker.pid)\n            finally: receiver.close()\n', b'                self.launch_environment, self.projection, self.anchor, self.started, receiver))\n            try: self.worker.start()\n            finally: receiver.close()\n'), (b"                    try:\n                        # Held pidfd + WNOWAIT proves the leader is unreaped, so its pgid cannot be reused.\n                        fd = getattr(self, 'worker_fd', None)\n                        if fd is None: raise RuntimeError('observer pidfd missing')\n                        os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)\n                        if os.getpgid(worker.pid) == worker.pid: os.killpg(worker.pid, number)\n", b'                    try:\n                        if os.getpgid(worker.pid) == worker.pid: os.killpg(worker.pid, number)\n'), (b"        finally:\n            if getattr(self, 'worker_fd', None) is not None: os.close(self.worker_fd); self.worker_fd = None\n            self.stopped = True\n", b'        finally:\n            self.stopped = True\n')),
    'scripts/rc_pretag_source_observation_cases.py': ((b'import rc_pretag_source_observation_profile as x\nfrom rc_pretag_reap_safe_profile import normalize as reap_safe_bytes\n\n', b'import rc_pretag_source_observation_profile as x\n\n'), (b"        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob(reap_safe_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n", b"        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n"), (b"        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(self.good[x.PROFILE][2], c._blob(reap_safe_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))\n        for path, row in x.SOURCE_PINS.items():\n            data = reap_safe_bytes(path, (c.ROOT / path).read_bytes())\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n", b"        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(self.good[x.PROFILE][2], c._blob((c.ROOT / x.PROFILE).read_bytes()))\n        for path, row in x.SOURCE_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n"), (b'        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1844, 1844))\n        data = {path: reap_safe_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}\n        def budgets(git=c._git):\n', b'        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1844, 1844))\n        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}\n        def budgets(git=c._git):\n'), (b"        for path in x.BASE_PINS:\n            current, frozen = reap_safe_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)\n            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):\n", b"        for path in x.BASE_PINS:\n            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)\n            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):\n"), (b'                self.assertEqual(x.normalize(path, frozen), frozen, path)\n        current = reap_safe_bytes(x.DISPATCHER, (c.ROOT / x.DISPATCHER).read_bytes())\n        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))\n', b'                self.assertEqual(x.normalize(path, frozen), frozen, path)\n        current = (c.ROOT / x.DISPATCHER).read_bytes()\n        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))\n'), (b"        for path, fragments in x.FRAGMENTS.items():\n            current = reap_safe_bytes(path, (c.ROOT / path).read_bytes())\n            altered = [current + b'# outside\\n', b'\\xff']\n", b"        for path, fragments in x.FRAGMENTS.items():\n            current = (c.ROOT / path).read_bytes()\n            altered = [current + b'# outside\\n', b'\\xff']\n"), (b"        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *self.args)\n        runtime = ast.parse(reap_safe_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes()).decode())\n        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))\n", b"        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *self.args)\n        runtime = ast.parse((c.ROOT / x.PROFILE).read_text())\n        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))\n"), (b"            path = 'scripts/' + module + '.py'\n            current, frozen = reap_safe_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n", b"            path = 'scripts/' + module + '.py'\n            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n"), (b"            self.assertNotIn('scripts/rc_publication_stage.py', group.x.CAPS)\n            self.assertEqual(x.normalize('scripts/rc_publication_stage.py', reap_safe_bytes('scripts/rc_publication_stage.py', (c.ROOT / 'scripts/rc_publication_stage.py').read_bytes())),\n                             c._git('show', group.x.M + ':scripts/rc_publication_stage.py', root=self.repo))\n", b"            self.assertNotIn('scripts/rc_publication_stage.py', group.x.CAPS)\n            self.assertEqual(x.normalize('scripts/rc_publication_stage.py', (c.ROOT / 'scripts/rc_publication_stage.py').read_bytes()),\n                             c._git('show', group.x.M + ':scripts/rc_publication_stage.py', root=self.repo))\n"), (b'    def test_new44_inventory_early_runtime_workflow_and_exceptional_outcomes(self):\n        text = reap_safe_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()\n        frozen = self.frozen(x.WORKFLOW).decode()\n', b'    def test_new44_inventory_early_runtime_workflow_and_exceptional_outcomes(self):\n        text = (c.ROOT / x.WORKFLOW).read_text()\n        frozen = self.frozen(x.WORKFLOW).decode()\n')),
    'scripts/rc_pretag_source_observation_profile.py': ((b'    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    from rc_pretag_reap_safe_profile import normalize as reap_safe_bytes\n    current = reap_safe_bytes(path, current)\n    assert type(path) is str and type(current) is bytes, \'source_observation inverse input\'\n', b'    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'source_observation inverse input\'\n'), (b'    ref = o._commit(ref, root, git)\n    import rc_pretag_reap_safe_profile as reap_safe\n    selected = reap_safe.select(ref, root, git, entries, historical, release, release_tree, documents)\n    if selected is not None:\n        return selected\n    try:\n', b'    ref = o._commit(ref, root, git)\n    try:\n')),
}
NEW_CASES = {
    'rc_pretag_reap_safe_cases.ReapSafeCompositionCases': ('test_actual_m_identity_and_fresh_historical_validation', 'test_exact_ordered_d_i_j_selection', 'test_wrong_topology_delegates_without_content', 'test_extra_missing_and_changed_paths_reject', 'test_source_pins_and_caps_match_working_tree', 'test_normalize_restores_exact_m_bytes_and_rejects_drift'),
    'rc_pretag_reap_safe_cases.ReapSafeCleanupCases': ('test_straggler_killed_and_leader_reaped_last', 'test_exited_leader_still_pins_group_for_straggler_cleanup', 'test_reaped_leader_is_never_signalled', 'test_post_kill_timeout_fails_closed_without_reaping', 'test_leader_running_observes_without_reaping', 'test_close_uses_reap_safe_helpers_only', 'test_externally_reaped_observer_is_never_group_signalled', 'test_cleanup_has_no_poll_reap_before_group_signal'),
}
CLASS = 'rc_pretag_reap_safe_cases.ReapSafeCompositionCases'
DIGEST = 'f68b3cd73ea3bb978b04e83432df98558a9d976f3e0e212aeadb3ae80ebf5fb7'


def normalize(path, current):
    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""
    assert type(path) is str and type(current) is bytes, 'reap_safe inverse input'
    if path not in BASE_PINS:
        return current
    identity = o.pin(current)
    baseline = BASE_PINS[path]
    if identity == baseline[1:3] or identity in PRIOR_PINS.get(path, ()):
        return current
    row = SOURCE_PINS[path]
    assert (identity, len(current), len(current.splitlines())) == (row[1:3], row[3], row[4]), path
    restored = current
    for before, after in reversed(FRAGMENTS[path]):
        assert before and restored.count(before) == 1, 'reap_safe fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (
        baseline[1:3], baseline[3], baseline[4]), 'complete reap_safe M inverse'
    return restored

def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; no correction chains or ancestry inference."""
    if release != p.R:
        raise o.TopologyError('reap_safe_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('reap_safe_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('reap_safe_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('reap_safe_candidate_parent')
    return kind, tip, source

def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh immutable M admission, exact candidate pins and complete reviewed delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'reap_safe M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'reap_safe M tree'
    raw = git('cat-file', 'commit', M, root=root)
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == M_RAW, 'reap_safe M raw'
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(M, root) and len(baseline) == 1840
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 10 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() and len(BASE_PINS) == 5
    assert FRAGMENTS.keys() == BASE_PINS.keys() and PRIOR_PINS.keys() <= BASE_PINS.keys()
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1845
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    assert all(actual[path] == (row[0], 'blob', row[1]) for path, row in SOURCE_PINS.items())
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, count) in SOURCE_PINS.items():
        assert mode == '100644' and o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, count), path
    for path, row in BASE_PINS.items():
        assert baseline[path] == (row[0], 'blob', row[1]), path
        assert normalize(path, data[path]) == git('cat-file', 'blob', baseline[path][2], root=root), path
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'reap_safe_delta_budget')
    return actual

def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected and historical content errors escape."""
    ref = o._commit(ref, root, git)
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
