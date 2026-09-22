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

## Round 3 — owner browser authorization review

- Recovered exact prior local commit 4b6f197 from the published bundle on verified ba9c379 baseline; remote PR #36 remained at ba9c379. No earlier unpushed work was discarded.
- Existing issue #41 already described the required boundary; reused it instead of opening a duplicate.
- Graph LOW labels are incomplete Rust callgraphs, not security sign-off. Auth and HTTP source/test callsites were reviewed directly. FTS is unavailable offline. A concurrent index read temporarily failed; retried serially after index completion. Focused router impact was obtained after its initial additive route composition, a procedural ordering gap retained here rather than claimed as pre-edit evidence.
- Failed route baseline: authorize GET was absent (404). Added the controller and its tests; no test fixture authentication is exposed in the production library.
- Security bug reproduced: waiting for a client row lock can exhaust a previously valid browser flow. The first new regression failed. Recheck database time after awaited client validation and inside the code-issuance transaction; the regression then passed. No expired flow may create a code.
- The original trusted-API HTTP test expected 404 for POST authorize. GET authorize is now intentionally registered, so POST correctly returns 405. Updated only that assertion and added no-Location/zero-code assertions; direct admin issuance/invitation paths still require 404. The failing intermediate full-suite result is retained.
- Initial new test compilation used an incorrect access-validation method name; corrected to the actual authenticate_access API. No test was skipped to hide this error.
- One SQL transaction covers owner/flow/client revalidation, code issuance and flow consumption. Password work runs outside database locks; owned semaphore permits survive HTTP cancellation. Password rotation is explicit CAS and revokes existing owner OAuth families.
- Source side effects are confined to the new standalone cloud library, its tests/CI and specifications. No desktop/source/installer or live network configuration changes.
- Remaining risks: same-origin site trust, public rate limiting, MFA/owner operations, backup anti-rollback, durable grant projection and Agent fencing. No independent security audit, real browser or ChatGPT outcome claimed.


## Round 6 — #46 local review

52 new channel tests plus existing full suite (194 total) pass. Read `round6-validation.md` for the exact limits, boot/session/lease review and retained failures. Opt-in WS router is not publicly mounted, and a connected session is not an execution permit. GitNexus Rust caller coverage is incomplete; path-qualified results and manual callsites were both checked. No prior desktop symbols or authorization method bodies modified. Physical/Host tests deferred at user request; publication/CI are separate from local PASS.
