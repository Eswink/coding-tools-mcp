# Release continuation — v0.4.0

User instruction: `很好，继续任务，直到任务全部完成收尾，完成后双端发布！`, continued with `继续任务！`.

Recovered feature SHA: 65ce45bda6a23a91bbcd2dd7d3594661c4ada9b0; tree: 4fc351563985ad565d658330ae98c218cf2e7d7c; PR #12 remains draft. Source archive10316745621 SHA2563033d318f8560d3cb00baf2eed044c3409fbb14ad5d07a78090af7fa789d4f54 was downloaded and its complete Git tree independently recomputed. Do not reapply the old ecf5ca9 increment; it is already in this tree.

## Round 19 — Native modal navigation race

Run34752009576 built new0.4.0 NSIS, DEB and AppImage packages. Windows installed acceptance succeeded; all four Ubuntu installed cases failed in stage5 while trying to click the global inbox behind an already-open modal. Ubuntu24.04 DEB evidence10316676516 and native-failure.png show the correct candidate modal,89-second countdown, unchecked fingerprint confirmation and requested permissions. The trace reports HTTP400 `element not interactable` in candidate -> legacy.click -> native WebDriver. This is not an OAuth discovery or approval bypass defect.

Change only the native test navigation: an exact candidate fingerprint readback detects already-open dialogs. A single inbox click remains the fallback. The helper accepts only WebDriver400 `element not interactable` or `element click intercepted` when a fresh readback proves that the exact expected modal is now open. It never repeats a click, clicks via JavaScript, calls approval IPC, ignores another error, or accepts the wrong dialog. The background/expiry scenario uses the same helper. All native fingerprint, reduced-scope,90-second expiry, replay and standard-user gates remain unchanged.

Manual impact is limited to exclusive_native_acceptance.candidate and the background inbox stage, called by the Windows standard-user and Ubuntu installed launchers. Eight deterministic navigation contracts run alongside the existing nine evidence contracts on both package builders. Local17/17 passed; these are contract tests, NOT installed acceptance. AGENTS/Probe4.0.1/project-context/GitNexus skills were read; the exact pinned resume CLI and offline impact attempt returned ENOTCACHED. Manual call-chain/diff review is explicitly not graph validation.

## Remaining execution

1. Commit exact reviewed test changes to the feature branch and fast-forward the dedicated native build branch without force.
2. Rebuild and execute twelve installed stages on Windows and Ubuntu22.04/24.04 DEB/AppImage. Read exact-revision artifacts; never inherit PASS from the old SHA.
3. Execute complete source regression, release helper contracts, provenance/version/evidence checks. Review public discovery separately from synthetic local credentials.
4. Prepare a new dual-platform pre-release only after all applicable automated gates. Keep real ChatGPT account provenance and OS toast display explicitly unverified unless actual evidence is obtained; an installed modal/HTTP fixture cannot prove either. Never call all real-user acceptance complete based on CI alone.
5. Preserve v0.3.2, its tag/assets, PR#11 and live Nginx. No macOS. Verify the published package bytes by anonymous download and record final SHA256/source SHA/run IDs.

Status: round19 candidate awaiting changed-source/native CI. No new publication in this continuation yet.

## Round 20A — Await the actual revoke result

Run34757864939 at85587e87 passes the previously failing foreground modal stage and stages1–8 on Ubuntu, including100 foreign requests, refresh continuity and live-child draining. It then fails when immediately requesting candidate C after a native revoke click. WebDriver click return does not await the asynchronous Svelte IPC mutation. The captured UI subsequently shows B already revoked, consistent with this timing boundary. Windows is not used to waive the faster WebKit path.

The native helper now waits for an authoritative read-only snapshot with no pending/active records after its ONE revoke click. It does not invoke revoke via IPC, retry a mutation, change server timing, or infer that draining tasks ended. The existing separate task-cancellation/free-state assertion remains. Two deterministic contracts cover delayed completion and draining semantics; local19/19 pass. Candidate failures now expose only their machine code in assertions, never tokens. Changed-source installed tests are required again.
