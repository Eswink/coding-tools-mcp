# Round 5 Acceptance Matrix

Date: 2026-09-20  
Status: IN PROGRESS  
Real ChatGPT connector setup: DEFERRED BY USER

## Evidence classes

- **SOURCE** — Rust/HTTP/unit/integration regression.
- **PACKAGED** — actual Tauri installer/package produced and installed in CI.
- **HOST** — actual ChatGPT connector/UI observation.
- **DEFERRED** — intentionally not executed yet; must not be relabeled PASS.

## Matrix

| Scenario | Evidence path | Current status |
|---|---|---|
| Workspace Online -> Offline -> Online | Round 3 execution-gate + HTTP regressions | SOURCE PASS |
| Active owner during Offline | Round 3 HTTP regression | SOURCE PASS |
| Unrelated/foreign chat during Offline | Round 4 privacy matrix | SOURCE PASS |
| 100 repeated non-owner authorization calls | Round 4 privacy matrix | SOURCE PASS |
| OAuth refresh while Offline | Round 3 refresh HTTP regression | SOURCE PASS |
| Tunnel membership/public origin unchanged by pause/resume | Round 3 supervisor regression | SOURCE PASS |
| Stale pause against replacement listener | Round 3 supervisor regression | SOURCE PASS |
| Async task observation/cancel isolation | Round 4 chat-domain/task regression | SOURCE PASS |
| Recovery-required non-disclosure | Round 4 privacy regression | SOURCE PASS |
| Windows full regression | Round 5 packaged workflow | IN PROGRESS |
| Windows NSIS build/install/uninstall | Round 5 packaged workflow | IN PROGRESS |
| Ubuntu full regression | run `35509843023` | SOURCE PASS |
| Ubuntu DEB build/install/purge | run `35509843023` | PACKAGED PASS |
| UI close/reopen with real ChatGPT connector | actual host connector | DEFERRED |
| App process restart observed by ChatGPT | actual host connector | DEFERRED |
| Network flap/tunnel restart observed by ChatGPT | actual host connector | DEFERRED |
| Real reconnect-card behavior | actual host connector | DEFERRED |
| Shared-account connector visibility | actual host/account UI | DEFERRED |

## Final result vocabulary

### ENGINEERING_CANDIDATE_PASS

Requires all SOURCE and PACKAGED rows to pass.

It means:

- the Level A implementation has passed source/security regressions;
- actual Windows and Ubuntu desktop packages build and install correctly;
- package removal is clean;
- no release was published.

It does **not** mean the ChatGPT reconnect UI has been proven fixed.

### HOST_VALIDATED

Requires the deferred HOST rows.

Only this state can support a claim about:

- whether ChatGPT still presents reconnect UI;
- how an installed connector appears to another user sharing the ChatGPT account;
- host behavior across process/network interruption.

## Release policy

No Round 5 CI artifact is a release candidate by publication semantics:

- no version bump;
- no Git tag;
- no GitHub Release;
- no production signing secret;
- bounded CI retention only.

The project plan branch may accept ENGINEERING_CANDIDATE_PASS while the overall issue remains open for HOST_VALIDATED.


## Ubuntu packaged checkpoint

Run `35509843023`, source candidate `b1c190f29135dda6a80cb9af03883e8c6dcdd5a8`:

- frontend offline-safe UI contract: 3/3 PASS;
- Rust primary suite: 380 passed, 0 failed;
- integration suites: PASS;
- strict library compile: PASS;
- Debian bundle: `Coding Tools MCP_0.6.0-rc.4_amd64.deb`;
- package id: `coding-tools-mcp`;
- package version: `0.6.0-rc.4`;
- package SHA-256: `4c6ff10665fcd73756cbdb5e4cb8ff36e9a390dcc9138a01eaddcad9aba9ad7a`;
- installed executable: `/usr/bin/coding-tools-mcp-desktop`;
- install verification: PASS;
- purge/removal verification: PASS;
- CI artifact digest: `sha256:b638409e5a890380f0c75d636493048a0a576db7f7269607b9d90e9fc8429c0a`.

Windows packaged acceptance remains open.
