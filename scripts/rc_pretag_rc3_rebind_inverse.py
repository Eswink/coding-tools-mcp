"""rc.3 append-only rebind layer: S1/S2 source drift (63d18622, e243a4df, 44d2e6a9, d9b840b8) rebound P/A/N/S
in the publication tests; reverse exactly those four hunks once so frozen rc.1/rc.2 inventories (815/775) see rc.2 bytes.
Applied only by the 815/775 preservation checks; live consumers keep the rebound bytes."""
import rc_pretag_ownership_profile as o

# rc.2 (bdc4aeb5) bytes and the rc.3 (S1/S2-rebound) bytes.
BASE_PINS = {
    'scripts/rc_pretag_publication_tests.py': ('100644', '7edd71605311422b18a5e278aa1d457aaa8a88d4', '75f122d730e30a1a8895a618ba373d5f87b760c2e811869df5f4db5c4db841d2', 29775, 443),
}
SOURCE_PINS = {
    'scripts/rc_pretag_publication_tests.py': ('100644', '007a394018ba6fadc193c378775b0817d748eced', '1817e110a519ff2e53d7751b4365bb9f90ab0fdee032cc42f8ff9887fe7b5321', 30332, 451),
}
FRAGMENTS = {
    'scripts/rc_pretag_publication_tests.py': (
        (b"        # Live good tracks S\xe2\x80\xb2+amendment pins (PROFILE tip; others frozen AMENDMENT/ANCILLARY).\n        # selected(M) early-returns entries(M) and must not be used as live good after S\xe2\x80\xb2 rebound.\n        def _live(path):\n            if path == p.PROFILE:\n                return (c.ROOT / path).read_bytes()\n            pin = (p.AMENDMENT_PINS | p.ANCILLARY_PINS)[path][0]\n            return c._git('cat-file', 'blob', pin, root=c.ROOT)\n        self.good = self.source | {path: ('100644', 'blob', self.blob(_live(path)))\n                                   for path in p.AMENDMENT_CAPS | p.ANCILLARY_CAPS}\n",
         b'        self.good = self.selected(p.JOIN_ONCE_M)\n'),
        (b"        self.assertEqual((p.N, p.N_TREE, p.N_PARENTS), ('1b7ddb954482b1381365cf8e9d73df595eadd09d',\n            '3c6de03b580b4a13d958fa3e1665fff1e1ccd70e',\n            ('a88be4901623f7c8629b93df984166587253f0be', 'b9430b06469d8fb0cb6f5922611aef11a35fc65b')))\n",
         b"        self.assertEqual((p.N, p.N_TREE, p.N_PARENTS), ('e459c9bec1dc6006eaad6df5f65111491c7b7572',\n            '1eae7b72539740c2a1cc167a82ec2af3b5f951d6',\n            ('a88be4901623f7c8629b93df984166587253f0be', '65b04eda5d63b8457b5b8879cd97d391e5e2b021')))\n"),
        (b'        self.assertEqual((p.SOURCE_DELTA_LIMIT, p.AMENDMENT_DELTA_LIMIT), (1340, 1260))\n',
         b'        self.assertEqual((p.SOURCE_DELTA_LIMIT, p.AMENDMENT_DELTA_LIMIT), (1340, 1050))\n'),
        (b"        self.bad_content(self.changed(p.PROFILE, data + b'# boundary\\n' * (521 - len(data.splitlines()))))\n",
         b"        self.bad_content(self.changed(p.PROFILE, data + b'# boundary\\n' * (401 - len(data.splitlines()))))\n"),
    ),
}


def normalize(path, current):
    """Reverse only the rc.3 rebind bytes exact-once; every other path or already-rc.2 byte is untouched."""
    assert type(path) is str and type(current) is bytes, 'rc3 rebind inverse input'
    if path not in BASE_PINS:
        return current
    identity, baseline = o.pin(current), BASE_PINS[path]
    if identity == baseline[1:3]:
        return current
    row = SOURCE_PINS[path]
    assert (identity, len(current), len(current.splitlines())) == (row[1:3], row[3], row[4]), path
    restored = current
    for before, after in reversed(FRAGMENTS[path]):
        assert before and restored.count(before) == 1, 'rc3 fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (baseline[1:3], baseline[3], baseline[4]), 'complete rc3 inverse'
    return restored
