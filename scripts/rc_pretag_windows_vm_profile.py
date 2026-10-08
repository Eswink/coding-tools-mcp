"""Finite Windows engineering admission; independent full-tree review binds self."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

# Actual merged F identity, independently verified before source sealing.
M = '7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116'
M_TREE = '2862d635ab7ce082ad863d9315514537df8864f1'
M_PARENTS = ('8bdd5f327b4603c5570dc764e2d62fecbe6e02d2', '76949e7e496ee4a5a3a7554d26e2cd67691f07e0')
M_RAW = (1227, '38f560ddd99ace241b4925b558ddb386ec45f40fac111e9134a574be1f73901c')
PROFILE = 'scripts/rc_pretag_windows_vm_profile.py'
CASES = 'scripts/rc_pretag_windows_vm_cases.py'
DISPATCHER = 'scripts/rc_pretag_git_budget_profile.py'
WORKFLOW = '.github/workflows/issue88-publication-executor.yml'
CAPS = {
    '.github/workflows/issue88-publication-executor.yml': (185, 14),
    '.github/workflows/windows-vm-session.yml': (120, 120),
    'docs/specs/windows-vm-session/design.md': (100, 100),
    'docs/specs/windows-vm-session/requirements.md': (100, 100),
    'docs/specs/windows-vm-session/tasks.md': (100, 100),
    'scripts/prepare_windows_vm_session.ps1': (105, 105),
    'scripts/rc_pretag_git_budget_cases.py': (365, 24),
    'scripts/rc_pretag_git_budget_profile.py': (220, 6),
    'scripts/rc_pretag_windows_vm_cases.py': (450, 450),
    'scripts/rc_pretag_windows_vm_profile.py': (350, 350),
    'services/windows-vm-broker/channels_windows.go': (215, 215),
    'services/windows-vm-broker/guest_windows.go': (150, 150),
    'services/windows-vm-broker/inputs.json': (40, 40),
    'services/windows-vm-broker/main_windows.go': (190, 190),
    'services/windows-vm-broker/owner_windows.go': (330, 330),
    'services/windows-vm-broker/owner_windows_test.go': (480, 480),
    'services/windows-vm-broker/protocol_windows.go': (280, 280),
    'services/windows-vm-broker/quarantine_windows.go': (200, 200),
    'services/windows-vm-broker/upstream-defaults.patch': (12, 12),
    'src-tauri/src/tools/mod.rs': (50, 3),
    'src-tauri/src/tools/windows_vm.rs': (350, 350),
    'src-tauri/src/tools/windows_vm/native_tests.rs': (240, 240),
    'src-tauri/src/tools/windows_vm/protocol.rs': (495, 495),
    'src-tauri/src/tools/windows_vm/tests.rs': (480, 480),
}
BASE_PINS = {
    'src-tauri/src/tools/mod.rs': ('100644', '6a5b9645ac2bc9e53000a4f63e62644c4dcb99a4', '12aa6eb606677452b6a513437285134abceede13317d94fac5b9a47d31e6dfe5', 1462, 47),
    'scripts/rc_pretag_git_budget_profile.py': ('100644', '7c163dd6585ba762b3c0ab267b8bfe1c1911686a', '832a5a7fecc377bc41bbd1228092b3647082fab95dea03430e507dcfe7ca934b', 46420, 202),
    'scripts/rc_pretag_git_budget_cases.py': ('100644', '9b0fbd9c4818ec7bcdf448aafa6267b4d5e50817', '67b41b0e6a0443739c4b895dd5e79479203e096ff8180eb6d4b2227e141e59d4', 27799, 340),
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'c1deaabd33200ed0d4795f0e5380a9809192f39e', 'f072b9fd591b9990deb80d7f4d7e45750813f2bea62fd73d0d48b8b13c46d9d0', 14422, 168),
}
PRIOR_PINS = {
    '.github/workflows/issue88-publication-executor.yml': (('2e287f38ffc6cbcdc9da82277bce9e1c25bc7a50', '377086ca7c6edb11fbace99c35340bb4147c2102123d96cd00ef3a3e196f0979'), ('6af82d85156eda76f2fd464a7bd72b1e78ea3e53', '451bbeffce17f243a9f3b02f7e91c03c847e92c62caa2c9d40a3062103354dac'), ('a61797b57dcba000d238dbd2c224247ec077cdbc', '28601d9ded709b55ccad36f966a106e2912d67c48ec47833b9b519e1524045dc'), ('a81e9404bae5e4a56599eb0455026c207acbdc27', 'ef64753deb51f2260812bf136ad4bca0d811bc84e61e601e80697fdef314181c'), ('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e'), ('d06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634'), ('e740760c079a8a831342b3f964f7430dd581002f', 'f0952d0a1238feee4d82f27ccdf725ca4e9cba87e6dedfd493fb2ea015234fd6'), ('f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a'), ('f76a50f14444f1b1c5959fa27097a85d87bfe8b0', '1ba5c751af0b605efc3f6f8165aa9b97f13d3c93d973493b451cc7bca2c53cff'), ('e89d4431fa1490187c55970c8626d725c064e5f0', '4159a606e279f3e3b77814e0398f3dc36f302aa5d38f8aa5ca82af3dfca657df')),
}
DELTA_LIMIT = 4700
# BEGIN SEALED SOURCE
SOURCE_PINS = {
    '.github/workflows/issue88-publication-executor.yml': ('100644', '0bcc32d8c8cf8fe7ae1067bbb7b6cb7ea3fa686f', '7c04fe2a37ce4ad1f8e2dee685e71132ee9660b9acdd84beb678a7d35badefac', 15358, 177),
    '.github/workflows/windows-vm-session.yml': ('100644', '00e10dde869f9cd6e5f0f1e679c083e63c242335', 'dcb8b7fc11c7380faf742796cda46ed4b95cf89a201022ae9eaba2e95410fb42', 7669, 106),
    'docs/specs/windows-vm-session/design.md': ('100644', '3afad04da7531b0380c1b1106593d5ddd8b893ca', 'e0724f75f767971a8a48df3239c4dd3774b047f486e4e4aa915aea96be9a5fa8', 12799, 86),
    'docs/specs/windows-vm-session/requirements.md': ('100644', 'b054850c94265c7d6f0d3e780e60d8e1af790d08', 'd77515f73ce20081480abb15ee2f7c2cbc92dfd82bfab6b16fa6fa7f1dbcf45a', 8373, 94),
    'docs/specs/windows-vm-session/tasks.md': ('100644', 'bd1e6ecb6f8b263dca125f53f171a9dee26ee533', '1f58cdff8677b922fdf63e443286a9252cd20ba3a7156dbe84e663f2a80f8efb', 7170, 81),
    'scripts/prepare_windows_vm_session.ps1': ('100644', 'a38a7ee2a9627a0a45f123ae08b57de5018e6c5e', '58157c707608ed4e83055cb0fea9fa0083f424086cdf79055172becee98eae01', 7734, 97),
    'scripts/rc_pretag_git_budget_cases.py': ('100644', '62ab5b5522ac339cd735b7ae447e8980f231cc54', 'dd39d371def695eaac1b34217d23c0a0a63f7be72eba8887b4e2288a1bfae4f0', 28098, 341),
    'scripts/rc_pretag_git_budget_profile.py': ('100644', '9f1399e6454e2c9d0f75cd600ecf8cb9f50861d8', '5af4218d0acebbf6aa36cc4449450daeefaa548c1c78539e8c9e8bdbcff5e7a9', 46752, 208),
    'scripts/rc_pretag_windows_vm_cases.py': ('100644', '5c7f728f2a70ac8e064b270d3960fca41cd21443', 'baf41ff51213f5109cbad49570ec74a50c0784071ff85edcf41c7b0485271e13', 31655, 350),
    'services/windows-vm-broker/channels_windows.go': ('100644', '7465847b52ad8d820b7c0743ef742955308a7e9e', 'cb38b7dcdd809d2418a51b58860e908df1a4b9a7ca965f152d3fd19186c0b9c9', 6048, 212),
    'services/windows-vm-broker/guest_windows.go': ('100644', '82f249fb00aea1ef2d5db5866e3e117282532be9', '72b681ccd4f19eadbc9ff1fce7e1302c0848114ab71115e321ad337cba0cbc46', 4906, 135),
    'services/windows-vm-broker/inputs.json': ('100644', 'd7a0c5d717b77499bfbc821622873d3394c3f6f1', '32b8b25c35024830d09cd7257fcac4d05117820ef0850a96733445d804847850', 1783, 36),
    'services/windows-vm-broker/main_windows.go': ('100644', '2fa50dc729fe000b1c8564c0f753877f0ae077f1', '3ea09fa942a7b3e7f2a2a3bd611adaf43c8b4353887bfbd2788a5fe4326b4d20', 5027, 183),
    'services/windows-vm-broker/owner_windows.go': ('100644', 'a1dfab60b966f375e316ebcd22d3fcd35bfb8b92', 'b462eac0a390afac06b48d783a6cccaddcc550da1ee238214e13979647b9ff8c', 9834, 321),
    'services/windows-vm-broker/owner_windows_test.go': ('100644', '25b0a56d4d28bad9fbd3ccabd6436d528dfc726b', '1655256cad53f27bdf83714eb2bc99af7ebe69a05959bd022b13ee5938e948fa', 17057, 480),
    'services/windows-vm-broker/protocol_windows.go': ('100644', 'a84c37934000e72f88ac1658fc169b7bce415071', 'a03ae3062d397c3e9b1079077e3ed33904c684642798e003055ef01e5aafcdd1', 6969, 275),
    'services/windows-vm-broker/quarantine_windows.go': ('100644', '790243e13a58cbae58f042398ba7041180d90926', '6c7e4df40d2d274c2b522aa6612f31af907c95284b3a8cb894adbe976c7d51d7', 5139, 183),
    'services/windows-vm-broker/upstream-defaults.patch': ('100644', '8c64fa80f3767ef1dca1746d6f618372301bc0cd', 'baebb4177f2f972022dbef62299b81596fef0ee23d40b1bd8b4ad71e7f5290b0', 602, 12),
    'src-tauri/src/tools/mod.rs': ('100644', 'c38339b3654295539d1fe293f5a88710ebb6dd23', 'd6c2feb9e7e161188f10dd00fb66206b7c98c978f7d511c55904b798448041ea', 1546, 50),
    'src-tauri/src/tools/windows_vm.rs': ('100644', '5075599be11ba7e18030912c260bb3f08e8d1b59', 'bf003ec6d4afc3e1fa4edc6fb678ff9b876033074f1d494dd3af0a4032641c95', 10468, 317),
    'src-tauri/src/tools/windows_vm/native_tests.rs': ('100644', 'd4191eace9841157b3de6034df1f21313401facd', '45c16f4c1c1b9038bf4dc5f54f38959063738f3b3f568ba29fe9a10a7504161b', 9489, 236),
    'src-tauri/src/tools/windows_vm/protocol.rs': ('100644', 'c3b1ebe0d9662574a5dd9282b8f1e5393cbdb835', '2e71022fd52dc66b4df5df0bfed731290de8f2c40fa98b6a6325bddbdf779a01', 12719, 372),
    'src-tauri/src/tools/windows_vm/tests.rs': ('100644', '455a5f96dd5669593ff3605d331d2b091ccd0b0d', '88f3281578ad21ac756ed43e6f237606137fff78aa491df2fece32a642b098fc', 16540, 463),
}
FRAGMENTS = {
    'src-tauri/src/tools/mod.rs': ((b'pub mod policy;\npub mod registry;\npub mod session;\n#[cfg(windows)]\n#[cfg_attr(not(test), allow(dead_code))]\npub(crate) mod windows_vm;\npub mod workspace;\npub(crate) mod worktree_tools;\n\n', b'pub mod policy;\npub mod registry;\npub mod session;\npub mod workspace;\npub(crate) mod worktree_tools;\n\n'),),
    'scripts/rc_pretag_git_budget_profile.py': ((b'\ndef normalize(path, current):\n    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    from rc_pretag_windows_vm_profile import normalize as windows_vm_bytes\n    current = windows_vm_bytes(path, current)\n    assert type(path) is str and type(current) is bytes, \'git_budget inverse input\'\n    if path not in BASE_PINS:\n        return current\n', b'\ndef normalize(path, current):\n    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'git_budget inverse input\'\n    if path not in BASE_PINS:\n        return current\n'), (b'def select(ref, root, git, entries, historical, release, release_tree, documents):\n    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    import rc_pretag_windows_vm_profile as windows_vm\n    selected = windows_vm.select(ref, root, git, entries, historical, release, release_tree, documents)\n    if selected is not None:\n        return selected\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n    except o.TopologyError:\n', b'def select(ref, root, git, entries, historical, release, release_tree, documents):\n    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n    except o.TopologyError:\n')),
    'scripts/rc_pretag_git_budget_cases.py': ((b"import rc_pretag_staged_bytes_cases as staged\nimport rc_pretag_stage_retirement_cases as retirement\nimport rc_pretag_git_budget_profile as x\nfrom rc_pretag_windows_vm_profile import normalize as windows_vm_bytes\n\nF_BINDING = ('8bdd5f327b4603c5570dc764e2d62fecbe6e02d2', 'b75fdae6b9a2cb9589b51d832d7ba638384cb6b8', ('f0fdfba5cd48b7cad477f1e2cb77bb70153ad657', '33503cc901acc0619ca5658eff187efd7799b040'))\nCONSUMER = 'scripts/rc_artifact_consumer.py'\n", b"import rc_pretag_staged_bytes_cases as staged\nimport rc_pretag_stage_retirement_cases as retirement\nimport rc_pretag_git_budget_profile as x\n\nF_BINDING = ('8bdd5f327b4603c5570dc764e2d62fecbe6e02d2', 'b75fdae6b9a2cb9589b51d832d7ba638384cb6b8', ('f0fdfba5cd48b7cad477f1e2cb77bb70153ad657', '33503cc901acc0619ca5658eff187efd7799b040'))\nCONSUMER = 'scripts/rc_artifact_consumer.py'\n"), (b"        cls.addClassCleanup(cls._immutable_f.clear)\n    def setUp(self):\n        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob(windows_vm_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n        self.feature = self.commit([x.M, self.pure], self.good)\n        self.overlay = self.good | c.RELEASE_DOCS\n", b"        cls.addClassCleanup(cls._immutable_f.clear)\n    def setUp(self):\n        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n        self.feature = self.commit([x.M, self.pure], self.good)\n        self.overlay = self.good | c.RELEASE_DOCS\n"), (b"        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1803, 1813, 17, 7))\n        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(x.CAPS, {'scripts/rc_artifact_consumer.py': (260, 2), 'scripts/rc_consumer_contracts.py': (300, 12), 'scripts/release_dependency_contract.py': (300, 6), 'scripts/exact_build_audit.py': (480, 48), 'scripts/rc_consumer_fixed_git.py': (420, 420), 'scripts/rc_consumer_git_test_support.py': (120, 120), 'scripts/rc_consumer_fixed_git_cases.py': (225, 225), 'scripts/rc_consumer_git_supervisor_cases.py': (210, 210), 'scripts/rc_publication_git_budget_cases.py': (260, 260), x.DISPATCHER: (220, 6), ADAPTER: (380, 24), x.WORKFLOW: (175, 14), x.PROFILE: (350, 350), x.CASES: (450, 450), **{'docs/specs/issue88-fixed-git-budget/' + name + '.md': (cap, cap) for name, cap in (('requirements', 60), ('design', 90), ('tasks', 70))}})\n        self.assertEqual(self.good[x.PROFILE][2], c._blob(windows_vm_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))\n        for path, row in x.SOURCE_PINS.items():\n            data = windows_vm_bytes(path, (c.ROOT / path).read_bytes())\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n                changed = list(row); changed[index] = value\n", b"        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1803, 1813, 17, 7))\n        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(x.CAPS, {'scripts/rc_artifact_consumer.py': (260, 2), 'scripts/rc_consumer_contracts.py': (300, 12), 'scripts/release_dependency_contract.py': (300, 6), 'scripts/exact_build_audit.py': (480, 48), 'scripts/rc_consumer_fixed_git.py': (420, 420), 'scripts/rc_consumer_git_test_support.py': (120, 120), 'scripts/rc_consumer_fixed_git_cases.py': (225, 225), 'scripts/rc_consumer_git_supervisor_cases.py': (210, 210), 'scripts/rc_publication_git_budget_cases.py': (260, 260), x.DISPATCHER: (220, 6), ADAPTER: (380, 24), x.WORKFLOW: (175, 14), x.PROFILE: (350, 350), x.CASES: (450, 450), **{'docs/specs/issue88-fixed-git-budget/' + name + '.md': (cap, cap) for name, cap in (('requirements', 60), ('design', 90), ('tasks', 70))}})\n        self.assertEqual(self.good[x.PROFILE][2], c._blob((c.ROOT / x.PROFILE).read_bytes()))\n        for path, row in x.SOURCE_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n                changed = list(row); changed[index] = value\n"), (b"\n    def test_individual_and_aggregate_caps_reject(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2400, 2367))\n        data = {path: windows_vm_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'git_budget_delta_budget')\n        budgets()\n", b"\n    def test_individual_and_aggregate_caps_reject(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2400, 2367))\n        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'git_budget_delta_budget')\n        budgets()\n"), (b"        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())\n        self.assertEqual(len(x.FRAGMENTS), 7)\n        for path in x.BASE_PINS:\n            current, frozen = windows_vm_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)\n            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):\n                self.assertEqual(x.normalize(path, current), frozen, path)\n                self.assertEqual(x.normalize(path, frozen), frozen, path)\n", b"        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())\n        self.assertEqual(len(x.FRAGMENTS), 7)\n        for path in x.BASE_PINS:\n            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)\n            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):\n                self.assertEqual(x.normalize(path, current), frozen, path)\n                self.assertEqual(x.normalize(path, frozen), frozen, path)\n"), (b"\n    def test_missing_duplicate_outside_and_binary_inverse_changes_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = windows_vm_bytes(path, (c.ROOT / path).read_bytes())\n            altered = [current + b'# outside\\n', b'\\xff']\n            weakened = current.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)\n            if weakened == current: weakened = current.replace(b'assert ', b'assert False and ', 1)\n", b"\n    def test_missing_duplicate_outside_and_binary_inverse_changes_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = (c.ROOT / path).read_bytes()\n            altered = [current + b'# outside\\n', b'\\xff']\n            weakened = current.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)\n            if weakened == current: weakened = current.replace(b'assert ', b'assert False and ', 1)\n"), (b"            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *args)\n            fresh.assert_called_once()\n        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *self.args)\n        runtime = ast.parse(windows_vm_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes()).decode())\n        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))\n\n    def test_original1493_strict303_consumer452_ids_and_assertions_are_preserved(self):\n", b"            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *args)\n            fresh.assert_called_once()\n        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *self.args)\n        runtime = ast.parse((c.ROOT / x.PROFILE).read_text())\n        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))\n\n    def test_original1493_strict303_consumer452_ids_and_assertions_are_preserved(self):\n"), (b'        self.assertEqual((c.ROOT / \'scripts/rc_publication_stage.py\').read_bytes(), self.frozen(\'scripts/rc_publication_stage.py\'))\n\n    def test_new48_inventory_readonly_workflow_and_exceptional_outcomes(self):\n        text = windows_vm_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()\n        for fragment in ("branches: [\'ci/issue88-publisher-executor-*\']", \'permissions:\\n  contents: read\', \'timeout-minutes: 30\', \'frozen three hundred fifty seven cases\', \'import rc_pretag_git_budget_profile as profile\', \'supervisor_readiness.inventory()\', \'supervisor_readiness.execution_valid(loaded, result)\', \'supervisor-readiness-cases.log\', \'supervisor-readiness-inventory.json\', \'stage_retirement.inventory()\', \'stage_retirement.execution_valid(loaded, result)\', \'stage-retirement-cases.log\', \'stage-retirement-inventory.json\', \'git_budget.inventory()\', \'git_budget.execution_valid(loaded, result)\', \'git-budget-cases.log\', \'git-budget-inventory.json\', \'parents == [profile.M]\', \'checked() == before\', "\'production_ready\': False"):\n            self.assertIn(fragment, text)\n        for forbidden in (\'secrets.\', \'GH_TOKEN\', \'GITHUB_TOKEN\', \'contents: write\', \'workflow_dispatch:\', \'pull_request:\', \'gh release\', \'curl \', \'pip install\'):\n', b'        self.assertEqual((c.ROOT / \'scripts/rc_publication_stage.py\').read_bytes(), self.frozen(\'scripts/rc_publication_stage.py\'))\n\n    def test_new48_inventory_readonly_workflow_and_exceptional_outcomes(self):\n        text = (c.ROOT / x.WORKFLOW).read_text()\n        for fragment in ("branches: [\'ci/issue88-publisher-executor-*\']", \'permissions:\\n  contents: read\', \'timeout-minutes: 30\', \'frozen three hundred fifty seven cases\', \'import rc_pretag_git_budget_profile as profile\', \'supervisor_readiness.inventory()\', \'supervisor_readiness.execution_valid(loaded, result)\', \'supervisor-readiness-cases.log\', \'supervisor-readiness-inventory.json\', \'stage_retirement.inventory()\', \'stage_retirement.execution_valid(loaded, result)\', \'stage-retirement-cases.log\', \'stage-retirement-inventory.json\', \'git_budget.inventory()\', \'git_budget.execution_valid(loaded, result)\', \'git-budget-cases.log\', \'git-budget-inventory.json\', \'parents == [profile.M]\', \'checked() == before\', "\'production_ready\': False"):\n            self.assertIn(fragment, text)\n        for forbidden in (\'secrets.\', \'GH_TOKEN\', \'GITHUB_TOKEN\', \'contents: write\', \'workflow_dispatch:\', \'pull_request:\', \'gh release\', \'curl \', \'pip install\'):\n')),
    '.github/workflows/issue88-publication-executor.yml': ((b"        with: {ref: '${{ github.sha }}', fetch-depth: 0, persist-credentials: false}\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen three hundred sixty nine cases\n        shell: python\n        run: |\n          import hashlib, json, os, pathlib, platform, subprocess, sys, traceback, unittest\n", b"        with: {ref: '${{ github.sha }}', fetch-depth: 0, persist-credentials: false}\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen three hundred fifty seven cases\n        shell: python\n        run: |\n          import hashlib, json, os, pathlib, platform, subprocess, sys, traceback, unittest\n"), (b"              sys.path.insert(0, 'scripts')\n              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_windows_vm_profile as profile; import rc_pretag_git_budget_cases as git_budget; import rc_pretag_windows_vm_cases as windows_vm\n              import rc_pretag_stage_retirement_cases as stage_retirement\n              import rc_pretag_integration_admission_cases as admission\n              import rc_pretag_final_admission_cases as final_admission\n", b"              sys.path.insert(0, 'scripts')\n              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_git_budget_profile as profile; import rc_pretag_git_budget_cases as git_budget\n              import rc_pretag_stage_retirement_cases as stage_retirement\n              import rc_pretag_integration_admission_cases as admission\n              import rc_pretag_final_admission_cases as final_admission\n"), (b"                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'git-budget-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert git_budget.execution_valid(loaded, result)\n              names = windows_vm.inventory()\n              suite = unittest.defaultTestLoader.loadTestsFromNames(names)\n              loaded = [test.id() for test in c._flatten(suite)]\n              with (evidence / 'windows-vm-cases.log').open('w', encoding='utf-8') as output:\n                  result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=c.InventoryResult).run(suite)\n              receipt = {'loaded_ids': loaded, 'executed_ids': result.executed_ids, 'tests_run': result.testsRun,\n                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'windows-vm-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert windows_vm.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n          except BaseException:\n", b"                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'git-budget-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert git_budget.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n          except BaseException:\n")),
}
# END SEALED SOURCE
DISPATCH = b'    import rc_pretag_windows_vm_profile as windows_vm\n    selected = windows_vm.select(ref, root, git, entries, historical, release, release_tree, documents)\n    if selected is not None:\n        return selected\n'
NORMALIZE = b'    from rc_pretag_windows_vm_profile import normalize as windows_vm_bytes\n    current = windows_vm_bytes(path, current)\n'
NEW_CASES = {'rc_pretag_windows_vm_cases.WindowsVmCompositionCases': ('test_actual_f_identity_and_fresh_historical_validation', 'test_exact_ordered_d_i_j_and_four_document_overlay', 'test_wrong_repeated_nested_and_same_tree_topologies_reject', 'test_twenty_four_exact_paths_modes_pins_and_entry_count', 'test_individual_and_aggregate_caps_reject', 'test_four_full_byte_inverses_and_six_dispatch_lines', 'test_ten_historical_workflow_identities_are_finite_and_immutable', 'test_missing_duplicate_outside_and_binary_inverse_changes_reject', 'test_selected_historical_and_release_failures_are_terminal', 'test_current_candidate_is_never_cached', 'test_original1541_strict303_consumer452_ids_and_assertions_are_preserved', 'test_new12_inventory_readonly_workflows_and_exceptional_outcomes')}
CLASS = 'rc_pretag_windows_vm_cases.WindowsVmCompositionCases'
NAMES = ('test_actual_f_identity_and_fresh_historical_validation', 'test_exact_ordered_d_i_j_and_four_document_overlay', 'test_wrong_repeated_nested_and_same_tree_topologies_reject', 'test_twenty_four_exact_paths_modes_pins_and_entry_count', 'test_individual_and_aggregate_caps_reject', 'test_four_full_byte_inverses_and_six_dispatch_lines', 'test_ten_historical_workflow_identities_are_finite_and_immutable', 'test_missing_duplicate_outside_and_binary_inverse_changes_reject', 'test_selected_historical_and_release_failures_are_terminal', 'test_current_candidate_is_never_cached', 'test_original1541_strict303_consumer452_ids_and_assertions_are_preserved', 'test_new12_inventory_readonly_workflows_and_exceptional_outcomes')
DIGEST = '383bd1abb88ab211267ee75d9fc21eba8dfba36e660e9dbf94101b1482956f21'


def normalize(path, current):
    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""
    assert type(path) is str and type(current) is bytes, 'windows_vm inverse input'
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
        assert before and restored.count(before) == 1, 'windows_vm fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (
        baseline[1:3], baseline[3], baseline[4]), 'complete windows_vm F inverse'
    return restored


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; no correction chains or ancestry inference."""
    if release != p.R:
        raise o.TopologyError('windows_vm_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('windows_vm_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('windows_vm_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('windows_vm_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh immutable M admission, exact candidate pins and complete reviewed delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'windows_vm M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'windows_vm M tree'
    raw = git('cat-file', 'commit', M, root=root)
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == M_RAW, 'windows_vm M raw'
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(M, root) and len(baseline) == 1813
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 24 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() and len(BASE_PINS) == 4
    assert FRAGMENTS.keys() == BASE_PINS.keys() and PRIOR_PINS.keys() <= BASE_PINS.keys()
    assert set(PRIOR_PINS) == {WORKFLOW} and len(PRIOR_PINS[WORKFLOW]) == 10
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1833
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
    assert sum(len(data[path].splitlines()) for path in paths if path.startswith('docs/specs/windows-vm-session/')) <= 300
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'windows_vm_delta_budget')
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
