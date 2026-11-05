# sqlx-macros-core 0.8.6 — drop unused optional mysql/sqlite drivers

Vendored from the **unmodified official crates.io archive**, then **Cargo.toml only**
edited to remove unused optional `sqlx-mysql` / `sqlx-sqlite` dependencies and their
feature forwards. No `.rs` source changes.

- Official archive: https://static.crates.io/crates/sqlx-macros-core/sqlx-macros-core-0.8.6.crate
- SHA256: `19a9c1841124ac5a61741f96e1d9e2ec77424bf323962dd894bdb93f37d5219b`
- Original crate source commit: `bab1b022bd56a64f9a08b46b36b97c5cff19d77e`
- Patch: `drop-optional-mysql-sqlite.patch` (Cargo.toml only)
- Why: gateway enables postgres-only sqlx features; stock sqlx still locks optional
  mysql/sqlite drivers → `rsa 0.9.10` / RUSTSEC-2023-0071 in `Cargo.lock` even when
  `cargo tree -i rsa` is empty. Path-patching these crates lets a controlled lock
  regeneration omit the unused closure **without** `--ignore`.

`services/cloud-gateway/Cargo.toml` selects these via `[patch.crates-io]`.
Product sqlx features remain `runtime-tokio-rustls,postgres,migrate,macros,uuid`
with `default-features = false` (no mysql).

This batch does **not** close whole packaging #85 (GLib installed-bytes / yoke /
FINAL / Win remain OOS). Never claim Windows PASS/QUALIFIED/FINAL.
