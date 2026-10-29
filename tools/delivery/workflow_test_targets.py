"""Fail closed when a workflow names a `cargo test --test X` target that does not exist.

`cargo test --test X` with an unknown X exits 101 ("no test target named X"),
but only when that line is reached; an earlier failing gate can hide a dead
target for a whole release (v0.7.0 `cloud-execution-bridge` named a
`service_cli` target that never existed). This check runs first and resolves
every `--test X` in `.github/workflows/*.yml` statically:
  * with `--manifest-path P/Cargo.toml` the target must be `P/tests/X.rs`,
    `P/tests/X/main.rs`, or a `[[test]] name = "X"` in that manifest;
  * without `--manifest-path` (the step's working directory decides the crate)
    it must exist in at least one first-party crate of the repository.
Only arguments before a bare `--` count, so libtest flags such as
`--test-threads` are never mistaken for targets.
"""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

CARGO_TEST = re.compile(r'\bcargo\s+(?:\+\S+\s+)?test\b')
TEST_NAME = re.compile(r'name\s*=\s*"([^"]+)"')
SKIP_DIRS = {'vendor', 'target', 'node_modules', '.git'}


def logical_lines(text: str):
    """Yield (line_number, text) with shell `\\` continuations joined."""
    buf, start = '', 0
    for number, raw in enumerate(text.splitlines(), 1):
        if not buf:
            start = number
        if raw.rstrip().endswith('\\'):
            buf += raw.rstrip()[:-1] + ' '
            continue
        yield start, buf + raw
        buf = ''
    if buf:
        yield start, buf


def cargo_test_invocations(text: str):
    """Yield (line_number, manifest_path_or_None, [targets])."""
    for number, line in logical_lines(text):
        for match in CARGO_TEST.finditer(line):
            rest = re.split(r'\|\||&&|[|;]', line[match.end():], maxsplit=1)[0]
            try:
                args = shlex.split(rest, comments=True)
            except ValueError:
                args = rest.split()
            manifest, targets, i = None, [], 0
            while i < len(args):
                arg = args[i]
                if arg == '--':
                    break
                if arg in ('--test', '--manifest-path') and i + 1 < len(args):
                    value = args[i + 1]
                    i += 1
                elif arg.startswith('--test=') or arg.startswith('--manifest-path='):
                    value = arg.split('=', 1)[1]
                    arg = arg.split('=', 1)[0]
                else:
                    i += 1
                    continue
                if arg == '--test':
                    targets.append(value)
                else:
                    manifest = value
                i += 1
            if targets:
                yield number, manifest, targets


def crate_targets(crate: Path) -> set[str]:
    names: set[str] = set()
    tests = crate / 'tests'
    if tests.is_dir():
        names.update(p.stem for p in tests.glob('*.rs'))
        names.update(p.parent.name for p in tests.glob('*/main.rs'))
    manifest = crate / 'Cargo.toml'
    if manifest.is_file():
        section = None
        for raw in manifest.read_text(encoding='utf-8', errors='replace').splitlines():
            stripped = raw.strip()
            if stripped.startswith('['):
                section = stripped
                continue
            found = TEST_NAME.match(stripped)
            if section == '[[test]]' and found:
                names.add(found.group(1))
    return names


def first_party_crates(root: Path) -> list[Path]:
    crates = []
    for manifest in root.rglob('Cargo.toml'):
        rel = manifest.relative_to(root).parts
        if not SKIP_DIRS.intersection(rel):
            crates.append(manifest.parent)
    return crates


def check(root: Path) -> list[str]:
    problems: list[str] = []
    any_crate: set[str] | None = None
    for workflow in sorted((root / '.github/workflows').glob('*.y*ml')):
        text = workflow.read_text(encoding='utf-8', errors='replace')
        for number, manifest, targets in cargo_test_invocations(text):
            where = f'{workflow.relative_to(root).as_posix()}:{number}'
            if manifest:
                crate = (root / manifest).parent
                if not (root / manifest).is_file():
                    problems.append(f'{where}: --manifest-path {manifest} does not exist')
                    continue
                known, scope = crate_targets(crate), manifest
            else:
                if any_crate is None:
                    any_crate = set().union(*(crate_targets(c) for c in first_party_crates(root)))
                known, scope = any_crate, 'any first-party crate'
            for target in targets:
                if target not in known:
                    problems.append(f'{where}: cargo test --test {target} has no target in {scope}')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    problems = check(args.root)
    for problem in problems:
        print(problem)
    if not problems:
        print('every workflow `cargo test --test X` resolves to an existing target')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
