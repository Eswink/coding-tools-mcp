# Strict legacy source gates and manual source freeze

## Stable and RC provenance
`source_provenance_gate.py` reads the committed package version and selects an existing validator using a complete string match. Stable versions retain the original stable verifier; numbered RC versions use the existing RC verifier. Other suffixes, leading zeros, mixed fields, dirty tracked source and wrong SHA remain failures. Both validators are unchanged. This classification grants no tag or publication authority.

## Cumulative manifest contract
The cumulative lab path requires a committed `docs/releases/reviewed-source-manifest.json`. This increment deliberately does not supply that file. A missing file is a release blocker, not a skipped test.

After the final source and version review, the parent must freeze this exact schema manually:
- `schema`: integer1
- `base_commit`: `758c60a6e74e624e144f9c19c5f19d04d17f7a13`
- `version`: the actual six-field desktop product version
- `review_reference`: human-readable locator of the external review/decision
- `entries`: path-sorted exact changed-file list

Each entry contains exactly `path`, `status`, `before`, `after`. Status is A/M/D/T from Git with rename detection disabled; renames are delete plus add. Each non-null side contains the actual Git mode,40-character `blob_sha`, and64-character SHA256 of the Git blob bytes. Added files have null before; deleted files have null after. Include every helper, workflow, test, dependency lockfile, document, generated tracked source and deletion that differs from the pinned baseline. New symlink entries fail closed.

No CI command generates, accepts or broadens the list from the PR diff. The checker computes the actual diff only to compare it with the already frozen reviewed list. Missing, extra, changed, duplicated, reordered, stale or wrongly hashed entries fail.

## Self-reference and approval trust
Only the literal manifest file itself is excluded from its own digest list. No other file in its directory is excluded. The result records the actual manifest Git blob and content digest together with source SHA/tree, so reviewers can identify precisely which review material was checked.

A manifest committed in a PR is not proof of external approval. A contributor who can change both the verifier and manifest can propose matching malicious changes. External review and protected-branch policy remain the trust anchor. `review_reference` is an audit locator, not a cryptographic attestation. CI reports repository consistency and always retains `publish_approved=false`.

No version is chosen by this change. Freeze the manifest only after version fields and the complete candidate are reviewed. Adding the single manifest file afterward does not require a circular self-hash; any other later source edit requires a new reviewed freeze.

## Historical laboratory path
The historical `feat/cloud-gateway-agent-runtime` increment retains its exact original additive scope guard. Main PR cumulative candidates use the new frozen manifest check. Protocol syntax/HTTP tests, offline-safe tests and fault-proxy tests run independently before scope validation, so a scope failure no longer prevents their execution. Their assertions are unchanged. Both scope paths remain fail closed.

## Current verification limits
Temporary-repository positive/negative tests and actionlint can validate the validator logic here. No final frozen manifest exists yet, no source approval is inferred, and no release/merge is performed. Full candidate native CI and the outstanding Windows runtime security decision remain independent blockers.
