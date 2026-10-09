# Manifest-only SQLx dependency proposal

## 概述

Corresponds to FR-1/FR-2/FR-3. Keep exact F13 source clean and use a separate checkout only for read-only research. No Cargo invocation, resolution, build or audit is performed. Restore two whole official source packages in a new independent F13 checkout and edit only their normalized Cargo.toml files.

## 技术方案

FR-1: parse the exact TOML lock graph rather than assume selected build reachability. Bind desktop598/local44/cloud-agent121/gateway230 locked package sets and their original audit identities. Current gateway manifest already excludes default features and activates only PostgreSQL; two optional registry package paths still make RSA present in the lock. The existing RustSec finding has no patched version.

FR-2: begin a future exact manifest-only patch for sqlx and sqlx-macros-core. Both have optional sqlx-mysql dependencies and weak MySQL references in migrate/uuid and other feature tables. SQLx-macros itself exposes a mysql feature forwarding to macros-core/mysql: its compatibility and Cargo validation must be examined, not silently treated as covered by two packages. An unused cfg label is not an enabled MySQL implementation or proof of removal. No optional PostgreSQL branch, runtime/TLS feature, migration macro code or embedded checksum may be changed. Product current-feature parity and rejected unsupported MySQL requests need meaningful future controls. A broader driver/API rewrite is an alternative requiring a new specification, not a permitted shortcut.

FR-3: future patch root and package inventories are explicit; restored original files retain modes/bytes and manifests have precise before/after diffs. Regenerate Cargo.lock through actual compatible Cargo with these manifest dependencies, never edit entries by hand. Compare all changed package rows and source provenance. If resolution retains RSA or requires third-package edits, reject this candidate and report the exact remaining path. Real fresh four audits and selected/conservative compiler graph, binary/source correspondence and Postgres migration behavior follow independent source/startup admission.

## 文件结构

Current delivery adds a source-only candidate and ordinary controls to these external specifications and prior immutable readonly evidence. Existing F13 product source, every lock, migrations, compiler artifacts, raw audit reports and production vendor package are unchanged. Vendor paths are services/cloud-gateway/vendor/sqlx and services/cloud-gateway/vendor/sqlx-macros-core. Product Cargo.toml and every product lock remain exact F13. Future root Cargo may use explicit external --config patch.crates-io paths; no patch is wired now.

## 对应需求

FR-1 binds original negative audits and both dependency paths. FR-2 protects all PostgreSQL semantics and requires provenance of manifest-only changes. FR-3 reserves normal lock generation, compatibility, four fresh audits and source/build/install qualification for a later authorized scope.

## Concrete source mechanism and controls

FR-2: authenticate cached .crate whole SHA against original Cargo.lock before memory tar parsing; require canonical regular members only and exact package root, then restore193 files with O_EXCL and original executable classification. Seal original full bytes/mode/length/hash before transformation. Parse original TOML and remove only sqlx-mysql optional table, quoted weak reference entries, and its strong mysql feature entry. Preserve semantic TOML of every other key; SQLx mysql forwards only to original macros; core mysql is empty. Preserve all other191 package files, all1840 F13 paths, third manifest official bytes, both migrate! source modules and migrations. Ordinary feature closure computes package features/strong and weak forwarded references to a fixed point using the original PostgreSQL selection; it is an explicit TOML model, not Cargo resolution. Negative controls mutate Postgres selection/optional dependency, manifest scope, source bytes and unsupported feature requests; failures must remain failure-first. The candidate admission helper only rejects unsupported requested features, never mints authority or invokes Cargo.
