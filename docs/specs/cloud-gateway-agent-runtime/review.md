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
