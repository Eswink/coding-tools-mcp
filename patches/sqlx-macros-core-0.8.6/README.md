# sqlx-macros-core 0.8.6 — drop unused optional mysql/sqlite drivers (thin path patch)

Same C21b thin layout as `patches/sqlx-0.8.6/`: Cargo.toml-only intentional edit;
pristine upstream `src/` via `crate/upstream-src.tar.gz` + `build.rs` extract into
gitignored `crate/extracted/`.

- Official archive: https://static.crates.io/crates/sqlx-macros-core/sqlx-macros-core-0.8.6.crate
- SHA256: `19a9c1841124ac5a61741f96e1d9e2ec77424bf323962dd894bdb93f37d5219b`
- Patch: `drop-optional-mysql-sqlite.patch` (Cargo.toml only)
- Selected by gateway `[patch.crates-io]` as
  `sqlx-macros-core = { path = "../../patches/sqlx-macros-core-0.8.6/crate" }`.

Does **not** close whole #85. Never claim Windows PASS/QUALIFIED/FINAL.
