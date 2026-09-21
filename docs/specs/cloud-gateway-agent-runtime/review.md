# Round 1 review — isolated protocol laboratory

Scope: only the additive M1 laboratory, documentation and CI. This is an assistant
code review using real staged diff and deterministic tool guidance, not an
independent production security certification.

## Findings and dispositions

| Finding | Severity | Disposition |
|---|---|---|
| Explicit JSON null tool arguments were silently defaulted to an empty object | Medium, contract | Fixed in dispatchProtocol; new regression failed before fix and passed afterward |
| Production interceptor has a broad execution impact | High, architecture | Not modified; preserved desktop baseline; extraction requires a separate reviewed PR |
| Synthetic bearer/session fixtures are not real OAuth or verified human identity | Production blocker | Explicit non-production flags, loopback-only API, no OS executor, README and open issue gates |
| Unknown-outcome fixture cannot prove distributed execution guarantees | Production blocker | No replay/idempotency certification claimed; durable journal/channel work remains open |
| Read-only workflow changes still alter a validation contract | Medium, scope | Bounded runner matrix, contents:read, no credentials/production deployment, source allowlist and candidate hashes |
| Tool-generated local env/runtime files appeared as untracked review inputs | Low, scope | Excluded from Git staging; only allowlisted additions will be published |

## Architecture evidence

`architecture mode=validate` initially reported missing structured alternative,
root-cause and boundary evidence. Supplied the actual staged design in structured
form; validation then returned `passed=true`.

First drift check rejected a misleading `cleanup` field: excluding temporary
local tooling had been classified as removing old implementation paths. M1 is
strictly additive. Corrected this metadata and reran; drift returned
`passed=true`. A premature PASS heartbeat was explicitly corrected to failed
before the successful rerun. Original failure evidence is retained, not rewritten.

These passes apply to **M1 boundaries only**. The 36-issue roadmap remains active.

## Checks

- Complete staged diff inspected; review tool reports no truncation.
- `git diff --cached --check` passes.
- GitNexus staged impact is medium, one affected flow in the new lab; direct
  dispatchProtocol impact is LOW. FTS-unavailable warning is recorded.
- HTTP/CLI contracts: 32 passed, zero skipped.
- Existing UI contracts: 8 passed. Existing Python fault-proxy contracts: 8 passed.
- Native Windows/Ubuntu CI remains a separate candidate gate; no local result is
  labeled as that CI or as a desktop installation test.
- Manual checks: catalog does not reveal local identifiers; no raw token/session
  logging; no arbitrary upstream, execution or remote approval path; unsupported
  methods/versions remain protocol errors; write-capable annotations are not
  falsified to avoid host approval.


## Round 2 manual review

- Reviewed exact new SQL, OAuth client/resource/code/refresh binding, family locking and replay revocation, identity-key continuity, device proof consumption order and signed-grant scope/epoch checks.
- Fixed the demonstrated malformed-Origin normalization issue. Raw Origin serialization is checked rather than relying on a URL parser's repair behavior.
- Keep operator methods out of HTTP. Metadata/token router is a partial library, not a complete authorization service; deployable status is explicitly blocked.
- Device enrollment and a verified signed claim do not replace local approval/lease/recovery/execution authorization. WSS and authoritative local-grant integration remain separate gates.
- Template validation does not certify real TLS/WAF/site integration. Compose remains behind a disabled profile with mandatory external image/secret inputs; no binary/image is fabricated.
- Recorded CentOS Stream 8 EOL and unknown Docker Engine version. Do not modify OS/WAF/firewall as a hidden prerequisite.
- Real database/process restart and race tests passed; backup rollback resistance, capacity/GC/abuse limits, and public consent controller have NOT been implemented.
- Review and graph helpers are deterministic guidance, not an independent production security assessment. Remote CI and publication are not available in this turn.


### Round 2 pre-commit graph/architecture gate investigation

The incremental graph returned missing symbol IDs and implausible cross-language callers for the new renderer/identity methods; aggregate impact was CRITICAL (256 flows). A forced full rebuild restored concrete symbol IDs. Scoped `issue_after_owner_consent`, `refresh`, and renderer `main` queries were rerun against the rebuilt graph; exact results are retained in the evidence bundle. The rebuilt aggregate still reports CRITICAL (280 new/changed symbols, 16 flows); this warning is retained, not rewritten to LOW. It includes new identity/deployment contracts and warrants review before integration. Existing src/src-tauri, root package/lock, AGENTS and CLAUDE Git objects match the base exactly; the new crate has its own workspace and no desktop dependency. No production merge/deployment is performed.

The architecture helper initially rejected incomplete normalized metadata and then interpreted test-cluster teardown as legacy-code cleanup. Inputs were corrected to the actual additive-only scope (no legacy retirement). Bounded validate/drift then passed; unknown VPS/Host evidence remains explicit. These are structured planning checks, not independent security certification. Dependency advisory audit is still a production gate; pinned dependency seed does not by itself prove absence of vulnerabilities.
