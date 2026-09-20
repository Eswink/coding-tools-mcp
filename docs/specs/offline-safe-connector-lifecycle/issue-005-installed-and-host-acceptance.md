# ISSUE-005 — Offline-safe end-to-end and installed acceptance

Status: OPEN — CI INSTALLED ACCEPTANCE ACTIVE; REAL CHATGPT HOST CASES DEFERRED  
Parent: [plan.md](plan.md)  
Depends on: ISSUE-003 and ISSUE-004  
Round: 5 / 5

## Objective

Validate the completed Level A candidate across real packaged desktop artifacts and both supported CI operating-system families, while keeping the explicitly deferred real ChatGPT host cases separate.

This issue is the final project gate. It must not turn synthetic or CI evidence into a claim about ChatGPT host UI behavior.

## Acceptance partitions

### A — Source and protocol lifecycle

Already established in Rounds 3–4 and must remain green:

1. workspace Online -> Offline -> Online;
2. active owner survives pause/resume;
3. unrelated/foreign chat remains non-disclosing;
4. 100 repeated non-owner authorization calls create no pending grant/event;
5. OAuth access/refresh rotation succeeds while execution is Offline;
6. typed `WORKSPACE_OFFLINE` is not an OAuth challenge;
7. stale runtime generation cannot mutate a replacement listener;
8. tunnel membership/public origin is invariant under pause/resume;
9. async task drain-control remains available only inside the owning chat domain;
10. recovery-required remains stronger than resume/availability.

### B — Cross-platform packaged build

Required CI evidence:

- Windows 2025/2022 runner:
  - frontend check/build;
  - full Rust check/test/`-D warnings`;
  - actual Tauri NSIS package build;
  - silent package install;
  - verify registered install entry and installed executable exists;
  - uninstall package and verify removal.
- Ubuntu 24.04 runner:
  - frontend check/build;
  - full Rust check/test/`-D warnings`;
  - actual Tauri Debian package build;
  - install the produced `.deb` with dpkg/apt;
  - verify package registration and installed executable;
  - remove package and verify package registration disappears.

The installed smoke proves package/install lifecycle only. It does not launch a graphical WebView in headless CI.

### C — Process/network lifecycle available without ChatGPT

Where feasible in automated tests:

- listener startup/shutdown/restart;
- tunnel route policy/invariance tests;
- network/tunnel health regression;
- long-running task drain/recovery regression;
- process restart persistence/recovery tests.

These are existing suites and should be captured from the cross-platform run.

### D — Real ChatGPT host acceptance — DEFERRED

The user explicitly deferred the operationally expensive real-host setup.

Still open:

- actual ChatGPT reconnect-card behavior for Online -> Offline -> Online;
- connector visibility for another person sharing the same ChatGPT account;
- OAuth host refresh UX while execution is Offline;
- UI close/reopen through a real ChatGPT connector;
- machine/network interruption seen by the real host.

These items block the **final claim that the reconnect UX is fixed**, but they do not block completing the code and packaged-build engineering candidate.

## Installed artifact safety

Round 5 CI artifacts are acceptance artifacts only:

- do not create a GitHub Release;
- do not push a version tag;
- do not publish installers;
- do not mutate release/version files;
- do not sign with production secrets;
- upload CI artifacts with bounded retention only.

## Windows installation contract

The acceptance workflow should:

1. build `--bundles nsis`;
2. locate exactly one generated installer;
3. invoke NSIS silently with `/S`;
4. find the uninstall registration by `DisplayName = Coding Tools MCP` in HKCU/HKLM uninstall locations;
5. require an installed executable under the registered `InstallLocation` or display icon location;
6. invoke the registered uninstall command silently when possible;
7. verify the registration disappears.

If the Tauri-generated installer does not support the expected silent contract, record the exact result as a packaging blocker instead of weakening the check.

## Ubuntu installation contract

The acceptance workflow should:

1. build `--bundles deb`;
2. locate exactly one `.deb`;
3. inspect package name using `dpkg-deb -f`;
4. install it with apt/dpkg;
5. verify `dpkg-query -W` reports installed;
6. verify at least one executable installed under `/usr/bin` or package file list;
7. remove package;
8. verify `dpkg-query` no longer reports installed.

## Cross-platform source expectations

Windows and Ubuntu must both execute the full test suite because process/session behavior has platform-specific code.

A single Linux PASS is insufficient for final Round 5 CI acceptance.

## Failure policy

Any packaging/install failure is retained as evidence:

```text
FAIL
 -> record exact command / runner / artifact
 -> classify package vs source vs environment
 -> make one bounded correction
 -> rerun
```

Do not retry-until-green.

## Exit states

### ENGINEERING_CANDIDATE_PASS

May be reached when:

- Rounds 3–4 source/synthetic evidence is green;
- Windows packaged install lifecycle passes;
- Ubuntu packaged install lifecycle passes;
- cross-platform source regression passes;
- exact diff/evidence recorded;
- no production release was published.

### HOST_VALIDATED / DONE

Requires the deferred real ChatGPT cases.

Until then, final truth status is:

```text
engineering candidate: validated
real ChatGPT reconnect UX: UNCONFIRMED_ON_REAL_HOST
shared-account connector visibility: UNCONFIRMED_ON_REAL_HOST
```
