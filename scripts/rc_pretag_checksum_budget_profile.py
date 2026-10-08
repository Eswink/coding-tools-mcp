"""Finite checksum-budget admission; independent complete-tree review binds this module."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '39a9ae7e2761f419db5cace712368e5671042b5e'
M_TREE = 'ecf7792ca9911d969ac223227c819fbb8ef70fe7'
M_PARENTS = ('981d7b23af1c5c8174352c4564aa65b1557cc546', '9d9f5d9ee1bad13b825fd8ac1f114a578122af2a')
PROFILE = 'scripts/rc_pretag_checksum_budget_profile.py'
CASES = 'scripts/rc_pretag_checksum_budget_cases.py'
DISPATCHER = 'scripts/rc_pretag_staging_budget_profile.py'
WORKFLOW = '.github/workflows/issue88-publication-executor.yml'
CAPS = {
    'scripts/rc_artifact_consumer.py': (255, 4),
    'scripts/rc_consumer_archive.py': (390, 70),
    'scripts/rc_consumer_io.py': (450, 100),
    'scripts/rc_pretag_ownership_tests.py': (378, 2),
    'scripts/rc_pretag_staging_budget_profile.py': (205, 6),
    'scripts/rc_pretag_staging_budget_cases.py': (383, 15),
    '.github/workflows/issue88-publication-executor.yml': (119, 14),
    'scripts/rc_consumer_checksum_budget_cases.py': (480, 480),
    'scripts/rc_pretag_checksum_budget_profile.py': (400, 400),
    'scripts/rc_pretag_checksum_budget_cases.py': (440, 440),
    'docs/specs/issue88-checksum-budget/requirements.md': (40, 40),
    'docs/specs/issue88-checksum-budget/design.md': (70, 70),
    'docs/specs/issue88-checksum-budget/tasks.md': (60, 60),
}
BASE_PINS = {
    'scripts/rc_artifact_consumer.py': ('100644', '0dfd9bc7fb13e6504d76a9c9f374b55d3daf1123', '963d36b5f5f3408e84c73482086e258c34f5ff3d5e27e6abed9083a7a51d44ee', 14358, 251),
    'scripts/rc_consumer_archive.py': ('100644', 'd4645a2d3640229aedee06fd2bef9d82fb49d031', '38e391f28b0fb3ccd64bbca65aee062bbc337f7d32c92909a1ff4611a9ab1e80', 17725, 344),
    'scripts/rc_consumer_io.py': ('100644', '2719bd8cb0ed3c3a9b149ca5b89832325f5aac52', '4dffc2c0773f107b7abdc6e0970516b8e793826babd9696ac258768b5de00459', 13783, 378),
    'scripts/rc_pretag_ownership_tests.py': ('100644', 'e6ecfa8a7976215ea9d5fbc4eb3e8a60fdca62ee', '07711c5fa4b78855a98a16be87b8653dbff23620b36e5b76324e8faea2aa7711', 22900, 378),
    'scripts/rc_pretag_staging_budget_profile.py': ('100644', '8fcbc1bfaff93026a77d3b95ffa90f21b5b3a6f7', 'f060e38c9a3cda5b195300609406a4d251e22ff38a1644fcc9646ae4ee7ad465', 44698, 199),
    'scripts/rc_pretag_staging_budget_cases.py': ('100644', '5f0d773cbf81b2650d2a9538aff654bceb05f717', '163ede10fba1845e31bddcc44b814de309fcff438752c5e10471a7cd3c6fdf54', 27947, 382),
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'a61797b57dcba000d238dbd2c224247ec077cdbc', '28601d9ded709b55ccad36f966a106e2912d67c48ec47833b9b519e1524045dc', 8575, 109),
}
PRIOR_PINS = {
    'scripts/rc_artifact_consumer.py': (('1475ffd862c75effb4f4f8f401f37e816ba714ce', '3408807349f305037799025810bd109f4f1e95a0c53a00bd80bf69a2cfc145ec'),),
    'scripts/rc_pretag_ownership_tests.py': (('4bf8ddbe8b2b2ffc3c0bbea1a473cf0c26d6b56e', '8f40b75ada5a5ba0d6dd652aa015ed28a7fd1af22d2c603db3b0d40b420af0d5'),),
    '.github/workflows/issue88-publication-executor.yml': (('a81e9404bae5e4a56599eb0455026c207acbdc27', 'ef64753deb51f2260812bf136ad4bca0d811bc84e61e601e80697fdef314181c'), ('f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a'), ('d06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634'), ('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e')),
}
DELTA_LIMIT = 1800
# BEGIN SEALED SOURCE
SOURCE_PINS = {
    'scripts/rc_artifact_consumer.py': ('100644', '74ef163b292ff86d902639df5f92ab7f48d596d5', '6fc5ba85f1a1bafbb5688de8aff0787c16f8e7b452de4177e6b75649c6c29bf0', 14368, 251),
    'scripts/rc_consumer_archive.py': ('100644', 'cfb8f438d19e1adb8ef8bd531d202646cfca0930', '32f10689f464c41dbc05590a076b459acf82b74e61bc5bf68bc6f4117e87a812', 18206, 352),
    'scripts/rc_consumer_io.py': ('100644', 'ac825651db0cbc203fb6103a66eb0a78553ba51b', '3dfab864c9aba495f5bf732b6fa0642b3404bc41ab17b517416ac91101a3ca88', 15575, 426),
    'scripts/rc_pretag_ownership_tests.py': ('100644', 'bb3c608556c5b40c43c7ab4b3846d60ff425e3c6', 'bbc901fd5449aaa9a58abddb94c372e7fc170e4847602c38f81c918b09b6a3da', 22925, 378),
    'scripts/rc_pretag_staging_budget_profile.py': ('100644', 'ea0c4d87541bdd9d066c377417f5e05c51fd6804', '0148cddd2270a6ea984c4fccfffad960dfd51d09bd21f798f17227b1c1074234', 45032, 205),
    'scripts/rc_pretag_staging_budget_cases.py': ('100644', '627ae81d0d3dab11a94a33279293f2597ca5c3a8', 'da74ca7c097617850e348a771abed1aeb18aae25eed5001756ad0ee347d85833', 28180, 383),
    '.github/workflows/issue88-publication-executor.yml': ('100644', '2e287f38ffc6cbcdc9da82277bce9e1c25bc7a50', '377086ca7c6edb11fbace99c35340bb4147c2102123d96cd00ef3a3e196f0979', 9555, 119),
    'scripts/rc_consumer_checksum_budget_cases.py': ('100644', '2a912fc0f6b2c5b714322603b26998b70f9e7186', '23915a8546a77061e30e78409b4eebca52b1ce2b00754e0ab135822390c53e3d', 19946, 361),
    'scripts/rc_pretag_checksum_budget_cases.py': ('100644', 'c968e30aeb68cdb23df55d9d6700b01e6ccbf01a', '23ea5f92e7101cfecb94f859956b8cf48982f4de10de1279b0ba8f75a302b4ac', 27690, 379),
    'docs/specs/issue88-checksum-budget/requirements.md': ('100644', '82050ffec72b745f536471ea3f4b95d5d9e4cdae', '767138735e6d4493744048c500e878690f1946f3bb94c0b66ee446c2fab76914', 3442, 36),
    'docs/specs/issue88-checksum-budget/design.md': ('100644', '386f5e64814ec74be8e5ae6197fa9060713d7583', 'fb56191035d0c09a2a401fc70a9780ea8e8522a1938b94b00f8f2c54d7727524', 4974, 42),
    'docs/specs/issue88-checksum-budget/tasks.md': ('100644', 'bd7d090b98dd4ae8dbf4f171d69ccd8e5182c5b1', '0d911dbc11fab29e97d1cd70c374ef8371cd17b4fe125d23511f4d649a60c9db', 3205, 41),
}
FRAGMENTS = {
    'scripts/rc_artifact_consumer.py': (
        (b"    path = transport.download_artifact_zip(api, metadata, download, opener=opener, **budget)\n    snapshot.revalidate_download(api, selection, metadata)\n    archive.extract_bounded_zip(path, bundle, [name for name, _, _ in payloads(producer.version)])\n    archive.verify_checksum_inventory(bundle, **budget)\n    archive.extract_bounded_cloud_tar(bundle.path / 'cloud-linux-amd64.tar.gz', cloud)\n    content = contracts.verify_consumed_bundle(root, bundle.path, cloud.path, producer, selection['integration'])\n    download.files(); bundle.files(); cloud.files()\n", b"    path = transport.download_artifact_zip(api, metadata, download, opener=opener, **budget)\n    snapshot.revalidate_download(api, selection, metadata)\n    archive.extract_bounded_zip(path, bundle, [name for name, _, _ in payloads(producer.version)])\n    archive.verify_checksum_inventory(bundle)\n    archive.extract_bounded_cloud_tar(bundle.path / 'cloud-linux-amd64.tar.gz', cloud)\n    content = contracts.verify_consumed_bundle(root, bundle.path, cloud.path, producer, selection['integration'])\n    download.files(); bundle.files(); cloud.files()\n"),
    ),
    'scripts/rc_consumer_archive.py': (
        (b'import zlib\n\nfrom rc_consumer_io import (CHUNK, FILE_LIMIT, JSON_LIMIT, PATH_LIMIT, ConsumerError,\n                            PrivateRoot, _check_budget, hash_file, json_file, need, open_file, safe_relative)\n\nZIP_LIMIT = 2 * 1024**3\nDIRECTORY_LIMIT = 8 * 1024**2\n', b'import zlib\n\nfrom rc_consumer_io import (CHUNK, FILE_LIMIT, JSON_LIMIT, PATH_LIMIT, ConsumerError,\n                            PrivateRoot, hash_file, json_file, need, open_file, safe_relative)\n\nZIP_LIMIT = 2 * 1024**3\nDIRECTORY_LIMIT = 8 * 1024**2\n'),
        (b"        raise ConsumerError('invalid_zip') from None\n\n\ndef verify_checksum_inventory(root: PrivateRoot, *, deadline=None, check_active=None):\n    budget = {} if deadline is None and check_active is None else dict(deadline=deadline, check_active=check_active)\n    _check_budget(deadline, check_active)\n    files = set(root.files())\n    _check_budget(deadline, check_active)\n    need('SHA256SUMS.txt' in files, 'missing_checksum_inventory')\n    try:\n        text = root.read('SHA256SUMS.txt', JSON_LIMIT).decode('utf-8')\n    except UnicodeError:\n        raise ConsumerError('invalid_checksum_inventory') from None\n    _check_budget(deadline, check_active)\n    need(text.endswith('\\n') and '\\r' not in text, 'invalid_checksum_inventory')\n    entries, names = {}, _Names()\n    for line in text[:-1].split('\\n'):\n        _check_budget(deadline, check_active)\n        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)\n        need(match is not None, 'invalid_checksum_inventory')\n        name = names.add(match[2])\n        need(name != 'SHA256SUMS.txt', 'invalid_checksum_inventory')\n        entries[name] = match[1]\n    _check_budget(deadline, check_active)\n    need(set(entries) == files - {'SHA256SUMS.txt'}, 'checksum_coverage')\n    for name, expected in entries.items():\n        _check_budget(deadline, check_active)\n        need(hash_file(root.path / name, **budget) == expected, 'checksum_mismatch')\n    _check_budget(deadline, check_active)\n    return entries\n\n\n", b"        raise ConsumerError('invalid_zip') from None\n\n\ndef verify_checksum_inventory(root: PrivateRoot):\n    files = set(root.files())\n    need('SHA256SUMS.txt' in files, 'missing_checksum_inventory')\n    try:\n        text = root.read('SHA256SUMS.txt', JSON_LIMIT).decode('utf-8')\n    except UnicodeError:\n        raise ConsumerError('invalid_checksum_inventory') from None\n    need(text.endswith('\\n') and '\\r' not in text, 'invalid_checksum_inventory')\n    entries, names = {}, _Names()\n    for line in text[:-1].split('\\n'):\n        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)\n        need(match is not None, 'invalid_checksum_inventory')\n        name = names.add(match[2])\n        need(name != 'SHA256SUMS.txt', 'invalid_checksum_inventory')\n        entries[name] = match[1]\n    need(set(entries) == files - {'SHA256SUMS.txt'}, 'checksum_coverage')\n    for name, expected in entries.items():\n        need(hash_file(root.path / name) == expected, 'checksum_mismatch')\n    return entries\n\n\n"),
    ),
    'scripts/rc_consumer_io.py': (
        (b'import re\nimport secrets\nimport stat\nimport time\nimport unicodedata\n\nCHUNK = 64 * 1024\n', b'import re\nimport secrets\nimport stat\nimport unicodedata\n\nCHUNK = 64 * 1024\n'),
        (b'            os.close(fd)\n\n\ndef _check_budget(deadline, check_active):\n    """Check caller-owned controls without renewing a budget or exposing errors."""\n    if deadline is None and check_active is None:\n        return\n    need(deadline is None or type(deadline) is int or\n         (type(deadline) is float and math.isfinite(deadline)), \'invalid_transport_deadline\')\n    need(check_active is None or callable(check_active), \'artifact_transport_failed\')\n    if deadline is not None:\n        need(time.monotonic() < deadline, \'transport_deadline_exceeded\')\n    if check_active is None:\n        return\n    code, cancellation = None, None\n    try:\n        if check_active() is not None:\n            code = \'artifact_transport_failed\'\n    except KeyboardInterrupt:\n        cancellation = KeyboardInterrupt\n    except SystemExit:\n        cancellation = SystemExit\n    except BaseException as error:\n        code = \'artifact_transport_failed\'\n        try:\n            value = error.code\n            if type(value) is str:\n                code = {\'cancelled\': \'transport_cancelled\',\n                        \'timeout\': \'transport_deadline_exceeded\'}.get(value, code)\n        except BaseException:\n            pass\n    if cancellation is SystemExit:\n        raise SystemExit(1)\n    if cancellation:\n        raise KeyboardInterrupt()\n    if code:\n        raise ConsumerError(code)\n    if deadline is not None:\n        need(time.monotonic() < deadline, \'transport_deadline_exceeded\')\n\n\ndef hash_file(path, *, deadline=None, check_active=None) -> str:\n    _check_budget(deadline, check_active)\n    with open_file(path) as stream:\n        need(os.fstat(stream.fileno()).st_size <= FILE_LIMIT, \'file_size_limit\')\n        digest = hashlib.sha256()\n        total = 0\n        while True:\n            _check_budget(deadline, check_active)\n            data = stream.read(CHUNK)\n            if data:\n                total += len(data)\n                need(total <= FILE_LIMIT, \'file_size_limit\')\n            _check_budget(deadline, check_active)\n            if not data:\n                break\n            digest.update(data)\n        result = digest.hexdigest()\n    _check_budget(deadline, check_active)\n    return result\n\n\ndef _pairs(pairs):\n', b"            os.close(fd)\n\n\ndef hash_file(path) -> str:\n    with open_file(path) as stream:\n        need(os.fstat(stream.fileno()).st_size <= FILE_LIMIT, 'file_size_limit')\n        digest = hashlib.sha256()\n        total = 0\n        while data := stream.read(CHUNK):\n            total += len(data)\n            need(total <= FILE_LIMIT, 'file_size_limit')\n            digest.update(data)\n        return digest.hexdigest()\n\n\ndef _pairs(pairs):\n"),
    ),
    'scripts/rc_pretag_ownership_tests.py': (
        (b"\n    def test_ownership_io_drift_and_reverted_handoff_reject(self):\n        old = c._git('show', o.M + ':' + o.IO, root=self.repo)\n        current = integration_bytes(o.IO, (c.ROOT / o.IO).read_bytes())\n        mutations = [old, current + b'\\n', current.replace(b'CHUNK = 64', b'CHUNK = 63')]\n        for name in ('_directory', '_parent', '__init__'):\n            def method(data):\n", b"\n    def test_ownership_io_drift_and_reverted_handoff_reject(self):\n        old = c._git('show', o.M + ':' + o.IO, root=self.repo)\n        current = (c.ROOT / o.IO).read_bytes()\n        mutations = [old, current + b'\\n', current.replace(b'CHUNK = 64', b'CHUNK = 63')]\n        for name in ('_directory', '_parent', '__init__'):\n            def method(data):\n"),
    ),
    'scripts/rc_pretag_staging_budget_profile.py': (
        (b'def normalize(path, current):\n    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'staging inverse input\'\n    from rc_pretag_checksum_budget_profile import normalize as checksum_bytes\n    current = checksum_bytes(path, current)\n    if path not in BASE_PINS:\n        return current\n    identity = o.pin(current)\n', b'def normalize(path, current):\n    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'staging inverse input\'\n    if path not in BASE_PINS:\n        return current\n    identity = o.pin(current)\n'),
        (b'def select(ref, root, git, entries, historical, release, release_tree, documents):\n    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    import rc_pretag_checksum_budget_profile as checksum\n    selected = checksum.select(ref, root, git, entries, historical, release, release_tree, documents)\n    if selected is not None:\n        return selected\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n    except o.TopologyError:\n', b'def select(ref, root, git, entries, historical, release, release_tree, documents):\n    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n    except o.TopologyError:\n'),
    ),
    'scripts/rc_pretag_staging_budget_cases.py': (
        (b"import rc_pretag_final_admission_cases as final_cases\nimport rc_pretag_download_budget_cases as download_cases\nimport rc_pretag_staging_budget_profile as x\nfrom rc_pretag_checksum_budget_profile import normalize as checksum_bytes\n\ndef inventory():\n    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]\n", b"import rc_pretag_final_admission_cases as final_cases\nimport rc_pretag_download_budget_cases as download_cases\nimport rc_pretag_staging_budget_profile as x\n\ndef inventory():\n    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]\n"),
        (b"        cls.fixture.__exit__(None, None, None)\n    def setUp(self):\n        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob(checksum_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n        self.feature = self.commit([x.M, self.pure], self.good)\n        self.overlay = self.good | c.RELEASE_DOCS\n", b"        cls.fixture.__exit__(None, None, None)\n    def setUp(self):\n        self.original = c._entries(x.M, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}\n        self.pure = self.commit([x.M], self.good)\n        self.feature = self.commit([x.M, self.pure], self.good)\n        self.overlay = self.good | c.RELEASE_DOCS\n"),
        (b"        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1764, 1770, 13, 7))\n        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(x.CAPS[x.PROFILE], (400, 400))\n        self.assertEqual(self.good[x.PROFILE][2], c._blob(checksum_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))\n        for path, row in x.SOURCE_PINS.items():\n            data = checksum_bytes(path, (c.ROOT / path).read_bytes())\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n                changed = list(row)\n", b"        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1764, 1770, 13, 7))\n        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        self.assertEqual(x.CAPS[x.PROFILE], (400, 400))\n        self.assertEqual(self.good[x.PROFILE][2], c._blob((c.ROOT / x.PROFILE).read_bytes()))\n        for path, row in x.SOURCE_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n                changed = list(row)\n"),
        (b"        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed\\n'))\n    def test_individual_and_total_budgets_fail_closed(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1800, 1734))\n        data = {path: checksum_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'staging_delta_budget')\n        budgets()\n", b"        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed\\n'))\n    def test_individual_and_total_budgets_fail_closed(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1800, 1734))\n        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'staging_delta_budget')\n        budgets()\n"),
        (b"                    self.assertEqual(x.normalize(path, prior), prior)\n    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = checksum_bytes(path, (c.ROOT / path).read_bytes())\n            altered = [current + b'# outside\\n', b'\\xff']\n            for before, _ in fragments:\n                self.assertEqual(current.count(before), 1)\n", b"                    self.assertEqual(x.normalize(path, prior), prior)\n    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = (c.ROOT / path).read_bytes()\n            altered = [current + b'# outside\\n', b'\\xff']\n            for before, _ in fragments:\n                self.assertEqual(current.count(before), 1)\n"),
        (b"        changed = set()\n        for module in {item.split('.', 1)[0] for item in original}:\n            path = 'scripts/' + module + '.py'\n            current, frozen = checksum_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n            before, after = methods(frozen), methods(current)\n            self.assertEqual(before.keys(), after.keys(), path)\n", b"        changed = set()\n        for module in {item.split('.', 1)[0] for item in original}:\n            path = 'scripts/' + module + '.py'\n            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n            before, after = methods(frozen), methods(current)\n            self.assertEqual(before.keys(), after.keys(), path)\n"),
        (b"                'scripts/rc_consumer_io.py', 'scripts/rc_consumer_transport.py', 'scripts/rc_consumer_transport_worker.py',\n                'scripts/rc_consumer_proof_fixtures.py', 'scripts/rc_consumer_default_worker_proof.py', 'scripts/rc_consumer_default_worker_proof_tests.py',\n                'scripts/rc_consumer_c_93c2ad95_io.txt', 'src-tauri/src/workspace_snapshots/filesystem.rs'):\n            self.assertEqual(checksum_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)\n        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))\n    def test_new24_inventory_and_exceptional_outcomes_reject(self):\n        loaded = inventory()\n", b"                'scripts/rc_consumer_io.py', 'scripts/rc_consumer_transport.py', 'scripts/rc_consumer_transport_worker.py',\n                'scripts/rc_consumer_proof_fixtures.py', 'scripts/rc_consumer_default_worker_proof.py', 'scripts/rc_consumer_default_worker_proof_tests.py',\n                'scripts/rc_consumer_c_93c2ad95_io.txt', 'src-tauri/src/workspace_snapshots/filesystem.rs'):\n            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)\n        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))\n    def test_new24_inventory_and_exceptional_outcomes_reject(self):\n        loaded = inventory()\n"),
    ),
    '.github/workflows/issue88-publication-executor.yml': (
        (b"        with: {ref: '${{ github.sha }}', fetch-depth: 0, persist-credentials: false}\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen one hundred ninety-two cases\n        shell: python\n        run: |\n          import hashlib, json, os, pathlib, platform, subprocess, sys, traceback, unittest\n", b"        with: {ref: '${{ github.sha }}', fetch-depth: 0, persist-credentials: false}\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen one hundred sixty-eight cases\n        shell: python\n        run: |\n          import hashlib, json, os, pathlib, platform, subprocess, sys, traceback, unittest\n"),
        (b"              sys.path.insert(0, 'scripts')\n              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_checksum_budget_profile as profile\n              import rc_pretag_integration_admission_cases as admission\n              import rc_pretag_final_admission_cases as final_admission\n              import rc_pretag_download_budget_cases as download_budget\n              import rc_pretag_staging_budget_cases as staging_budget\n              import rc_pretag_checksum_budget_cases as checksum_budget\n              git = lambda *args: c._git(*args).decode().strip()\n              assert sys.version_info[:2] == (3, 12) and platform.python_implementation() == 'CPython'\n              assert git('rev-parse', '--is-shallow-repository') == 'false'\n", b"              sys.path.insert(0, 'scripts')\n              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_staging_budget_profile as profile\n              import rc_pretag_integration_admission_cases as admission\n              import rc_pretag_final_admission_cases as final_admission\n              import rc_pretag_download_budget_cases as download_budget\n              import rc_pretag_staging_budget_cases as staging_budget\n              git = lambda *args: c._git(*args).decode().strip()\n              assert sys.version_info[:2] == (3, 12) and platform.python_implementation() == 'CPython'\n              assert git('rev-parse', '--is-shallow-repository') == 'false'\n"),
        (b"                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'staging-budget-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert staging_budget.execution_valid(loaded, result)\n              names = checksum_budget.inventory()\n              suite = unittest.defaultTestLoader.loadTestsFromNames(names)\n              loaded = [test.id() for test in c._flatten(suite)]\n              with (evidence / 'checksum-budget-cases.log').open('w', encoding='utf-8') as output:\n                  result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=c.InventoryResult).run(suite)\n              receipt = {'loaded_ids': loaded, 'executed_ids': result.executed_ids, 'tests_run': result.testsRun,\n                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'checksum-budget-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert checksum_budget.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n          except BaseException:\n", b"                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'staging-budget-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert staging_budget.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n          except BaseException:\n"),
    ),
}
# END SEALED SOURCE
DISPATCH = (
    b'    import rc_pretag_checksum_budget_profile as checksum\n'
    b'    selected = checksum.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
    b'    if selected is not None:\n'
    b'        return selected\n'
)
NORMALIZE = (
    b'    from rc_pretag_checksum_budget_profile import normalize as checksum_bytes\n'
    b'    current = checksum_bytes(path, current)\n'
)
NEW_CASES = {
    'rc_consumer_checksum_budget_cases.ChecksumBudgetCases': ('test_default_hash_inventory_and_bundle_call_shapes', 'test_invalid_controls_reject_before_io', 'test_deadline_boundaries_huge_values_and_callback_only', 'test_callback_errors_and_interrupts_are_sanitized', 'test_real_multichunk_hash_stops_on_cancel_or_expiry', 'test_late_eof_and_close_cannot_return_digest', 'test_inventory_rows_share_original_controls', 'test_checksum_errors_and_root_ownership_are_preserved', 'test_two_downloads_share_controls_through_real_checksum', 'test_checksum_cancellation_reaps_both_children', 'test_checksum_timeout_reaps_both_children', 'test_checksum_cleanup_failures_remain_sticky'),
    'rc_pretag_checksum_budget_cases.ChecksumBudgetCompositionCases': ('test_exact_m_identity_and_fresh_historical_validation', 'test_ordered_d_i_j_and_exact_four_document_overlay', 'test_wrong_repeated_nested_correction_and_same_tree_parents_reject', 'test_all_thirteen_paths_modes_pins_and_entry_counts_are_exact', 'test_individual_and_total_budgets_fail_closed', 'test_exact_dispatch_and_seven_inverses_recover_complete_m_bytes', 'test_missing_duplicate_outside_and_binary_inverse_edits_reject', 'test_selected_historical_and_release_content_errors_are_terminal', 'test_actual_candidate_validation_is_never_cached', 'test_original1352_strict303_consumer452_ids_and_bodies_are_preserved', 'test_readonly_workflow_and_held_sources_remain_bounded', 'test_new24_inventory_and_exceptional_outcomes_reject'),
}
CLASS = 'rc_pretag_checksum_budget_cases.ChecksumBudgetCompositionCases'
NAMES = NEW_CASES[CLASS]
DIGEST = '69574b1b90f5d896c8351173f9a64af6b8563ac8ebbf120172d8da7fecb7d1dd'


def normalize(path, current):
    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""
    assert type(path) is str and type(current) is bytes, 'checksum inverse input'
    from rc_pretag_archive_budget_profile import normalize as archive_bytes
    current = archive_bytes(path, current)
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
        assert before and restored.count(before) == 1, 'checksum fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (
        baseline[1:3], baseline[3], baseline[4]), 'complete checksum M inverse'
    return restored


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; no correction chains or ancestry inference."""
    if release != p.R:
        raise o.TopologyError('checksum_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('checksum_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('checksum_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('checksum_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh immutable M admission, exact candidate pins and complete reviewed delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'checksum M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'checksum M tree'
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(M, root) and len(baseline) == 1770
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 13 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() and len(BASE_PINS) == 7
    assert FRAGMENTS.keys() == BASE_PINS.keys() and PRIOR_PINS.keys() <= BASE_PINS.keys()
    assert len(PRIOR_PINS) == 3 and sum(map(len, PRIOR_PINS.values())) == 6
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1776
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
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'checksum_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected and historical content errors escape."""
    ref = o._commit(ref, root, git)
    import rc_pretag_archive_budget_profile as archive
    selected = archive.select(ref, root, git, entries, historical, release, release_tree, documents)
    if selected is not None:
        return selected
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
