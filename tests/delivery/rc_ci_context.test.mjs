import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

test('Linux GLib source and optimized controls are mandatory independent evidence', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  const step = source.split('      - name: Independent Linux GLib source and optimized regression proof\n')[1]?.split('      - ')[0];
  assert.ok(step);
  assert.match(step, /if: always\(\) && runner.os == 'Linux' && steps.native_checks.outcome == 'success'/);
  assert.match(step, /set -euo pipefail/);
  for (const script of ['verify_glib_backport_tests.py', 'verify_glib_backport.py', 'glib_backport_regression.py']) assert.ok(step.includes(script));
  assert.match(step, /CARGO_TARGET_DIR="\$RUNNER_TEMP\/glib-regression-target"/);
  assert.match(step, /\|\| status=\$\?/);
  assert.match(step, /test "\$status" -eq 0/);
  assert.match(step, /cp -a.*evidence\/glib-regression/);
  assert.doesNotMatch(step, /continue-on-error|\|\| true|--skip|--ignored/);
});

for (const [name, expectedTargets] of [
  ['dot-rc-integration.yml', ['service_contracts', 'enrollment_contracts']],
  ['cloud-execution-bridge.yml', ['service_contracts']],
]) {
  test(`${name}: portable gateway targets exist and retain CLI contracts`, () => {
    const source = readFileSync(new URL(`../../.github/workflows/${name}`, import.meta.url), 'utf8');
    const commands = source.split('\n').filter(line => line.includes('--manifest-path services/cloud-gateway/Cargo.toml --lib --test'));
    assert.equal(commands.length, 1, `${name}: one portable gateway command`);
    const targets = [...commands[0].matchAll(/--test\s+(\S+)/g)].map(match => match[1]);
    for (const target of targets) {
      assert.ok(existsSync(new URL(`../../services/cloud-gateway/tests/${target}.rs`, import.meta.url)), `${name}: ${target}`);
    }
    assert.deepEqual(targets, expectedTargets, `${name}: retain the complete portable contract set`);
  });
}

test('portable target validation binds the three-platform source and preserves failures', () => {
  const source = readFileSync(new URL('../../.github/workflows/portable-ci-target-validation.yml', import.meta.url), 'utf8');
  assert.match(source, /branches: \['fix\/stale-portable-ci-target-20261001'\]/);
  assert.doesNotMatch(source, /pull_request:|workflow_dispatch:|secrets\.|continue-on-error/);
  assert.match(source, /permissions:\n  contents: read\n/);
  assert.match(source, /os: \[ubuntu-22\.04, ubuntu-24\.04, windows-2025\]/);
  assert.match(source, /fail-fast: false/);
  assert.equal([...source.matchAll(/uses: [^@\s]+@[a-f0-9]{40}\n/g)].length, 5);
  assert.match(source, /id: node\n        if: always\(\) && steps.source.outcome == 'success'/);
  assert.match(source, /id: python\n        if: always\(\) && steps.source.outcome == 'success'/);
  assert.match(source, /python-version: '3\.12'/);
  assert.match(source, /steps.node.outcome == 'success' && steps.python.outcome == 'success'/);
  assert.match(source, /ref: \$\{\{ github.sha \}\}\n          persist-credentials: false/);
  assert.match(source, /test "\$\(cat evidence\/source-sha.txt\)" = "\$GITHUB_SHA"/);
  assert.match(source, /git rev-parse 'HEAD\^\{tree\}' > evidence\/source-tree.txt/);
  for (const [name, expected] of [
    ['JavaScript workflow and gateway contracts', 'node --test tests/cloud-gateway/*.test.mjs tests/delivery/*.test.mjs'],
    ['Python delivery and probe classifier contracts', 'python -m unittest discover -s tests/delivery -v'],
    ['Standalone portable Cargo selection', 'cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --lib --test service_contracts'],
    ['RC portable Cargo selection', 'cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --lib --test service_contracts --test enrollment_contracts'],
  ]) {
    const step = source.split(`      - name: ${name}\n`)[1]?.split('      - ')[0];
    assert.ok(step, name);
    assert.match(step, /if: always\(\) && steps.source.outcome == 'success'/);
    assert.ok(step.includes(`${expected} 2>&1 | tee evidence/`), name);
    assert.ok(step.includes('codes=("${PIPESTATUS[@]}")'), name);
    assert.ok(step.includes('exit "${codes[0]}"'), name);
    assert.ok(step.includes('exit "${codes[1]}"'), name);
    assert.doesNotMatch(step, /\|\| true|--skip|--ignored/, name);
  }
  const python = source.split('      - name: Python delivery and probe classifier contracts\n')[1]?.split('      - ')[0];
  assert.match(python, /id: python_contracts\n        if: always\(\) && steps.source.outcome == 'success' && steps.python.outcome == 'success'\n        run: \|/);
  assert.ok(python.includes('python --version > evidence/delivery-python-version.txt'));
  assert.ok(python.includes('tee evidence/python-contracts.txt'));
  assert.ok(python.includes('> evidence/python-exit.txt'));
  assert.ok(existsSync(new URL('./test_probe_classifier.py', import.meta.url)), 'classifier tests retained in discovery');
  const outcomes = source.split('      - name: Preserve all step outcomes\n')[1]?.split('      - ')[0];
  assert.match(outcomes, /PYTHON_RESULT: \$\{\{ steps.python_contracts.outcome \}\}/);
  assert.ok(outcomes.includes('python=%s\\n'));
  assert.ok(outcomes.includes('"$JS_RESULT" "$PYTHON_RESULT" "$STANDALONE_RESULT"'));
  assert.match(source, /name: Preserve all step outcomes\n        if: always\(\)/);
  assert.match(source, /uses: actions\/upload-artifact@[a-f0-9]{40}\n        if: always\(\)/);
  assert.match(source, /if-no-files-found: error/);
});

test('release evidence does not restore compiled targets across Ubuntu generations', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  const caches = source.split('uses: Swatinem/rust-cache@v2').slice(1);
  assert.equal(caches.length, 2);
  for (const cache of caches) {
    const settings = cache.split('      - name:')[0];
    assert.match(settings, /cache-targets: false/);
    assert.match(settings, /key:.*matrix.os/);
  }
});

for (const name of ['dot-rc-integration.yml', 'cloud-execution-bridge.yml']) {
  test(`${name}: ephemeral PostgreSQL endpoint is evaluated in a step`, () => {
    const source = readFileSync(new URL(`../../.github/workflows/${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /^    env:\r?\n\s+TEST_DATABASE_URL:.*job\.services/m);
    assert.match(source, /^        env:\r?\n          TEST_DATABASE_URL:.*job\.services\.postgres\.ports\['5432'\]/m);
    assert.doesNotMatch(source, /job\.services\.postgres\.ports\[5432\]/);
    assert.match(source, /permissions:\r?\n  contents: read/);
  });
}

test('complete candidate keeps both Ubuntu generations and native Windows', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  assert.match(source, /os: \[ubuntu-22\.04, ubuntu-24\.04, windows-2025\]/);
  assert.match(source, /os: \[ubuntu-22\.04, ubuntu-24\.04\]/);
  assert.match(source, /cloud_application::wss_tests/);
  assert.match(source, /sandbox-dispatch\/run_probe\.py --evidence/);
  assert.doesNotMatch(source, /--expect-gap|continue-on-error: true/);
});

test('control tests keep setup-python while child sandbox tests select system tools locally', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /echo \/usr\/bin >>.*GITHUB_PATH/);
  assert.match(source, /python-version: '3\.12'/);
  assert.match(source, /if \[ "\$RUNNER_OS" = Linux \]; then export PATH="\/usr\/bin:\$PATH"; fi/);
});

test('browser evidence never disables Chromium sandbox', () => {
  for (const path of ['cloud-connection-browser.py', 'ui-refactor-browser.py', 'policy-hooks-browser.py', 'workspace-snapshots-browser.py', '../services/cloud-gateway/tests/run_service_acceptance.py']) {
    const source = readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /--no-sandbox|chromium_sandbox\s*[:=]\s*False/);
    assert.match(source, /chromium_sandbox['"]?\s*[:=]\s*True/);
  }
});

test('release matrix runs actual OAuth process browser acceptance separately from synthetic UI', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  const job = source.split('  oauth-process-browser:')[1];
  assert.ok(job);
  assert.match(job, /cargo build --locked.*--bins/);
  for (const script of ['run_enrollment_process.py', 'run_agent_process.py']) assert.ok(job.includes(script));
  assert.match(job, /run_service_http\.py.*--binary "\$binary"/);
  assert.match(job, /run_service_browser_ci\.py.*--binary "\$binary" --chromium \/opt\/google\/chrome\/chrome/);
  assert.match(job, /source-sha\.txt/);
  assert.doesNotMatch(job, /continue-on-error|--no-sandbox|\|\| true/);
});

test('native integration and restart proofs use real OS credential services', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  assert.match(source, /dbus-x11 gnome-keyring/);
  assert.match(source, /dbus-run-session -- bash -euo pipefail/);
  assert.equal((source.match(/--features native-keyring-tests data::secure_file::native_tests/g) || []).length, 2);
  assert.match(source, /cargo fmt --all --check --manifest-path src-tauri\/Cargo.toml/);
  assert.doesNotMatch(source, /--skip|--ignored|continue-on-error: true/);
});


test('native credential evidence runs independently without masking failed full tests', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  const names = ['Complete native application regression', 'Independent native credential and restart proofs', 'Independent production warnings and source integrity'];
  for (const name of names) {
    const step = source.split(`      - name: ${name}`)[1]?.split('      - ')[0];
    assert.ok(step, name);
    assert.match(step, /if: always\(\) && steps.native_checks.outcome == 'success'/);
    assert.match(step, /set -euo pipefail/);
    assert.doesNotMatch(step, /continue-on-error|\|\| true|--skip|--ignored/);
  }
  assert.match(source, /id: native_checks/);
  assert.match(source, /native_root_cross_process_crash_fences \.\.\. ok/);
});

test('native and preliminary package regressions continue across binaries but still fail', () => {
  const cases = [
    ['dot-rc-integration.yml', 'Complete native application regression', 2, 'bash'],
    ['linux-rc-packages.yml', 'Required full Rust regression with private Secret Service', 1, 'bash'],
    ['windows-rc-packages.yml', 'Required full Rust regression', 1, 'pwsh'],
  ];
  for (const [file, name, count, shell] of cases) {
    const source = readFileSync(new URL(`../../.github/workflows/${file}`, import.meta.url), 'utf8');
    const step = source.split(`      - name: ${name}\n`)[1]?.split('      - ')[0];
    assert.ok(step, name);
    const commands = step.split('\n').map(line => line.trim()).filter(line => line.startsWith('cargo test '));
    assert.equal(commands.length, count, name);
    for (const command of commands) {
      assert.match(command, /^cargo test --no-fail-fast /, name);
      const args = command.split(' 2>&1 | ')[0].split(' ').slice(3);
      assert.deepEqual(args.sort(), ['--locked', '--manifest-path', 'src-tauri/Cargo.toml'].sort(),
        `${name}: retain the complete unfiltered target set`);
    }
    assert.doesNotMatch(step, /continue-on-error|\|\| true|--skip|--ignored/, name);
    if (shell === 'bash') {
      assert.match(step, /set -euo pipefail/, name);
      assert.match(step, /dbus-run-session -- bash -euo pipefail/, name);
    } else {
      assert.match(step, /if \(\$LASTEXITCODE -ne 0\) \{ throw 'Windows Rust regression failed' \}/, name);
    }
  }
});
