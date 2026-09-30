# Open issue source reconciliation

2026-09-30 11:07 UTC. Read-only audit at canonical HEAD `49bbbef690afcc41b71f2a6e6c51dbda9233e67f`, with later cumulative fixes excluded from final-PASS claims. GitHub issue/PR state was queried at 11:04 UTC. This audit does not close issues or certify a release.

Current open issues: #32,33,34,37,38,39,40,41,42,43,44,45,46,70,73,81,84. Current open PRs: #30,36,77,79,80,82,83.

## Urgent executable gaps

1. **#39 production bootstrap missing.** `services/cloud-gateway/src/device.rs` implements invitation issuance/redemption, but every caller of `create_device_invitation` / `redeem_device_invitation` outside that module is a test or example. `Ed25519KeyPair::generate_pkcs8` appears only in tests/examples. Native `src-tauri/src/cloud_connection/` imports preexisting protected PKCS8. Gateway CLI offers check-config/migrate/provision-owner/register-client/rotate-owner/serve; control CLI only serve/select-device; Agent CLI only check-config/init-state/run. No shipped local-admin issuance/redemption or device-local key-generation/proof flow. Synthetic `examples/{agent_fixture,native_desktop_fixture}.rs` bootstrap is not an operator procedure. This blocks #39 AC1/2 and from-empty-state full-package bootstrap, not deferred physical-host testing.
2. **#34 production negative-matrix coverage missing.** Comprehensive `tests/cloud-gateway/protocol.test.mjs` imports the JavaScript prototype. Shipped Rust `mcp/protocol.rs` has four unit cases; `mcp_postgres.rs::legacy_initialize_list_and_tool_call_keep_same_auth_boundary` executes initialize/list only for 2025-06-18, despite its name. Need production modern + both legacy versions, actual successful/failed tool calls, mirrored metadata/header negatives, unknown versions/methods, missing context and correct envelopes. Existing code appears to implement these; no bypass is demonstrated by the coverage gap.

## Evidence matrix

Paths below prefixed `gateway/` mean `services/cloud-gateway/`; `spec/` means `docs/specs/cloud-gateway-agent-runtime/`. Present tests/source are not automatically a current executed PASS.

| Issue / acceptance | Actual source and tests | Remaining executable work / classification |
|---|---|---|
| #33 AC1 architecture/threat model | `spec/{design,threat-model,requirements,review}.md`: separate OAuth/device/conversation/local authority, private workspaces, bounded routing and no replay | Implemented documentation; synchronize stale status text after exact release reconciliation |
| #33 AC2 dependencies/rollback/real-host gates | `spec/issues.md`, design rollback section; `docs/releases/next-rc-ledger.md` current full-scope dependencies | Current ledger more complete than historical register; final source evidence still needed |
| #33 AC3 correct36 tasks | `spec/issues.md` explicitly ISSUE-010..045=36 | Present |
| #33 AC4 confirmed versus future | Iteration/round receipts explicitly distinguish library/prototype/integration and host boundaries | Preserve receipts; do not promote old green badges to current PASS |
| #33 AC5 no production changes | Audit read-only; historical scoped receipts distinguish source publication from main/release/deploy | No production changes authorized by audit |
| #34 AC1–4 modern/legacy wire | `gateway/src/mcp/protocol.rs::{complete,tool_result,validate_version,protocol_result}` and HTTP boundary | Source implemented; production test matrix gap above |
| #34 AC5 offline tool error | `gateway/tests/mcp_postgres.rs::authorized_agent_offline_is_tool_error_not_oauth_or_foreign_metadata` | Present; exact-source full regression pending |
| #34 AC6 OAuth failure | `mcp_postgres::oauth_errors_are_transport_auth_not_workspace_offline` | Present,401/WWW-Authenticate retained |
| #34 AC7 foreign/missing privacy | `mcp_postgres::{host_session_never_comes_from_tool_arguments,full_catalog_foreign_calls_never_disclose_offline_workspace_or_enter_ledger}` | Add explicit missing-context version matrix; no demonstrated source bypass |
| #34 AC8 catalog independent | `mcp_postgres::discovery_and_catalog_are_stable_without_agent_presence`; protocol catalog49tools | Present |
| #34 AC9 scope honesty | `spec/protocol.md`, lab tests and source receipts separate prototype from external compliance | Real ChatGPT deferred; production negative coverage remains executable |
| #37 AC1 fixedidentity/PKCE | `gateway/src/{config,oauth}.rs`; `identity_postgres::{exact_resource_and_redirect_binding,confidential_client_requires_secret_in_addition_to_pkce}` | Present |
| #37 AC2 code single-use/expiry | `identity_postgres::{incorrect_verifier_does_not_consume_code,code_replay_revokes_issued_access_and_refresh,expired_code_and_access_are_rejected}` | Present |
| #37 AC3 keyedtoken hashes/refresh | `identity_postgres::{database_contains_keyed_digests_not_token_bytes,old_refresh_reuse_revokes_whole_family,concurrent_refresh_has_one_rotation_and_reuse_revocation,foreign_client_cannot_consume_or_revoke_refresh}` | Present |
| #37 AC4 continuity/identity lock | `store.rs`; `identity_postgres::{refresh_persists_across_core_reopen_without_any_agent,store_refuses_changed_pepper_or_identity,owner_revocation_survives_reopen}` | Present |
| #37 AC5 properOAuthfailure | `http_postgres::invalid_refresh_is_oauth_error_not_workspace_offline`; mcp401 test | Present |
| #37 AC6 noimplicitgrant | `browser_store::begin_and_login_do_not_grant_oauth_or_device_authority`; projection enrollment-only test | Present |
| #37 AC7 portable/PG/restart | `pure_contracts.rs`, identity PG suite, `run_restart_test.py` | Historical precise runners present; cumulative exact-source evidence required |
| #37 AC8 browserconsent | `browser/{flows,credentials,envelope,http,html}.rs`, browser tests below | Present |
| #37 AC9 executable/browser/ingress | `src/main.rs`, `service/{cli,input,lifecycle,runtime}.rs`, process/browser suites | Old NOT_DEPLOYABLE text stale; #40 ingress prep independently audited |
| #37 AC10 compatibility/release | Full release gates | Real ChatGPT deferred; executable release review pending |
| #38 AC1 separateidentitytypes | `gateway/src/{oauth,projection,grant}.rs`; `services/cloud-agent/src/{identity,execution,projection}.rs` | Implemented; final cumulative integration tests pending#81 |
| #38 AC2 ticket notauthority | `services/cloud-agent/src/agent/host/{authority,runner,journal}.rs`; hosttests deny foreignscope/mutatedargs/staleepoch/expiredprojection, suppress output onrevocation | Present |
| #38 AC3 signature/claimsbinding | `gateway/src/projection/claims.rs`; `projection_contracts.rs` | Present |
| #38 AC4 monotonicrestore/drain | `projection/store.rs`; `projection_postgres` restore/reboot/drain/ownertransfer tests | Present |
| #38 AC5 nopendingoffline/foreignprivacy | `mcp_postgres::{offline_foreign_authorization_request_is_suppressed_without_state_or_channel_noise,offline_owner_authorization_remains_active_without_new_pending_state}` | Present |
| #38 AC6 reviewednativeextraction | `src-tauri/src/cloud_application.rs`, cloud_connection/, tools/cloud_host/live/; native `application/wss_tests::application_import_listener_native_approval_pause_revoke_and_stop_are_end_to_end` | Historical untouched-desktop clause was pre-extraction gate, not permanent bar to reviewed#81; current native acceptance pending |
| #39 AC1 localadminCLI | No shipped invitation command | Missing; implement bounded trustedCLI |
| #39 AC2 device-localkey/proof | Device crypto library and test fixtures only; nativeconfig importsPKCS8 | Missing shippedkeygen/proof; private key must stay device-local |
| #39 AC3 domainproof preservingtoken | `device.rs::enrollment_message/redeem_device_invitation`; issuer+connector deterministically bind resource, token+key; signaturebeforeconsume | Present; add explicit wrongdomain/key/token tests |
| #39 AC4 concurrentredemption | `device_postgres::concurrent_enrollment_creates_one_device`; rowlock thenDBclock | Existing same-key case; add distinct-key race and lockwaitexpiry |
| #39 AC5/6 challenge/classes/generation/revoke | `channel/{protocol,store}.rs`; channelcontracts/postgres/websocket cover nonce,replay,expiry,epoch/revoke/stalegeneration,OAuthhandshake rejection | Present |
| #39 AC7 noimplicitpermission | `projection_postgres::enrollment_and_oauth_identity_alone_never_make_local_authority` | Present |
| #39 AC8 core/DB/restart | device/channel PG tests plus canary process fixtures | Add shippedcommand from-empty-key/config→selection→WSS process bootstrap, restart/replay/redaction; not a physical-host deferral |
| #41 AC1–8 checked engineering | `browser_store.rs`: explicitowner, noimplicitgrant, CSRF/cookie/fixation/replay/expiry/deny, clientmutation, credentialrotation, concurrentconsent/login, lockwaitexpiry, boundtransactions/passwordwork, encryptedtamper. `browser_http.rs`: strictforms,cookies,Origin,redirect,escaping | Source exists; retain exact-source CI |
| #41 final browser/interoperabilityreview | `run_service_acceptance.py` + `run_service_browser_ci.py`: Chromium actualsecurecookies,Origin,CSRFrotation,deny/expiry,PKCE,restart,credentialrotation | Current process/browser job reportedPASS36704408237; full release review remains; realChatGPT deferred |
| #42 AC1 plan/review | `issue-013c-runnable-service.md`, round4/6 receipts | Present historical review |
| #42 AC2 safeprovisioning | `service/lifecycle.rs`: createonlyowner/client and expectedepochrotation | Present |
| #42 AC3 protectedsecrets/noadmin | `service/{input,cli}.rs`, `service_contracts.rs`: boundedprotectedfile/stdin, noambientfallback/argsecrets/echo/publicadmin | Windowssecretfiles failclosed; supportednonterminalstdin preserved |
| #42 AC4 actualprocesswithoutAgent | `run_service_http.py`, `run_service_acceptance.py` | Present; latestOAuth process/browserPASS reported |
| #42 AC5 browsersecurity | browserStore/HTTP+Chromium above | Present |
| #42 AC6 platform/PG/proxy scope | `service_contracts.rs`, nativeCI and deploymenttests | Windowsportable versus UbuntuPG/browser explicitly distinguish; final cumulativeCI pending |
| #42 AC7 preflight | `deploy/cloud-gateway/`, deploymenttests | Separate #40 audit/implementation; no production changes |
| #42 AC8 sourceCI/rollback | Historical roundreceipts and nextRCledger | Exactfullcandidate artifacts/rollback/publication not complete |
| #43 AC1 reviewedadditivemigration | `issue-014a-grant-projection.md`, migrations/0003_grant_projection.sql | Present |
| #43 AC2 pureproof/bounds | `projection_contracts.rs`:16case signature/domain/state/bounds suite | Present |
| #43 AC3 PGconcurrency/reopen/restore | `projection_postgres.rs`:34cases including conflicting/identicalraces, restart, restore, postlockexpiry/revoke | Present |
| #43 AC4 owner/drain/epoch/revoke/cloudonly | Same suite: directownertransfer, expansionrequiringdrain, exactack, staleepoch, enrollmentonly | Present |
| #43 AC5 existingregressions | Current fullCI not allgreen | Still executable cumulative gate |
| #43 AC6 publication/parentreceipt | Historicaltestedpublication exists | Current exact integratedreceipt and sourcehashes pending |
| #44 AC1–7 transportumbrella | channel/{protocol,store,transport}, agent/{client,config,signer,journal}; channelcontracts/PG/WS,run_agent_process.py,host_agent_wss,managed_agent_wss,execution_postgres | Near-duplicate#46+#47 plus admission#49 and livebridge#81. Do not duplicateimplementation/close blindly |
| #44 TLS/restart/bounds details | ProcessWSS rejectswrongname/untrusted/expiredcert/redirect; newboot/reconnect/revisionjournal; channeloldclose/lateframes; executionlate replies/no replay; boundedjitter/backoff/rate/messages/connections | Present source/tests; fullcurrentcrossplatformevidence pending |
| #45 AC1/2 impact/redfirst | `issue-013d-browser-referrer-policy.md`, round6receipt preserves originalbrowserfailure and review | Present historicalreceipt |
| #45 AC3 pagepolicy/Origin | `browser/html.rs::page` strict-origin; secure() + httpboundary APIs/errors/redirects no-referrer. Three `referrer_contracts.rs` cases inclmissing/null/foreignOrigin | Present |
| #45 AC4 oldregressions | Current cumulative run notfullgreen | Still requiresfinalsuite |
| #45 AC5 realChromiumwithoutheaderrewrite | `run_service_acceptance.py` actualPOSTOrigin,origin-onlyReferer,callbacknone,login/deny/CSRF/rotation/restart | LatestOAuthbrowserjobPASS reported; notphysicalworkstation/ChatGPT proof |
| #46 checked8foundationACs | channel source/tests and retained round6failurefirst/source receipts | Present |
| #46 priorunchecked actualclient/WSS/mount | `service/control_cli.rs`, runtime.rs, agent/client.rs, `mcp_runtime.rs`; `run_agent_process.py`, channel_shutdown.rs | Implemented since stalebody; syntheticbootstrap still doesnotfulfill#39 |
| #46 admission/reconciliation/release | `execution_postgres` restart/unknown/tombstones/late reply; cloud-agentlivehost and native#81 | Finalcumulative native/security/package review pending |

## Remaining boundaries

- Current run36704408237 has reported OAuth process/browser and Ubuntu22 real transport PASS, but not final fullCI/release PASS. All new source changes require rerun at exact cumulative source/tree; source/test existence is not a passing run.
- #40 is separately audited; #70/#73/#81/#84 ongoing implementation preserves full scope. Windows isolation/security decision, Hooks, snapshot metadata, packages and version decision remain broader ledger gates.
- Only physical workstation/VPS/real ChatGPT observations are deferred. Enrollment bootstrap and production wire coverage are executable engineering gaps.
- PR77/79/80 overlap already-integrated sandboxhistory; PR82/83 are recovered gateway/nativeconfiguration inputs. PR30 first-contact governance has a colliding ISSUE-010 label but is not #33architecture. Compare exact scope rather than blindly merge.
- GitNexus read-only query initially lackedregisteredrepo; this source audit claims no graph/security certification. No source edits were made for the audit.

## Subsequent confirmed protocol defect

The shipped legacy notification route currently sends HTTP202 with a JSON object. Both pinned Streamable HTTP revisions require an accepted notification response with no body. A red-first production-route regression and minimal header-preserving correction are required, not an assertion that preserves the defective behavior. References: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports and https://modelcontextprotocol.io/specification/2025-06-18/basic/transports . The prototype already uses an empty response; prototype tests did not catch this shipped-code divergence.
