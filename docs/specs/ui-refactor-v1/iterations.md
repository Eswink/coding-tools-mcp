# UI refactor v1 — iteration ledger

Status: IMPLEMENTING / NOT RELEASE ACCEPTANCE. User approved the plan with “确认 Plan，开始 UI 重构 ！循环迭代任务启动！ @GitHub”; latest continuation is “继续任务！”. No merge or release before visual review.

## Round 01 — restore, baseline, boundaries

Planning branch ce8c5a9/tree7382e84 and main v0.4.0 5b1265f/tree552088e4 were independently reconstructed from the source archive. No existing UI implementation branch was present. Created one implementation branch feat/ui-refactor-v1, keeping PR#11, main and published packages untouched. CI-only baseline b8b3f90/tree3fe28280 run34772132859 passed all seven jobs, including existing Windows/Ubuntu source, browser and publication contracts. Local unmodified frontend baseline:139 passed,0 failed/skipped. This is not candidate acceptance.

Read AGENTS/CLAUDE, project-context, design-system, graph summary and pinned Probe/GitNexus skills. Native discovery found no matching integration. Project resume launcher returned127; pinned4.0.1 self-install timed out; offline resume/start_ui/query/impact returnedENOTCACHED. No managed-plan/graph PASS. Continue only with explicit manual call-chain/diff review and recorded runtime tests; do not report inaccessible tools as executed successfully.

## Rounds 02–04 — presentation foundation and workspace extraction

Split global CSS into semantic tokens/base/shell/components/feedback, retaining compatibility selectors. Implemented a navy desktop shell, transparent page heading, real-state badges, card primitives, readable equivalent dark palette and system/local fonts. Kept route URLs and native window behavior. Extracted the display-only MCP/Actions service subtree into WorkspaceServiceView, with actual endpoints, authenticated configuration, tunnel, task, log and health children. Orchestration and backend API modules remain in place.

Manual impact: global CSS/shell reaches all routes (HIGH visual regression surface); service prop boundary reaches endpoint display, forms and tasks (HIGH correctness risk). Local approval, OAuth/refresh/draining Rust, API wrappers and grant decision functions are deliberately unchanged. Production metadata and mock reference timestamps are never hard-coded as live status.

First candidate frontend run:135 passed/4 failed. The four existing AST tests looked for components that moved into the new view. Replaced those location assumptions with parent-to-view AND view-to-child checks, preserving actual-origin, temporary-tunnel and all four Actions URL assertions. A fifth new boundary check proves task-budget callbacks capture the rendered service and original workspace.

## Rounds 05–11 — consistent pages, same capabilities

Restyled the authorization panel without editing approval/revoke/recovery functions. Re-housed all four settings pages using the shared surface/header system. Credentials remain masked and per-field load failures/rekey invalidations remain intact. FRP global profile management is explicitly separate from per-workspace live tunnel state; software lists only installed/path/managed facts supported by the API. Do not invent software versions, health/latency, account grants, language/autostart or directory controls from the reference drawings.

Added a shared light/dark/system theme store using the existing localStorage theme key, clean listener lifetime and synchronization with the sidebar toggle. No network fonts or new dependencies. Added conservative draft-change confirmation before switching service/subpanel; cancellation keeps the actual form mounted. A confirmation that returns after disposal, workspace/view change or a new mutation cannot switch the panel. Successful internally managed saves may still trigger a conservative confirmation; this is a known UX limitation, not permission to discard drafts.

## Round 12 — keyboard and local verification

Tabs now use manual keyboard activation with Arrow/Home/End focus navigation, roving tabindex and named associated panels. Arrow movement alone does not discard a form. First local type check found two callback type mismatches; narrowed them to the existing Promise contracts. Removed noninteractive region tabindex after the accessibility warning.

Current local result:153 frontend tests passed,0 failed/skipped (139 existing with moved-boundary checks +14 new); Svelte/type checks0 errors/0 warnings; actual production build succeeded. Theme API and guard tests run production functions with synthetic environment objects; not DOM/native evidence.

Added actual-built-route browser fixture: five pages, four viewport sizes, light/dark, explicit synthetic-data banner, no fake production routes, screenshots plus interactions. Existing approval component/native regression scripts are not replaced. Root Chromium sandbox launch was rejected; using the existing non-root account kept the sandbox enabled but localhost navigation was denied with ERR_BLOCKED_BY_ADMINISTRATOR. Retain both failures; no policy/sandbox workaround. Run actual-page capture on GitHub Actions and review screenshots before claiming visual parity.

## Pending gates

Candidate source CI, actual-page browser/contrast/overflow review, long/error/empty states, visual tuning, installed Windows/Ubuntu UI parity and user visual approval. No Rust was run in this container. Version remains0.4.0 because this is source-only development; a future installer requires a distinct version and the existing publication protocol. Rounds above describe implementation progress, not completed acceptance. No release is authorized by a green browser mock alone.
