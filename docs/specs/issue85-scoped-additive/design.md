# 设计文档：issue85-scoped-additive

## 概述
Covers FR-1 through FR-5. The additive path is source/audit identity → actual Tauri Cargo runner → rustc compiler-input trace → pre-bundle emitted ELF → exact DEB marker transform → trusted data-only replay.

## 技术方案
Use Python3.12 standard-library collectors and parsers. Keep source verification and paired advisory semantics unchanged. Pin Tauri CLI 2.11.4 (upstream 8909f221d1515955fc843808032bdc5d62209c96), Rust1.98.1 and cargo-audit0.22.2. Resolve actual Rust/Cargo binaries with the selected toolchain, not rustup shim hashes.

### Production invocation and process boundaries
The collector invokes npm run tauri -- build --config src-tauri/Ubuntu桌面v1.json --bundles deb --target x86_64-unknown-linux-gnu --runner ABSOLUTE_SCRIPT -- --locked --message-format=json.
The runner accepts only build --locked --message-format=json --bins --features tauri/custom-protocol --release --target x86_64-unknown-linux-gnu in src-tauri. It forwards/captures Cargo stdout and stderr concurrently without adding text, preserving exits/signals and capture failure. The rustc wrapper inherits streams without buffering live metadata notifications and preserves Cargo jobserver FD/FIFO state with explicit pass_fds as appropriate. No shell and no unrestricted environment capture.

A newly owned external target has no compiled cache. Reject inherited CARGO_BUILD_BUILD_DIR, target/flags/wrappers/RUSTC/RUSTDOC/profile/config overrides. Check both Cargo config names in searched source ancestors and CARGO_HOME. Use only reviewed explicit child environment fields. Required root/GLib artifact events have fresh=false. Keep full locked metadata, selected normal/build feature tree and complete raw compiler JSON.

### Compiler-input lineage
Capture each invocation separately with exact args, cwd, real compiler identity, target, package/source identity and successful output hashes. Read explicit extern paths before/after compilation and require equality. Associate rmeta and rlib co-outputs with the same successful invocation and exact source hash. An input edge uses the consumed artifact's path/hash, never a sibling hash. Reconcile after all compilers finish; pipelined rmeta consumers may start before producer exit. Reject cycles, duplicate output owners, changed inputs, target/host confusion, query/test/check-only proof and missing ancestry. Cargo probes pass through but do not count.

Pinned Linux output rules cover normal lib/rlib, metadata, bin, cdylib, dylib, proc-macro and staticlib; repeated/comma-separated crate types are supported. Reject unknown output-affecting forms for proof units, including -o and explicit emit output paths. Cargo's uplifted executable must have the same bytes as the root rustc output. Extern arguments make crates available; this does not establish complete native-linker consumption or retained machine code.

### Copies and file ownership
Copy the selected GLib rlib and root executable before returning to Tauri. After successful bundle, require restored target bytes unchanged. Cargo may hardlink aliases inside its fresh target; account for all aliases there. Separately created evidence copies have st_nlink=1 and share no inode with target or each other. Traverse parents using no-follow directory descriptors; compare stable descriptor identity/size/timestamps before/after reads/copies. No symlink ancestor or path escape.

### DEB and ELF contract
Only ar members debian-binary (2.0 newline), control.tar.gz and data.tar.gz, in order. Pinned short BSD/common names are space-padded, no extended identifiers. Accept regular GNU tar headers for ordinary directory/file entries, arbitrary entry ordering, no links/special/extension records. Control contains control and md5sums. Package is coding-tools-mcp; executable is coding-tools-mcp-desktop; version stays the actual source RC; architecture amd64.

The current data regular set is the desktop executable, usr/share/applications/Coding Tools MCP.desktop, and hicolor 32x32,128x128,256x256@2 app PNGs. Corresponding directories are permitted. No install scripts/resources are configured. Retained tar mtimes mean archive reproducibility is not claimed.

Require one source __TAURI_BUNDLE_TYPE_VAR_UNK and construct expected bytes by exactly replacing it with __TAURI_BUNDLE_TYPE_VAR_DEB. Existing DEB strings remain unchanged. Require equal length/full bytes, valid little-endian ELF64 amd64, marker wholly in one readable nonwritable file-backed PT_LOAD, no writable mapping alias. Check filesz≤memsz, header/segment ranges, fixed-width overflow, alignment and offset/vaddr congruence.

### Resource bounds
DEB/ar ≤256MiB; cumulative decompressed tar ≤512MiB; entries≤4096; member≤256MiB; control≤1MiB; encoded path≤1024 bytes; ELF≤256MiB; GLib proof≤128MiB. JSON file≤64MiB, record≤4MiB, depth≤64, trace count≤8192, argv count≤4096, argument≤16384 bytes, total trace≤64MiB, retained evidence≤1GiB. Exact integer fields reject bool/float aliases. Reject duplicate keys/nonfinite values.

Use bounded incremental gzip decoding and check eof/unused/trailing data; reject concatenated streams. Parse every tar header; reject unsupported PAX/GNU longname/longlink/sparse, devices, symlinks/hardlinks, malformed/trailing nonzero bytes, missing terminal zero blocks, duplicate normalized names, path escapes, setuid/setgid. No broad normalization on disagreement.

## 数据模型
Envelope schema1 binds exact source SHA/tree/version/target and source-input hashes, producer repository/workflow/run/attempt/job/platform, commands/exits/toolchain identities, source-audit summary, all raw evidence file hashes/sizes, selected compiler outputs and package identities. It has fixed engineering scope and false global flags. The trusted envelope digest is a required external argument. Compiler trace records have unique invocation IDs, argv/cwd/source/target, input/output identities, start/end diagnostics and exit; times do not invent metadata emission or impose non-pipelined ordering.

## API 设计
Collector CLI collect produces an owned evidence directory; internal build and rustc-wrapper entrypoints are only for reviewed Tauri/Cargo invocation. Data-only verify takes trusted source/producer/digest inputs and reconstructs the scoped result. Contract verifies complete events, source/audits and inventory. Link module captures/reconciles compiler inputs. DEB module validates structure and exact marker transform. No consumer executes payloads or changes GITHUB identity.

## 文件结构
- scripts/desktop_glib_build_evidence.py
- scripts/desktop_glib_build_contract.py
- scripts/desktop_glib_deb.py
- scripts/desktop_glib_link.py
- scripts/desktop_glib_build_evidence_tests.py
- scripts/desktop_glib_deb_tests.py
- scripts/desktop_glib_link_tests.py
- .github/workflows/issue85-desktop-glib-deb.yml
- docs/specs/issue85-scoped-additive/requirements.md
- docs/specs/issue85-scoped-additive/design.md
- docs/specs/issue85-scoped-additive/tasks.md

## 设计决策
Keep all existing validators/config/dependency/version files unchanged. The current hooks run unchanged. Same-build compiler events are insufficient, so record input/co-output ancestry. Rmeta pipelining is supported, not disabled. A limited engineering success does not change installed/security/release flags.

## CI 与信任
Only push branches ci/issue85-desktop-glib-deb-*; no dispatch/PR/tag/workflow_run trigger. Read-only contents permission, no persisted checkout credentials, no secrets or production environment. Ubuntu22 builds with Python3.12; Ubuntu24 explicitly uses Python3.12 for data-only replay. Upload immutable artifact ID/digest and envelope digest as authenticated job outputs; download by ID. Raw ZIP audit independently verifies outer size/digest/source/run plus upload ID association with exact run-attempt job/step logs. Artifact API JSON alone does not establish job/attempt. All jobs and raw evidence must be reviewed at exact candidate before acceptance.

## 测试策略
Cover source/tool/env/target/producer/digest mismatches; compiler truncation/errors/duplicates/features/profile; rmeta pipelining and absent ancestry; stdio/jobserver/signals; descriptor/hardlink ownership; every parser/bounds/marker rejection; filtered/changed paired audits and false flags. Retain existing source/dependency/package/consumer suites. Real fresh Tauri build, authenticated independent replay and mutation of actual emitted ELF/DEB are mandatory.

## 风险评估
HIGH trust boundary: source/workflow/compiler/isolated runner are trusted. Trace is authenticated producer evidence, not independent recompilation or resistance to malicious toolchain/privileged mutation. Parser disagreements stop for review. AppImage, native linker/code retention, installed Ubuntu22/24, system libraries, Windows and release remain open.
