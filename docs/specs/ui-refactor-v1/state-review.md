# UI state coverage — Round 14a

Status: TEST SOURCE READY; CI acceptance pending.


While the corrected exact-source run is executing, add eight actual-page scenarios at960x640: empty workspace/FRP/software, long workspace identity/path, partial secret read failure, empty/failed task list, dark native-HTML-dialog focus containment, and live system-theme changes. These reuse the real production routes/components and synthetic IPC, with labelled state screenshots. No business source changes in this round. The shared task panel still needs visual review along with the state images; no native acceptance or all-state completeness is inferred.

Local strict Svelte/type check remains0 errors/0 warnings and all160 frontend tests pass after these additions. The actual-page scenarios must still execute on the candidate in Actions; Python compilation is not runtime browser proof.

## Round 14b — failed shared-secret rendering

Run34775462769 at e5e6af6 passed the40 normal screenshots and eight interactions, then the extended state test failed: after one synthetic key-read rejection, the shared-key section remained on its loading DOM and no failed-field input appeared. Artifact10323735746 SHA256253e687c5d299e2faf82716fb9f9566dc1a723d6246b0e60d321fb52a8c51db7 was downloaded and checked. Empty inventories and long-identity screenshots were retained.

Source inspection: failed keys are deliberately absent from the secrets map, but both credential sections passed that undefined value through bind:value into SecretInput's $bindable("") fallback. The installed Svelte runtime throws props_invalid_value for exactly that contract (also documented at https://svelte.dev/docs/svelte/bind). It is wrong to solve this by making a failed key an editable empty secret. Render an explicitly disabled, unbound failed-field placeholder instead; normal rows keep their original binding and mutations. All load/rekey/reconcile/save functions and error guards remain byte-identical. Scope is the two template branches only; the high-risk secret mutation contract is not relaxed.

Three AST regressions against the production page: old template2 failed/1 passed; corrected template3 passed. The first AST harness used the legacy expression field; corrected it to the installed modern AST test field before collecting the assertion-specific red/green result. Add per-state JSON and console-error recording so an asynchronous render exception cannot hide behind the test runner's pageerror-only channel. This does not alter or waive the existing input/disabled assertions.

All163 local frontend tests pass, strict type/Svelte0errors/0warnings and production build pass. Compared the complete script block before/after: unchanged. The minimal change is template-only. New CI is required.

Visual consistency review also found the old task panel uses the legacy tx-btn selector, which had no shared primitive style, and destructive hover could still inherit neutral ghost text. Map that existing selector into the existing secondary-button rule and preserve danger color on hover; no task event handler or operation changes. Actual state tests now check rendered budget-button geometry and unchanged destructive hover color.

## Round 14c — bound extreme workspace titles

The preserved960x640 long-workspace screenshot from e5e6af6 showed a five-line title consuming most of the first viewport. Limit the visual heading to two lines, give the breadcrumb an ellipsis, and preserve the complete name in DOM/accessibility text, tooltip and editable name field. No name is changed or truncated in the data model. The state gate checks both rendered line height and the full title attribute. Normal names and all route/IPC contracts are unchanged; review impact is the shared PageHeader presentation only.


Round14c also corrects a test-only selector mismatch exposed by run34776016396 at7fb6e7b. Its40 normal screenshots,8 interactions and first5 state scenarios passed, including the previously failing partial-secret rendering case. The sixth case timed out looking for “保存预算”, but the actual production button is labelled “保存上限” and uses the legacy tx-btn class. Verified against both the built DOM and tracked Svelte source before correcting the exact accessible-name selector; do not rename the product or broaden the selector to evade the check. Keep the40px geometry, list-only IPC, task failure and no-auto-start assertions. Artifact10323756510 SHA25653a09803c77dbd3a4eb8d59303d2e55d437da4739cf3ede7199c89b995410ec7 was verified.

Final14c local check initially reported one vendor-only line-clamp warning; added the standard property alongside the WebKit fallback.163 frontend assertions still pass. Recheck exact staged files before publishing; no zero-warning claim for that intermediate run.

## Round 15 — modal keyboard containment and error readability

Run34776481784 at62928e3 passed40 screenshots,8 main interactions and6 state cases, then correctly failed the minimum-window dialog keyboard containment assertion. The existing native HTML dialog kept the background inert, but successive Tabs left the dialog's active element; this is a focus-navigation defect, NOT evidence of an authorization bypass. Artifact10323791959 SHA25660323d5a8ceef2061a7b91f82e680ef8afd47469499b00a1cafc96a6825668eb verified. The partial-key fix and task failure checks passed on the real built UI.

Follow W3C's dialog pattern (https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): add one keyboard-only helper at the dialog element. Re-evaluate visible enabled controls on each Tab, wrap only at a boundary, skip disabled fieldsets/hidden/inert elements and preserve Escape and OS shortcuts. No synthetic click or approval; all pre-existing display/decide/refresh/grant logic remains unchanged. HIGH sensitivity because this touches the local approval host; manual upstream review covers only import/event/helper, after the offline GitNexus impact attempt failed ENOTCACHED. New eight helper contracts and24 real browser Tab/Shift+Tab steps plus Escape focus restoration are required.

The dark failed-key screenshot also showed a legacy hard-coded error red. Use the semantic danger text/border token in that page, add light/dark danger-on-card/canvas contrast pairs, and scroll state screenshots to the actual failed input/task error so evidence shows the tested state rather than just its header. This is presentation only. Never count token checks as full WCAG certification or browser mocks as native desktop proof.
