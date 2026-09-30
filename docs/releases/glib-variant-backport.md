# GLib VariantStrIter source backport: Issue85

## Scope and finding

Desktop Linux's normal GTK/Tauri dependency graph selects GLib 0.18.5.
The inspected normal/build Windows MSVC and Apple Darwin graphs do not select it.
This is target/package selection, not a function-level exploitability claim.

RUSTSEC-2024-0429 identifies a real unsound variadic C out-argument in
`VariantStrIter::impl_get`: an immutable `&p` points to storage that C mutates.
On optimized Rust 1.98.1, all five affected iterator methods reproduced NULL
dereferences and SIGSEGV. The exact upstream fix changes `let p` to `let mut p`
and `&p` to `&mut p`.

Sources: [official upstream fix](https://github.com/gtk-rs/gtk-rs-core/commit/b5a4071e439bef2b5eea76c3aa25e5ae84839e34),
[RustSec advisory](https://rustsec.org/advisories/RUSTSEC-2024-0429.html).

## Source selection and provenance

`src-tauri/Cargo.toml` has one crates.io patch selecting `vendor/glib-0.18.5`.
The desktop lock changes only GLib's registry source/checksum lines; its version
and dependency edges are unchanged. No other dependency version or Tauri major
family is changed. No product version, release gate or publishing contract is
changed.

All 121 official crate files remain present, with original MIT license,
copyright, manifests and source identity. The only source delta is the exact
two-line upstream fix. Provenance and the reproducible patch are outside the
vendor directory, under `patches/glib-0.18.5`.

The checker independently reconstructs expected bytes from the official archive,
checks the complete inventory, and rejects extra/missing/tampered files and links.
It rejects additional Cargo patch/replace/path/git/alternate-registry remaps,
including target/workspace dependency sections, unknown local package identities,
unreviewed Cargo config files in project/ancestor/CARGO_HOME locations, and source
override environment variables. Rejection of all Cargo config files is deliberate
fail-closed behavior; review a necessary environment setting rather than adding a
broad bypass. Metadata reconciles the full lock and all resolved package IDs.

GitNexus cannot index the third-party `impl_get` in the pre-backport repository:
impact is UNKNOWN, not zero. Manual official-source review finds five affected
direct iterator methods: `next`, `nth`, `last`, `next_back`, `nth_back`.

## Reproduce

Use Rust/Cargo 1.98.1, Python 3.11+, native GLib/GIO development libraries and
cargo-audit 0.22.2. Keep outputs and the Cargo target directory outside the source.
Download the [official archive](https://static.crates.io/crates/glib/glib-0.18.5.crate)
to an external path; the checker requires SHA256
`233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`.

From the repository root:

```sh
python scripts/verify_glib_backport_tests.py --archive /external/glib-0.18.5.crate
python scripts/glib_backport_regression.py --root "$PWD" \
  --archive /external/glib-0.18.5.crate --output /external/new-regression-receipt
python scripts/verify_glib_backport.py --root "$PWD" \
  --archive /external/glib-0.18.5.crate \
  --audit-bin /verified/cargo-audit --audit-db /verified/advisory-db \
  --output /external/new-source-audit-receipt
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
```

The Linux regression runner extracts the original archive into a temporary
directory and builds two standalone test fixtures with the **same committed lock
and test source**. Each of five upstream controls runs in its own process and
must produce SIGSEGV; compile failures or other exit codes are not accepted as
negative evidence. The patched build must pass all nine tests covering direct
methods, Unicode/empty strings, mixed iteration, bounds and borrowed lifetimes.
The runner disables core dumps and retains stdout/stderr, toolchain, binary
hashes, selected GLib identity/features and test-source/lock hashes.

## Audit visibility is deliberately separate

The capture runs cargo-audit twice without ignore, severity or target filters:

1. The actual full `src-tauri/Cargo.lock`, retained byte-for-byte as raw JSON
2. The separately labelled original GLib registry identity, retaining
   RUSTSEC-2024-0429 as an unsound warning

This second diagnostic is necessary because cargo-audit omits the path-patched
crate from registry advisories. It is not a product dependency graph or a
replacement/cleaned lock. Missing, filtered or unexpectedly changed GLib advisory
evidence fails verification. Other product findings and warnings remain visible.

The actual audit binary hash, official clean advisory-db Git/tree/content
identities, commands/exit codes and raw report hashes are recorded. Null raw
cargo-audit database telemetry is left untouched; the independent snapshot
identity supplies that provenance. Preserve the complete receipt, not just its
summary; external trusted source/run identity is still needed for release use.

## Restored validation results and remaining boundary

- Official archive SHA256 and all 121 source/license hashes verified
- Five optimized upstream SIGSEGV controls reproduced; nine patched tests passed
- 39 adversarial Python tests passed, including requested remap/advisory cases
- Desktop `cargo fmt --all --check` passed without reformatting vendor code
- All-target locked metadata reconciled all 598 packages and four approved locals
- Cargo-audit 0.22.2 against official DB
  `9b3a3b73a7f42606494c943e95f8196e9994df46` retained both real raw reports
- Patched product scan: zero vulnerability-list entries and six unmaintained
  warnings; original GLib identity scan: RUSTSEC-2024-0429 unsound warning retained

The six product warnings are proc-macro-error and five unic-* maintenance
advisories. Their presence and the retained upstream GLib warning must not be
described as raw audit zero. All summaries explicitly set `raw_zero_claim=false`
and `release_approved=false`.

This evidence proves the narrow source backport and isolated regression only.
It does not certify a completed desktop artifact, native/system GLib security,
full Linux/Windows/macOS acceptance, or authorize release. A future compatible
upstream dependency migration can retire the patch, after equivalent validation.

The full added-file diff whitespace check reports two provenance-preserving
exceptions: the official LICENSE ends with a blank line, and the saved standard
unified patch contains a space-only context line. Both are retained byte-for-byte;
the non-vendor implementation and documentation diff has no whitespace errors.
