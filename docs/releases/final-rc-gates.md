# Full RC packaging preparation and remaining release gates

This workflow prepares structural package evidence only. It does not select a version, create a tag, publish a release, or certify Windows isolation. Full original Epic32 scope remains required.

## Immutable-source contract
Either manually dispatch `final-rc-packages.yml` on the exact candidate commit with an owner-selected `major.minor.patch-rc.N` already present in all six committed version fields and a successful `dot-rc-integration.yml` run for that identical commit. Required jobs include the three native platforms, two real-transport platforms, browser and oauth-process-browser. Alternatively, after the owner has selected the version and engineering gates pass, the parent may create `release/full-rc-candidate-*` pointing at that same immutable commit. This push derives the committed version, reads successful exact-SHA runs for the fixed integration workflow, selects the unique highest run ID, then revalidates the run and its latest seven-job attempt. Missing or ambiguous evidence fails immediately without polling. Branch creation does not change source, tags or releases. Dispatch continues to require explicit version and run inputs. Every returned job must succeed; a historical green run, skipped job, different source or partial matrix fails closed.

Linux packages are built on Ubuntu22.04, then the identical DEB/AppImage bytes are installed and exercised on both22.04 and24.04. Windows NSIS is built and checked through the existing fresh standard-user installed acceptance. Preliminary fde46cc packages have been built in Actions and actually downloaded: both Ubuntu22/24 DEB/AppImage installed matrices pass, and Windows NSIS standard-user installed acceptance passes while required Windows full regression fails. These unchanged0.6.0-rc.4 engineering bytes are NOT_FINAL/NOT_PUBLISHABLE. Final selected-version/source packaging remains pending.

The four production Rust lockfiles are audited through actual cargo-audit0.22.2 JSON. npm audit JSON must show zero vulnerabilities. No advisory is ignored and no success-shaped receipt is fabricated. Issue84's devalue remediation is separately required before the audit can pass.

Bundle receipts bind version, source SHA, tree, run, installer digest and installed payload. Checksums cover packages and retained evidence. `publish_approved` always remains false. Windows security-profile and complete release-ledger gates survive successful package assembly.

## Historical main-PR failures and precise repair boundaries
### Additive laboratory scope is stale for a cumulative candidate
Run36376602012 job108783623181, commit2c5d133, fails before tests:
https://github.com/Eswink/coding-tools-mcp/actions/runs/36376602012
The rejected paths were Cargo.lock/Cargo.toml, harness/state.rs and tools context/dispatch/exec/execution_sandbox/git/git_runner/git_runner_tests/mod/session. The workflow compares all changes against main758c60a with a historical incremental allowlist. The missing artifact is secondary: failure occurred before candidate.json was written.

Do not fix this by allowing `src-tauri/**`, dropping the scope check, or skipping protocol regressions. Separate two contracts:
1. Preserve the historical additive guard for its intended isolated increment branch.
2. For cumulative main PRs, run the same complete protocol/offline/fault-proxy regressions unconditionally and validate an explicit reviewed cumulative source manifest against a pinned baseline, including deletions and file digests. The manifest should be produced from reviewed final source, not auto-accepted from the PR's own diff. Record a distinct cumulative classification.
The exact final manifest cannot be frozen while engineering/security/version changes remain pending. The new packaging gate requires a clean exact-source integration run; it is not a replacement for this explicit main-PR scope repair.

### Stable-only provenance validator is incorrectly applied to RC source
Run36376602015 job108783622981 fails with: project version must use no-leading-zero major.minor.patch.
https://github.com/Eswink/coding-tools-mcp/actions/runs/36376602015
`发布来源验证v4.yml` calls stable `发布版本校验v4.py` on RC source. This is classification mismatch, not evidence that all six version fields disagree.

Precise repair: keep stable verifier and its positive/negative regression unchanged. The PR source-validation workflow should read version once and select either strict stable fullmatch or strict numbered RC fullmatch; all other formats fail. In the RC branch call `rc_version_gate.py --expect-sha "$GITHUB_SHA"`; in stable branch retain existing stable verifier. Run both stable and RC negative test suites on every invocation. Never make the stable regex accept prereleases, never strip `-rc.N`, and never bypass clean-tree/exact-SHA checks. Release-tag publication remains a separate operation.

### Hardcoded historical versions remain historical
Existing linux/windows-rc-packages.yml pins0.6.0-rc.4; prior desktop workflow pins0.6.1-rc.1 and a reduced desktop-only allowlist. The new parameterized workflow does not alter those historical policies or assert their versions are available. Stable0.6.0 and desktop0.6.1-rc.1 already exist. Owner version choice and tag/release collision verification remain required.

## Windows implementation investigation and security decisions
Verified provider run36695185909 at7dc2aed: all three zero-capability LPAC modes deny WinSock catalog registry opens (error5), read provider DLLs, then fail WSAStartup10107. Ordinary AppContainer initializes and demonstrates actual denied networking, but fails the stronger outside-AAP-file read boundary. Startup failure is never network-denial evidence.

- Keep zero-capability LPAC: preserves the intended current boundary, but functional networking proof and production execution remain blocked.
- Add registryRead: Microsoft describes HKLM-hive read access, broader than the two runtime catalog keys. Protected synthetic canaries do not prove confidentiality for third-party machine configuration under inherited ACLs. This is a security-profile change requiring an explicit decision; it has not been implemented.
- Host-opened socket or ordinary AppContainer: changes authority/boundary and cannot serve as an equivalent passing test.
- Separate disposable VM/container: could isolate host-registry secrets but needs another supported execution platform, workspace mapping, lifecycle and resource design. It is a larger engineering decision, not a completed fallback.

The measured initialization error does not prove every offline runtime is unusable or that registryRead is necessary. Test-only exact Python/Node/npm/Git/shell observations are being collected with the original zero-capability boundary. Preparation failures are explicit failed required rows, not compatibility results or passing security tests.

No system registry ACL change, network capability, global preparation or persistent grant was made. See Microsoft's capability/access semantics: https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer and https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox . The latter API is explicitly experimental and is not adopted.
