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
