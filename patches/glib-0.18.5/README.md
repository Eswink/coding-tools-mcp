# GLib 0.18.5 narrow source backport

This directory describes the **unmodified official crate plus one upstream fix**.
The crate's 121 files are preserved under `vendor/glib-0.18.5`, including the
original MIT `LICENSE`, `COPYRIGHT`, normalized/original manifests, README and
`.cargo_vcs_info.json`. Only `src/variant_iter.rs` differs.

- Official archive: https://static.crates.io/crates/glib/glib-0.18.5.crate
- SHA256: `233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`
- Original crate source commit: `42b9caf98e03ded086362d9653ca58fe94dc8658`
- Exact fix: https://github.com/gtk-rs/gtk-rs-core/commit/b5a4071e439bef2b5eea76c3aa25e5ae84839e34
- Advisory: https://rustsec.org/advisories/RUSTSEC-2024-0429.html

`RUSTSEC-2024-0429.patch` changes `let p` to `let mut p` and `&p` to `&mut p`,
allowing the C variadic out-argument to update the local pointer soundly.
`provenance.json` records every original/patched file hash and the patch/license
hashes. The verifier recomputes them from the independently pinned official
archive; editing the inventory cannot authorize another source change.

`upstream-identity.Cargo.lock` is a **one-package diagnostic identity**, not the
product lockfile, dependency graph, build result or filtered replacement audit.
It retains the real original registry identity and checksum for cargo-audit,
which otherwise skips a patched local path crate. Its unsound advisory must stay
visible beside the original unfiltered product-lock report.

See `docs/releases/glib-variant-backport.md` for reproduction and limitations.
