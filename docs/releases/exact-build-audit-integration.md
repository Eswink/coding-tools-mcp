# Proposed exact-build dependency evidence integration

**Engineering helper only. Existing final_rc_evidence.audits remains unchanged and its raw-zero requirement still blocks release. No artifact family can grant full release approval.** Parent review and actual product build proof are required before any release-contract change.

## What is delivered

`scripts/exact_build_audit.py` independently captures and verifies the exact stable-Cargo Rust package build. It never deletes lock entries, produces a cleaned substitute lock, suppresses advisories, invokes a panic-string fallback, changes dependency versions or replaces the selected toolchain.

Two separate states are retained:

- `raw_lock_audit=findings_present`, with the original real report, counts, advisory IDs and maintenance warnings unchanged
- `exact_build_audit=passed` only when the complete selected/compiled package and unit sets agree and no affected package participates in either the actual or conservative graph

The latter means only this exact Cargo Rust build. It does not mean raw audit zero, full supply-chain safety, native-library security, function-level exploitability, Windows sandbox acceptance or release approval.

## Collection in the existing cloud release build job

After clean exact-source checkout, owner-selected committed version validation, the existing pinned stable toolchain and cargo-audit0.22.2 installation, let the collector clone the official RustSec advisory repository into a new external path and pin that snapshot. Keep output outside the source checkout. Existing unreviewed compiler wrappers/flags are rejected rather than implicitly changing the audited build.

Run:

    python scripts/exact_build_audit.py collect \
      --root "$GITHUB_WORKSPACE" --expected-sha "$GITHUB_SHA" \
      --version "$APPROVED_PRODUCT_VERSION" \
      --target x86_64-unknown-linux-gnu \
      --output "$RUNNER_TEMP/exact-cloud-build-audit" \
      --audit-bin /verified/path/to/cargo-audit \
      --audit-db "$RUNNER_TEMP/advisory-db" --clone-advisory-db

This owns the actual command:

    cargo build --release --locked --bins \
      --manifest-path services/cloud-gateway/Cargo.toml \
      --target x86_64-unknown-linux-gnu --message-format=json

Use those resulting binaries for packaging. Explicit target means their default directory is `services/cloud-gateway/target/x86_64-unknown-linux-gnu/release`, or the same target/release suffix under CARGO_TARGET_DIR. Do not rebuild after capture and substitute different bytes.

Collector saves metadata, exact-target normal/build tree, all-target/all-feature normal/build/dev tree, complete compiler JSON (fresh=true included), raw audit and stderr, toolchain identity, source commit/tree, lock/manifest hashes, product version, four executable hashes and an evidence envelope. It requires complete library/build-script/root target identities, not merely a root count. Version/source/feature/unit disagreement is a blocker to diagnose.

`cargo-audit --no-fetch` legitimately emits null database Git telemetry. The helper preserves it and independently binds a clean official advisory-repository HEAD/tree plus a deterministic digest of every tracked on-disk file, checking no missing/untracked/symlink files and no change during scanning. A contradictory non-null raw commit fails. The initial smoke exposing this distinction is retained, not relabeled PASS. GitHub collection requires the collector-owned fresh official clone. Its command, successful exit, and UTC start/completion times are recorded separately from raw audit telemetry. The snapshot is bound immediately after acquisition and checked again before and after audit. Explicit local fixture evidence may use an existing snapshot and says so; it makes no upstream freshness claim.

GitHub product evidence requires repository `Eswink/coding-tools-mcp`, its workflow-reference prefix, and both Cargo and Rust `1.98.1`. Local fixture evidence explicitly records provider `local` and may use another stable version. Non-finite JSON numbers and non-integer/bool schema values fail closed. All generated outputs, including build targets and topology evidence, must be under RUNNER_TEMP before collection starts; no broad source-cleanliness ignore is permitted.

## Provenance and complete archive verification

1. Record the printed `envelope_sha256` in the trusted build-job output and parent artifact receipt, separate from mutable contents of the uploaded envelope. Self-hashes alone do not authenticate evidence.
2. Preserve all five raw streams, the envelope, summary, original four-lock audit reports and source identity in the exact-source evidence bundle. Do not upload generated credentials or application databases.
3. Existing cloud_release_bundle.py builds the fixed archive from these four files and records its SHA256. Keep its ELF/CLI/version/ldd checks and fixed-members manifest unchanged.
4. In each installed/extracted acceptance job, use the existing strict cloud_release_bundle unpack verification to validate the archive digest, fixed member set, regular files and source/run/version manifest.
5. Then verify those actual extracted four files against the original audited build:

    python scripts/exact_build_audit.py verify \
      --root "$GITHUB_WORKSPACE" --expected-sha "$GITHUB_SHA" \
      --version "$APPROVED_PRODUCT_VERSION" \
      --target x86_64-unknown-linux-gnu \
      --output "$DOWNLOADED_EVIDENCE_DIR" \
      --expected-envelope-sha256 "$TRUSTED_BUILD_JOB_ENVELOPE_SHA256" \
      --binary-dir "$VERIFIED_UNPACKED_DIR/bin"

This joins audit evidence to the actual archive contents. A changed or absent executable, stream or envelope fails. Keep the original archive verification receipt beside this result; the helper alone does not validate a tar container or authorize extraction.

6. Retain all existing service/browser/PG/WSS/enrollment/startup tests. Repeat on each actual target required by the release contract; Linux evidence is not Windows evidence. For native Windows capture, use x86_64-pc-windows-msvc and its actual four .exe files.

## Avoiding a dependency cycle

The engineering build/evidence job may run and retain a valid exact-build applicability result even while the parent raw-zero final release gate remains BLOCKED. The helper is a predecessor evidence producer; it must not require final release approval to produce evidence, nor set publish_approved itself. Only after actual product proof and negative/end-to-end tests are reviewed may the parent propose an explicit contract distinguishing raw findings from exact-build applicability. Until then no change to final_rc_evidence.audits, final package publishing, installer acceptance or full roadmap gates.

## Tests and evidence boundaries

Run `python scripts/exact_build_audit_tests.py`. Mutations cover missing dependency/build-script/root units, bad finish/exit, source/tree/lock/version/target differences, ambiguity/source/version changes, features, active RSA/other advisory, filters, counts/database/checksum errors, external digest/stream tampering and altered/missing extracted binary bytes. Fresh=true is accepted and counted.

Local real-Cargo smoke uses a tiny four-binary fixture with an inactive transitive optional rsa0.9.10 dependency retained by weak feature forwarding. It executes real cargo-audit over the unchanged generated lock and distinguishes its one raw advisory from two selected packages/five actual compiler events. This validates the collector pipeline, not the actual gateway release. Actual product artifacts, runner identities and exact source CI remain required.

## Limitations requiring fail-closed handling

Cargo tree is not guaranteed exactly equivalent to every compiler configuration. This helper deliberately blocks differences rather than filtering them away. Same-name/same-version multiple source identities are currently rejected as ambiguous. Stable package/compiler metadata and trusted CI provenance do not establish arbitrary build-script or native/system-library safety. Unexpected compiler output, targets, configuration or package graph require review. Existing security controls are not waived by an unused lockfile classification.

## Standalone engineering runner supplied for review
`.github/workflows/issue85-exact-build-audit.yml` is isolated-CI-prefix/manual and permits current component versions. It builds the actual four product release binaries once with the existing1.98.1toolchain, retains raw findings, archives only those four files, then downloads and checks archive SHA/member safety plus all four binary hashes in a second job. Its receipts explicitly set release_approved=false and publish_approved=false. Prefer reusing this collector in the topology worker's existing build rather than running both builds. No hosted run has been performed by this worker.
