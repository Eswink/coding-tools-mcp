# Exact-build dependency evidence and archive contract

**No release approval.** The legacy `final_rc_evidence.audits` raw-zero checker remains unchanged. The final workflow's explicit `dependencies` mode additionally requires the authenticated cloud archive/build join and independently verified non-cloud reports. This contract change requires independent review and new-source hosted proof before adoption. Version, integration, installer/native and security gates remain mandatory; no artifact family can grant release approval.

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
3. Existing cloud_release_bundle.py builds the fixed archive from these four files and records its SHA256. Its ELF/CLI/version/ldd checks and fixed-members manifest remain unchanged.
4. The `release_dependency_contract.py` adapter requires both digests from trusted producer-job outputs. Its final mode calls strict cloud archive unpack verification with the independent archive digest, then verifies the actual four extracted files. Archive receipts, summaries and colocated checksum files are never trust anchors.
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

The engineering build/evidence job may run and retain a valid exact-build applicability result while final gates remain BLOCKED. It never depends on release approval or sets publish_approved. The same-commit final DAG is source/version/integration -> reusable cloud build/process/image -> dependency contracts -> native package builds -> installed acceptance -> final bundle. The cloud producer has no dependency on final contracts or bundle approval. The `issue85` engineering workflow uses a separately labelled four-member archive; its adapter mode cannot satisfy the final release-cloud contract.

After the same source approval, final packaging also calls the local reusable `issue40-container-topology.yml`. It builds separate exact-source engineering binaries and runs all 14 topology cases, including cleanup. Successful topology is a mandatory final bundle dependency: failed, skipped or cancelled topology blocks bundling. Its evidence never substitutes for the authenticated release archive, and the older 2602478 topology run cannot satisfy this same-final-source prerequisite.

## Trusted producer and warning policy

`release_dependency_contract.py` leaves the existing `verify_records` algorithm unchanged. After full verification it requires an exact match for provider, repository, source SHA, workflow reference, job, run ID, run attempt and runner OS. Final consumers require the current run/attempt and reviewed caller workflow. A reusable workflow inherits caller context; no downloaded producer declaration chooses the expected producer. A mixed-attempt rerun fails closed and needs the producer/dependents rerun.

The two required CI outputs are the actual archive SHA256 and original envelope SHA256. Both are handed through `needs`; missing outputs fail. Each process/image consumer repeats the join before executing binary bytes. The final bundle repeats it and checks the trusted contracts identity digest plus its complete evidence-file inventory, preventing replacement of non-cloud audits or desktop source evidence after the contracts job.

All final archive routes pass through `cloud_release_bundle.unpack_trusted` before the legacy structural `unpack` helper. Static call-route and runtime wrong/missing-digest regressions enforce this boundary; the legacy helper remains available to structural fixture tests only without external authentication.

Every raw warning is retained and mapped to its lock identity. Unknown/malformed warning kinds and all unresolved unsound warnings block. The optional RSA finding is accepted only as absence from the verified actual and conservative graphs; no advisory ID is ignored or suppressed. Non-cloud locks still require zero raw vulnerability entries. The final report explicitly records raw_zero_claim=false and both approval fields false.

## Separate GLib source prerequisite

`release_dependency_capture.py` records real unfiltered audits for the three non-cloud locks against a fresh official RustSec clone. If the desktop lock selects local/path GLib, it requires the independently supplied `verify_glib_backport.py`, downloads the pinned official original crate, and executes its full source/configuration/locked-metadata and paired-audit verification. The original RUSTSEC-2024-0429 registry-identity report remains in `desktop-glib/upstream-identity-raw-audit.json`. The product report is compared to the separately captured desktop raw report.

The final verifier rechecks source/configuration, the complete recorded metadata and paired reports against the current committed lock. These files are authenticated by the contracts job's externally passed identity digest. Missing source proof, altered package/source metadata, changed raw reports or any unresolved product unsound warning blocks. This is source-backport evidence only: it explicitly reports installed_desktop_bytes_verified=false. Existing native installed-payload checks remain mandatory and cloud RSA absence reasoning never applies to active Linux GLib.

## Tests and evidence boundaries

Run `python scripts/exact_build_audit_tests.py`. Mutations cover missing dependency/build-script/root units, bad finish/exit, source/tree/lock/version/target differences, ambiguity/source/version changes, features, active RSA/other advisory, filters, counts/database/checksum errors, external digest/stream tampering and altered/missing extracted binary bytes. Fresh=true is accepted and counted.

Local real-Cargo smoke uses a tiny four-binary fixture with an inactive transitive optional rsa0.9.10 dependency retained by weak feature forwarding. It executes real cargo-audit over the unchanged generated lock and distinguishes its one raw advisory from two selected packages/five actual compiler events. This validates the collector pipeline, not the actual gateway release. Actual product artifacts, runner identities and exact source CI remain required.

## Limitations requiring fail-closed handling

Cargo tree is not guaranteed exactly equivalent to every compiler configuration. This helper deliberately blocks differences rather than filtering them away. Same-name/same-version multiple source identities are currently rejected as ambiguous. Stable package/compiler metadata and trusted CI provenance do not establish arbitrary build-script or native/system-library safety. Unexpected compiler output, targets, configuration or package graph require review. Existing security controls are not waived by an unused lockfile classification.

## Standalone engineering runner supplied for review
`.github/workflows/issue85-exact-build-audit.yml` is isolated-CI-prefix/manual and permits current component versions. It builds four engineering binaries once with the pinned1.98.1toolchain, retains raw findings, then verifies the downloaded archive, exact producer, complete build evidence and warning policy in a second job. Its receipts explicitly set release_approved=false and publish_approved=false. The final workflow removes the unused historical agent_fixture artifact plumbing: current WSS acceptance uses shipped enrollment commands.

The prior unchanged verifier's actual product/second-runner proof at2602478 is prerequisite evidence, not proof of this integration. Run `python scripts/release_dependency_contract_tests.py`, the original exact-build/archive/final helper suites, affected package/image/native/version contracts and actionlint. New-source hosted adapter proof remains required. Full final acceptance remains impossible while the owner-selected version and Windows/snapshot security gates are unresolved; no final version or frozen release manifest is created here.
