"""Finite D1 sidebranch inverse for two #148-ported files that no earlier sealed layer pins; independent review binds self-bytes."""
import rc_pretag_ownership_profile as o

# Immutable bytes at 5dfea66b (#163 tip) and the sealed D1 sidebranch bytes at 05363d94.
BASE_PINS = {
    'scripts/rc_consumer_transport_tests.py': ('100644', '77853bf3ca29e9a54a3372ddfd1bff38f67a2e7a', '9f5c539e2474754810a4bb56b62b28929e8f26af25c9376f274a97fa24f81445', 16917, 332),
    'scripts/rc_consumer_snapshot.py': ('100644', '0d5b759be98287c329005aaf062d3bfdba05205c', '25ad5cf845efb9f19cd4d4e309702ecd81eba2b7be7c53d849c649eadd910391', 18232, 343),
}
SOURCE_PINS = {
    'scripts/rc_consumer_transport_tests.py': ('100644', '656808b765cf38541ff746faf8bac1a38a0a58a7', 'fe3b59155678332bfd579d96ebba15fd13add6346f647cdc02535b8a35acbff3', 16937, 332),
    'scripts/rc_consumer_snapshot.py': ('100644', 'dd819b3fbb79c506d240d7b4c19502d2c1b6ba15', '5b76efa0ac3a4c014ae953701093586b9d1b7940a01d554fe7b3fcf1943e0939', 18465, 347),
}
FRAGMENTS = {
    'scripts/rc_consumer_transport_tests.py': ((b"    for name in ('fixture.json', 'observed.json', 'observed.pending'):\n", b"    for name in ('fixture.json', 'observed.json'):\n"),),
    'scripts/rc_consumer_snapshot.py': ((b'from rc_consumer_wire_failure import _publication_failure\n', b''), (b"            OverflowError, RecursionError, subprocess.SubprocessError) as error:\n        normalized = _publication_failure(error)\n        failure = (normalized if normalized is not None and normalized.effect != 'none'\n                   else ConsumerError('invalid_snapshot'))\n    raise failure from None\n", b"            OverflowError, RecursionError, subprocess.SubprocessError):\n        raise ConsumerError('invalid_snapshot') from None\n")),
}


def normalize(path, current):
    """Reverse only the sealed D1 bytes exact-once; every other path or already-historical byte is untouched."""
    assert type(path) is str and type(current) is bytes, 'd1 snapshot inverse input'
    if path not in BASE_PINS:
        return current
    identity, baseline = o.pin(current), BASE_PINS[path]
    if identity == baseline[1:3]:
        return current
    row = SOURCE_PINS[path]
    assert (identity, len(current), len(current.splitlines())) == (row[1:3], row[3], row[4]), path
    restored = current
    for before, after in reversed(FRAGMENTS[path]):
        assert before and restored.count(before) == 1, 'd1 fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (baseline[1:3], baseline[3], baseline[4]), 'complete d1 inverse'
    return restored
