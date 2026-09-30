# 任务清单：glib-variant-backport
## 概述
Narrow source backport plus separate advisory visibility and adversarial verification.
## 交付物清单（Scope-lock）
Only the vendor/source-provenance, regression/verifier/spec/docs paths listed in design and the src-tauri GLib manifest/lock selection. No other dependency versions, production code, release gates or hosted actions changed.
## 任务列表
- [x] 1.1 Preserve complete upstream crate and apply exact two-line fix
  - **证据块**: official archive SHA256 233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5; gtk-rs commit b5a4071e439bef2b5eea76c3aa25e5ae84839e34
  - **涉及文件**: vendor/glib-0.18.5, patches/glib-0.18.5, src-tauri/Cargo.toml, src-tauri/Cargo.lock
  - _需求: FR-1,FR-2_ ｜ _设计: 技术方案_
- [x] 2.1 Verify exact provenance, graph identities, absence of remaps and retained raw advisories
  - **证据块**: cargo-audit omits local path GLib from registry advisories; raw product report alone cannot prove resolution
  - **涉及文件**: scripts/verify_glib_backport.py, scripts/verify_glib_backport_tests.py
  - _需求: FR-2,FR-3_ ｜ _设计: 数据模型_
- [x] 3.1 Reproduce optimized red controls, run fixed regression and record limitations
  - **证据块**: all five upstream iterator methods reproduced SIGSEGV(-11) on Rust1.98.1
  - **涉及文件**: tests/glib-variant-regression, scripts/glib_backport_regression.py, docs/releases/glib-variant-backport.md
  - _需求: FR-3,FR-4_ ｜ _设计: 测试策略_
## 检查点
- [x] Spec gate before implementation
- [x] Exact source and all regression checks
- [x] Independent review and reviewed export
## 需求覆盖矩阵
|需求 ID|任务|设计章节|
|---|---|---|
|FR-1|1.1|技术方案|
|FR-2|1.1,2.1|技术方案|
|FR-3|2.1,3.1|数据模型|
|FR-4|3.1|测试策略|
## 文件变更清单
See scope-lock above. New verifier budget450lines, tests350lines, standalone regression runner150lines. Vendor source unchanged apart from the exact fix. New standalone regression does not build Tauri.
## 检查清单
- [x] Requirements and scope recorded
- [x] Revalidation after review

## Parent integration follow-on
- Exact unmodified upstream source was indexed before canonical import; the changed iterator helper has5direct callers atMEDIUM risk. `.gitnexusignore` explicitly includes this pinned vendor directory for future audits.
- Both Ubuntu native CI lanes now run the source verifier and optimized original/patched controls independently after successful native compilation, preserving failures and diagnostics. Windows does not link this Linux-only GLib dependency.
- Parent reran39verifier tests, locked all-target compilation, fmt, production warnings and workflow contracts. Hosted exact-source result and final package proof remain pending and are not part of the source-only completion above.
