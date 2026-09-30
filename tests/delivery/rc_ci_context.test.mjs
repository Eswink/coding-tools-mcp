import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

test('portable gateway targets exist and retain CLI contracts', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  const command = source.split('\n').find(line => line.includes('--lib --test'));
  assert.ok(command);
  const target = command.match(/--test ([a-z_]+)/)[1];
  assert.ok(existsSync(new URL(`../../services/cloud-gateway/tests/${target}.rs`, import.meta.url)), target);
  assert.equal(target, 'service_contracts');
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
