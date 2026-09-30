# Fixed fde46cc engineering artifact transfer

## Authorized scope

Read only existing GitHub Actions artifact 11114636713 from run 36748964715 in
Eswink/coding-tools-mcp. Its original source is fde46cc6299be88ffcf6b3fa3236d222dbdda7b1,
tree 183ea60ebc6f08010c885d436f8b4c02fc7800d7. The opaque ZIP is exactly 97384787 bytes,
SHA256 e7d8c352ba7f384c8c5dce25b74620d43211508d4ce7dcf960dae4b53c7d720d.

Dot's direct transfer limit is 32 MiB; a provided URL returned HTTP 403. This separate
authorized Actions path does not bypass that response: it uses GitHub's normal authenticated
artifact-read API with a job-scoped token and permissions limited to contents:read and actions:read.
No configurable artifact, repository, run, source or hash input exists.

## Contract

1. Fail closed unless GitHub metadata matches the exact artifact ID, name, digest,
   byte count, original run, branch, repository IDs and source SHA, and is not expired
2. Download the original ZIP through the official GitHub CLI; never print credentials,
   raw CLI failures, headers or temporary download URLs
3. Verify original ZIP SHA256 and size before splitting. Treat it as an opaque byte stream:
   no extraction, installer execution, rebuilding or package changes
4. Split into exactly five ordered parts, each at most 23 MiB, with offset, size and SHA256
5. Rehash the concatenated parts before publishing the receipt and individual chunk artifacts
6. Locally reassemble only the exact inventory, rejecting symlinks, malformed offsets,
   missing/extra/reordered/tampered chunks and an existing output. Verify the original
   pinned ZIP SHA256 and size before declaring the bytes materialized

The receipt separates original source/run identity from the transfer workflow's identity.
All outputs retain NOT_FINAL_NOT_PUBLISHABLE and release_approved:false.
Windows needs no split: its existing 6.98 MB artifact is already independently downloaded.

## Validation and stopping condition

Run `python scripts/rematerialize_linux_fde46cc_tests.py`, compileall, diff-check and
workflow lint before the parent publishes the isolated engineering branch. Unit tests
must cover metadata/source/digest tampering, bounded five-part roundtrip, changed source,
bad chunk inventory/path/hash and existing-output refusal. No local test executes a package.

After the authorized hosted transfer succeeds, download each new small artifact through
the normal connector, verify its GitHub digest, retain receipt and five original.zip.part-NN
files in one clean directory, and run the helper's `join` command. Only then inspect the
unchanged original ZIP and bind its package hashes to the already verified installed receipts.
Stop after exact reassembly and package verification; do not rebuild or rerun package tests.

This proof does not clear full Windows regressions, desktop audits, final RC/version gates,
VPS/ChatGPT acceptance, publication or production changes.

References: [GitHub artifact REST API](https://docs.github.com/en/rest/actions/artifacts),
[GitHub CLI API command](https://cli.github.com/manual/gh_api).
