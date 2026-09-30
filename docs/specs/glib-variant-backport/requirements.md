# 需求文档：glib-variant-backport
## 功能概述
Repair the active Linux GLib 0.18.5 VariantStrIter unsound out-pointer without changing the Tauri major dependency family or hiding RustSec findings.
## 需求列表
### FR-1 Exact narrow upstream backport
WHEN building the desktop dependency graph, the project SHALL select the complete official glib 0.18.5 crate with only gtk-rs commit b5a4071e439bef2b5eea76c3aa25e5ae84839e34 applied to src/variant_iter.rs. Version, API, manifests, license and all other source files remain upstream-identical.
### FR-2 Verifiable provenance and no extra remaps
WHEN verifying, the helper SHALL bind the official crate SHA256, all source-file hashes and exact two-line patch; reject missing/extra/altered files, links, extra path/git/alternate-registry dependencies, Cargo patch/replace/source overrides and unreviewed Cargo configuration.
### FR-3 Preserve advisory visibility
WHEN auditing, the helper SHALL retain the unfiltered product-lock report and a separately labelled official registry-identity GLib report. The latter must still contain RUSTSEC-2024-0429. A path dependency omitted by cargo-audit is not a clean upstream audit. No release gate or raw-zero claim is changed.
### FR-4 Reproducible optimized regression
WHEN validating, five official unpatched optimized iterator controls SHALL fail reproducibly; all nine fixed behavioral regressions SHALL pass. Provenance, graph and audit mutation cases SHALL fail closed.
## 非功能需求
NFR-1 No broad Tauri upgrade, release/publish authorization, production changes or dependency-version churn. Native/system GLib safety is outside this source backport.
## 依赖关系
Official crates.io glib 0.18.5 archive, upstream fix commit, RustSec advisory DB, Rust 1.98.1, native GLib libraries and cargo-audit 0.22.2.
## 验收标准
- [x] FR-1 and FR-2 exact-source inventory and remap rejection
- [x] FR-3 both real raw audit streams retained with unsound advisory visible
- [x] FR-4 five red controls, nine green regressions, adversarial checks
