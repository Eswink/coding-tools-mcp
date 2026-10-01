# Engineering verification guide for source version0.6.0-rc.4

**NOT A PUBLISHED RELEASE. NOT PUBLICATION APPROVAL.**

This guide matches the existing source metadata so engineering-only package/input checks can run before a final version decision. It does not select the next RC or supersede stablev0.6.0 / desktop-onlyv0.6.1-rc.1. A final candidate must receive a new version-matched guide after its source and version are frozen.

## Authoritative status

Use [the current release ledger](next-rc-ledger.md#current-engineering-evidence--2026-10-01), [current source reconciliation](source-acceptance-audit.md#current-source-and-executed-evidence), and the exact candidate commit's GitHub Actions. The audit's original 49bbbef body is explicitly historical; its bootstrap/protocol gaps are superseded by the current reconciliation. Do not reuse another commit's green run. Exact 1281915 non-Windows integration and provenance engineering evidence is verified, but overall integration still fails on Windows. Final release gates remain unresolved: Windows isolation/restore and warnings, the held snapshot root-binding repair, final source/version audits and topology, final installed packages, the RC publication consumer and post-publication checks.

## Required automated checks

- Frontend lock install, Svelte check/build and full regression driver
- Locked Rust all-target compile, full tests, format, shared Clippy and production warnings-as-errors
- Actual PostgreSQL/OAuth, three-version Rust MCP wire tests, authenticated WSS/native application execution, offline/foreign/revoke/generation/duplicate/restart/no-replay negatives
- Device-local key/proof and trusted operator enrollment process bootstrap
- Windows and Ubuntu22.04/24.04 worktree, mandatory sandbox, process cancellation, Hooks, native credential restart and snapshot metadata/recovery
- Raw dependency audit reports plus any separately reviewed exact-build reachability evidence; no ignored vulnerabilities or hidden raw findings
- Exact-source NSIS/DEB/AppImage builds, native install/runtime smoke, standalone cloud binary and container topology checks

## Artifact acceptance

Engineering artifacts must be labeled non-final and never attached to a Release as final packages. Final artifacts must all have the selected product version, exact source SHA/tree, expected architecture, verified metadata, byte size, SHA256 and successful download/integrity/installation evidence. Test fixtures and credentials must not enter customer archives/images. Required final workflows remain fail-closed while any coding/security/integration gate fails.

## External boundaries

Physical workstation, real ChatGPT, real VPS/Nginx/BaoTa/WAF/DNS/TLS and host-specific FUSE/Wayland/notification behavior remain unconfirmed. These observations cannot substitute for missing code or failed automated tests. No production deployment or stable release is authorized.

## Upgrade / rollback

No production upgrade is recommended from this engineering source. For an eventual published RC, drain work first, retain encrypted credentials/journals and monotonic revocation state, and back up under operator control. Do not restore stale authorization databases or automatically replay unknown mutations. Use only a verified previous installer with compatible state; never overwrite a tag or erase failed-release history.
