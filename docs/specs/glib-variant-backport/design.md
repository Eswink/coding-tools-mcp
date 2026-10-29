# 设计文档：glib-variant-backport
## 概述
Covers FR-1 through FR-4 and NFR-1. GLib 0.18.5 creates an immutable pointer local, then passes its address through a variadic C call that mutates it. Rust optimization may retain NULL, violating CStr::from_ptr. The exact upstream fix makes both the local and out-reference mutable.
## 技术方案
Place all 121 official crate files in vendor/glib-0.18.5. Add only the src-tauri crates.io patch. Keep provenance outside the vendor directory so an exact file inventory can reject any extra source. Verify archive SHA256 and independently recompute expected patched bytes from the official archive. Cargo metadata must map every local package to a fixed approved manifest; all registry packages must use crates.io and original locked checksums. Reject all discovered Cargo config files and source-remapping environment variables before Cargo runs.
## 数据模型
Provenance JSON includes official URL/archive hash/upstream source commit/fix commit, original and patched file maps, license identity and patch hash. A diagnostic one-package upstream identity lock names the original glib registry package and checksum. It is explicitly not the product lock or a substitute for the full product scan.
## API 设计
scripts/verify_glib_backport.py --root ROOT --archive glib-0.18.5.crate verifies files/config/metadata. Optional paired --product-audit and --upstream-audit require unfiltered original reports and the retained upstream unsound advisory. Metadata is collected by a fixed cargo metadata --locked command, never accepted as a claim of a completed product build.
## 文件结构
vendor/glib-0.18.5, patches/glib-0.18.5, tests/glib-variant-regression, scripts/verify_glib_backport.py, scripts/verify_glib_backport_tests.py, scripts/glib_backport_regression.py, docs/releases/glib-variant-backport.md and this spec. src-tauri/Cargo.toml and Cargo.lock change only GLib source selection. Existing release gates stay unchanged.
## 设计决策
Exact immutable archive identity plus independent patch reconstruction prevents an edited inventory from blessing unexpected source. Registry warning visibility is separate from source-backport verification. No advisory ignore entry or fake newer version. A source check does not prove full Linux/Windows/macOS release builds or release approval.
## 测试策略
Five separate release-mode upstream iterator tests must fail at runtime, not compile failure. Nine patched tests exercise direct entry points, Unicode, empty strings, forward/reverse, mixed iteration, bounds and borrowing. Python mutations cover all inventory, graph/remap and advisory constraints.
## 风险评估
GitNexus cannot resolve the external impl_get symbol: UNKNOWN, never safe-zero. Manual upstream review finds five direct affected iterator callers. Linux GTK uses GLib; normal Windows/macOS graphs do not select it. Full product release compilation and native-library audit remain separate evidence.
## 检查清单
- [x] Five optimized upstream controls reproduced SIGSEGV on Rust 1.98.1
- [x] Exact upstream patch and archive checksum verified
- [ ] Parent independent review and full release evidence
