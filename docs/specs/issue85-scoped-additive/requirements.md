# 需求文档：issue85-scoped-additive

## 功能概述
Add nonpublishing Ubuntu22 evidence connecting the verified local GLib backport's actual Rust compiler-input provenance to the emitted desktop ELF and exact DEB payload. Baseline is PR89 44ff88373d76b54a22d72eba17c0c7989e0be805. This is an engineering proof, not installed-app or security/release approval.

## 历史经验与坑
Cargo artifact events alone do not show compiler-input ancestry. Cargo pipelines rmeta before rlib completion. Tauri 2.11.4 mixes frontend/hook stdout with Cargo and deliberately replaces a 25-byte UNK bundle marker with DEB. Existing DEB literals may already occur. Native linker consumption and machine-code retention are separate unproven claims.

## 范围边界
In scope: eleven additive paths, real locked Tauri production build, compiler event/input trace, original paired audits, strict DEB byte binding, bounded data-only independent replay and isolated engineering CI.
Out of scope: existing validator changes, dependency/version changes, AppImage transformations, native-linker instrumentation, installs, system-library safety, Windows/Issue86, FINAL dispatch, main/release integration, tags, Releases or production credentials.

## 需求列表
### FR-1: Bind exact source, tools and original audit identity
Priority: Must. WHEN collecting THEN the producer SHALL require the exact clean source/tree/version, known source/config hashes, real Rust/Cargo 1.98.1 executables, locked Tauri 2.11.4, Python 3.12, cargo-audit 0.22.2, fresh target and absence of inherited compiler/Cargo overrides. WHEN reading GLib THEN it SHALL reuse the existing official archive/exact patch/config/metadata/paired-audit checks and retain the unfiltered original RUSTSEC-2024-0429 report. IF identity or source changes THEN it SHALL fail without a positive receipt.

### FR-2: Capture real product compiler-input provenance
Priority: Must. WHEN Tauri invokes the reviewed absolute runner THEN it SHALL pass exact reviewed argv to real Cargo, retain and forward unfiltered streams and preserve status/signals. WHEN Cargo invokes rustc THEN the wrapper SHALL preserve argv/cwd/live metadata/streams/jobserver and record only reviewed environment fields. WHEN a relevant compilation succeeds THEN it SHALL bind source and explicit extern hashes to emitted rmeta/rlib co-outputs and require target-only ancestry from the local GLib unit to the desktop bin. IF an event/unit/input is missing, stale, substituted, failed or inconsistent THEN it SHALL reject. WHILE Cargo pipelines metadata THE verifier SHALL allow a consumer before producer exit, reconciling successful co-outputs after the full build.

### FR-3: Verify exact emitted ELF to DEB transformation
Priority: Must. WHEN Cargo completes THEN its runner SHALL independently copy the emitted main ELF and GLib rlib before returning to Tauri. WHEN Tauri succeeds THEN restored main bytes SHALL match the pre-bundle copy. WHEN inspecting the actual DEB THEN the verifier SHALL require Package coding-tools-mcp, original engineering version, amd64 and exact binary path usr/bin/coding-tools-mcp-desktop. It SHALL accept only the unique UNK-to-DEB replacement in one readable nonwritable file-backed LOAD, with full remaining bytes identical. IF any other byte or structural condition differs THEN it SHALL reject.

### FR-4: Authenticate independent replay
Priority: Must. WHEN replaying THEN trusted source/producer/version/envelope digest and immutable upload artifact ID/digest SHALL come from reviewed CI outputs, not self-asserted receipt data. The replay SHALL be data-only and not execute downloaded payloads, build, install or spoof producer environment. The independent final audit SHALL authenticate raw ZIP size/digest and run/source metadata plus exact job-attempt upload-log association. IF any association is missing THEN acceptance SHALL remain blocked.

### FR-5: Bound parsing and preserve scope
Priority: Must. WHEN reading files or archives THEN the verifier SHALL use the concrete bounds and stable no-follow ownership checks in design.md. It SHALL retain installed_desktop_bytes_verified=false, security_approved=false, release_approved=false, publish_approved=false and raw_zero_claim=false. Success SHALL say compiler-input provenance plus exact emitted-ELF-to-DEB binding, never full native-linker consumption, retained code or installed/security approval.

## 非功能需求
NFR-1: New source and test files each remain below 500 lines; eleven paths and zero existing edits.
NFR-2: No shell for captured compiler commands; stream fidelity, finite time/resource limits, duplicate-key and path/identity rejection.
NFR-3: Explicit trusted reviewed source/workflow/compiler/isolated-runner assumption. Evidence is not an independent recompilation or defense against a malicious compiler or privileged concurrent mutator.

## 依赖关系
Existing verify_glib_backport, exact_build_audit and rc_version_gate helpers; official GLib archive/RustSec database; pinned native tooling and official Actions; isolated Ubuntu22 producer and Ubuntu24 Python3.12 replay.

## 验收标准
- All FR rejection conditions have actual adversarial tests; existing source39 and paired3 plus dependency/package/consumer regressions stay intact
- A fresh real Tauri candidate build passes, authenticated replay agrees and actual ELF/DEB byte mutations reject
- No source/policy/dependency/version edits outside the eleven paths or promotion of global flags
