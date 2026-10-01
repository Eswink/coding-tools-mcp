# Engineering verification guide for 0.7.0-rc.1

**ENGINEERING ONLY. NOT RELEASED. NOT FINAL. NOT PUBLICATION APPROVAL.**

The user selected the new minor series 0.7.0-rc.N. This source uses 0.7.0-rc.1 as non-final engineering metadata; it does not reserve or create a tag. Fresh GitHub reads on 2026-10-01 found no matching 0.7.0 tags or Releases, including drafts. Recheck immediately before an authorized tag action after all required gates pass. Existing stable v0.6.0 and desktop-only v0.6.1-rc.1 remain intact.

## Product version authority

The six desktop fields in package.json, package-lock.json, desktop Cargo manifest/self-lock and Tauri config agree with the gateway product package/self-lock at 0.7.0-rc.1. Frontend displays, desktop APIs, all four cloud binary version outputs and cloud MCP serverInfo derive these existing metadata sources. The independent cloud-agent and local-agent libraries retain 0.1.0; protocol and configuration schema versions are not product versions.

The two preliminary installer workflows expect the same engineering version. Actual installer bytes, installed PE metadata, the complete application version and native receipts must still be verified on their final build source. Debian package-manager metadata uses 0.7.0~rc1 so the future stable 0.7.0 sorts above this RC.

## Evidence scope

The dedicated engineering workflow verifies immutable source, the field-only transition from e61aaf2da99baccdb99db4922b39f7d8d5997096, unchanged dependencies, existing release-contract negatives, the real frontend and locked Cargo metadata on Ubuntu 22.04/24.04 and Windows 2025. It builds and probes the four gateway binaries; that is distinct from metadata parsing. Its result is only valid for the exact commit whose logs and evidence identify it. This guide asserts no run has passed.

release_preflight success is **release-inputs-only**. A committed clean-source check, a metadata pass, a binary version probe or an older green run cannot establish final integration, installed-package or release acceptance. Local Node 24 results are separate from hosted Node 22 results; absent local Cargo checks are never reported as executed.

## Remaining full-release gates

Use [the release ledger](next-rc-ledger.md), [full RC gates](final-rc-gates.md) and the exact source's CI for status. Windows mandatory execution isolation, Windows snapshot metadata/recovery and the held Issue86 opened-root authority work remain unresolved. This increment does not implement or retry them. Final source integration, full native/runtime matrices, complete dependency audits, topology, installed NSIS/DEB/AppImage receipts, cloud artifact verification and publication-consumer/publisher requirements remain independent gates.

No production VPS, physical workstation or real ChatGPT-account acceptance is established. No credentials, keys, fixture secrets or private configuration may be included in artifacts. Runtime permission, isolation and no-replay boundaries are unchanged.

## Final review and freeze

This guide is a prefreeze engineering input. Before final acceptance, reconcile it with the complete selected source and genuine final evidence. The final guide itself must be included in the reviewed-source manifest. Any later edit to this guide or another covered file invalidates that freeze and requires a newly reviewed manifest; there is no post-freeze documentation exception. This increment does not create the manifest or satisfy its external-review requirement.

## Upgrade and rollback

No production upgrade is recommended from this engineering source. Any eventual authorized upgrade must drain work and retain encrypted configuration, native credentials, journals and monotonic revocation state. Rollback requires verified compatible binaries and state; never restore stale grants, replay uncertain mutations, overwrite prior tags/assets or erase failed evidence.
