# sqlx 0.8.6 — drop unused optional mysql/sqlite drivers (thin path patch)

**Layout (C21b, topology-safe):** `crate/` is the `[patch.crates-io]` path target.
It keeps a **Cargo.toml-only** intentional edit (drop unused optional `sqlx-mysql` /
`sqlx-sqlite` deps + feature forwards). Pristine upstream `src/` bytes ship as
`crate/upstream-src.tar.gz` (binary) and are extracted by `crate/build.rs` into
gitignored `crate/extracted/` at build time. No full upstream tree is committed.

- Official archive: https://static.crates.io/crates/sqlx/sqlx-0.8.6.crate
- SHA256: `1fefb893899429669dcdd979aff487bd78f4064e5e7907e4269081e0ef7d97dc`
- Original crate source commit: `bab1b022bd56a64f9a08b46b36b97c5cff19d77e`
- Patch: `drop-optional-mysql-sqlite.patch` (Cargo.toml only)
- Why: gateway enables postgres-only sqlx features; stock sqlx still locks optional
  mysql/sqlite drivers → `rsa 0.9.10` / RUSTSEC-2023-0071 in `Cargo.lock` even when
  `cargo tree -i rsa` is empty. Path-patching these crates lets a controlled lock
  regeneration omit the unused closure **without** `--ignore`.

`services/cloud-gateway/Cargo.toml` selects this via
`sqlx = { path = "../../patches/sqlx-0.8.6/crate" }`.
Product sqlx features remain `runtime-tokio-rustls,postgres,migrate,macros,uuid`
with `default-features = false` (no mysql).

This batch does **not** close whole packaging #85 (GLib installed-bytes / yoke /
FINAL / Win remain OOS). Never claim Windows PASS/QUALIFIED/FINAL.
