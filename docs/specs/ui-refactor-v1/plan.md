# Coding Tools MCP UI Refactor v1 — Execution Plan

Status: **APPROVED / IMPLEMENTING — acceptance pending**
Planning baseline: **v0.4.0 / main `5b1265f6905e2953e32000797a62cfd2f16baa48`**
Target platforms: **Windows x64 + Ubuntu 22.04/24.04 amd64**
User approved implementation after this plan was saved. Progress and remaining gates are tracked in [iterations.md](iterations.md); visual approval remains required before merge/release.

## 1. Goal

Refactor the current Svelte/Tauri interface into a coherent desktop control console inspired by the five user-drawn reference screens while preserving the proven v0.4.0 runtime, OAuth, exclusive-chat, refresh-token, task, tunnel and secret-management behavior.

The refactor is primarily a **presentation architecture + information architecture + component-system** project. Product/security semantics must not be weakened merely to match a mockup.

## 2. Persistent reference assets

The exact uploaded PNG files are saved in the user's persistent Library folder:

`/Coding Tools MCP/UI References/v0.4.0-refactor/`

| Reference | Persistent filename | Intended page | Original SHA-256 |
|---|---|---|---|
| R1 | `workspace-overview.png` | Workspace dashboard / MCP service overview | `cc9a19928b520d75e881b207aba618ecbe1b0235d23e2d2cd743e1ca1ba035fa` |
| R2 | `general-settings.png` | General settings | `fad7244285cf01cdd0d6815ba69ddcb693d0889850e64beaed8a46b1b129ab25` |
| R3 | `credentials-and-keys.png` | Credentials / shared keys | `19bd726916c28ae332ea1c670528eac5b4de670e5f38b6283136c43847304cba` |
| R4 | `frp-configuration.png` | FRP configuration / public access | `c9644d628d465dbf5e514f885586eddfe7d447160afea9e42e3340b7f69a6100` |
| R5 | `software-management.png` | Software management / diagnostics | `0d5f65bbd268ddddaacf9ea1aa371674f07144e965b6addb58e06a64ce3f9af8` |

All five references are 1586×992 and should be treated as **design-intent references, not assertions that every displayed mock control already has a backend implementation**.

## 3. What to learn from the references

### 3.1 Shared visual language

- Persistent dark navy sidebar with a calm, high-contrast main canvas.
- White/light surface cards on a very light cool-gray/blue background.
- Blue is the single primary interaction color; green is reserved for healthy/running/authorized states.
- Rounded cards, restrained shadows, thin cool borders, generous whitespace.
- Strong page hierarchy: breadcrumb → page/workspace title → status → primary controls → grouped detail cards.
- Dense operational data is organized into rows/tables; configuration is organized into cards and labeled fields.
- Icons are functional, consistent and line-based; Lucide remains suitable.
- Important destructive actions remain visually isolated in red outlines rather than sharing primary action space.

### 3.2 Workspace overview (R1)

Desired hierarchy:

1. Workspace breadcrumb and identity header.
2. Editable workspace metadata row.
3. “ChatGPT new-session startup prompt” quick-copy card.
4. High-level ChatGPT authorization summary.
5. MCP / Actions segmented service switcher.
6. Selected service overview/configuration card with start/stop, local/public endpoint, OAuth endpoint, health status and logs entry.
7. Secondary operational panels (tasks/logs/health/policy) progressively disclosed rather than stacked above the fold.

### 3.3 General settings (R2)

Use a responsive two-column settings-card grid, with each card owning one concern. The mockup contains appearance, language, startup, network, updates, directories, notifications and local-security concepts.

**Important:** v0.4.0 does not currently implement every mocked control. The first UI refactor must only render controls backed by real state/actions. Unsupported mock concepts are product candidates, not fake settings.

### 3.4 Credentials and keys (R3)

Desired hierarchy:

- Clear credential section header and documentation link.
- Secret rows with masked value, reveal, copy and regenerate actions.
- Separate OAuth credentials from bearer/token-signing secrets; never imply interchangeable semantics.
- Security warning immediately adjacent to powerful long-lived credentials.
- Workspace/global policy selection shown only when that policy actually exists in the domain model.

### 3.5 FRP configuration (R4)

Desired desktop layout:

- Wide left configuration column.
- Narrow right status/preview column.
- Server/profile selector and connection settings.
- Domain/public-access configuration.
- Local MCP/Actions mapping.
- Collapsible advanced options.
- Right-side runtime status, public URLs and generated `frpc.toml` preview.
- Bottom action strip for test/save/start operations.

### 3.6 Software management (R5)

Desired hierarchy:

- Overall runtime health and available-update summary cards.
- Structured component table with current/latest version, installation path, status, source and actions.
- Release/package information and environment diagnostics below.

Again, the table must contain **actual components exposed by the v0.4.0 software/runtime APIs**. Mock rows such as browser/checker/runtime components must not be invented unless implementation is explicitly added later.

## 4. Current v0.4.0 UI baseline

The current UI already has useful pieces, but presentation responsibilities are too concentrated:

- `src/routes/workspace/[id]/+page.svelte` is ~709 lines and coordinates workspace metadata, authorization, MCP/Actions state, tunnel, authentication, policy, tasks, logs and health.
- `src/app.css` is ~845 lines and mixes design tokens, shell layout, primitives and legacy aliases.
- The route structure already maps well to the reference set:
  - `/workspace/[id]`
  - `/settings/general`
  - `/settings/keys`
  - `/settings/frp`
  - `/settings/software`
- Existing components such as `ChatAuthorizationHost`, `RemoteSessionSettings`, `AuthConfigForm`, `TunnelConfigForm`, `ServicePanel`, task/log/health panels and secret inputs should be preserved functionally and progressively re-housed in the new component hierarchy.

## 5. Chosen architecture

### 5.1 Preserve route contracts in the first refactor

Do **not** start by changing public route URLs. Keeping current routes minimizes risk to navigation state, workspace selection, tests and user muscle memory.

If nested workspace routes become useful later, introduce them only after the visual/component refactor is stable, with backward-compatible redirects.

### 5.2 Route components become orchestration layers

Target shape:

```text
src/routes/.../+page.svelte
  -> loads/coordinates real state
  -> renders page sections
  -> does not contain large reusable visual implementations

src/lib/components/layout/
src/lib/components/primitives/
src/lib/components/workspace/
src/lib/components/settings/
```

All **new filenames are English**.

### 5.3 Proposed component families

Layout:
- `DesktopShell.svelte`
- `AppSidebar.svelte`
- `SidebarWorkspaceItem.svelte`
- `PageBreadcrumb.svelte`
- `PageHeader.svelte`
- `ContentGrid.svelte`

Primitives:
- `SurfaceCard.svelte`
- `SectionHeader.svelte`
- `StatusBadge.svelte`
- `StatusRow.svelte`
- `PrimaryButton.svelte`
- `SecondaryButton.svelte`
- `DangerButton.svelte`
- `FormField.svelte`
- `CopyField.svelte`
- `SecretField.svelte`
- `InlineNotice.svelte`
- `SegmentedControl.svelte`
- `DataTable.svelte`
- `EmptyState.svelte`

Workspace:
- `WorkspaceIdentityHeader.svelte`
- `WorkspaceMetaCard.svelte`
- `SessionPromptCard.svelte`
- `AuthorizationSummaryCard.svelte`
- `ServiceSwitcher.svelte`
- `ServiceOverviewCard.svelte`
- `ServiceEndpointGrid.svelte`
- `ServiceHealthStrip.svelte`
- `ServiceOperationsPanel.svelte`

Settings:
- `SettingsCard.svelte`
- `SettingsActionRow.svelte`
- `CredentialsSection.svelte`
- `FrpStatusPanel.svelte`
- `FrpConfigPreview.svelte`
- `SoftwareStatusTable.svelte`
- `EnvironmentDiagnostics.svelte`

This is a target decomposition, not permission to create all components blindly. During implementation, merge trivial primitives when abstraction does not reduce duplication.

## 6. Design-system direction

### 6.1 Core palette

The exact final values should be tuned against the references in browser/native screenshots, but the semantic system should be stable:

- Canvas: cool very-light gray/blue.
- Card: opaque/near-opaque white in light mode.
- Sidebar: navy gradient or solid dark navy.
- Primary: clean medium blue.
- Success: green.
- Warning: amber.
- Destructive: red.
- Text: near-black navy, secondary slate, muted blue-gray.

Avoid introducing multiple decorative accent colors. Gradients, if retained, should be subtle and structural rather than “AI purple”.

### 6.2 Geometry

- Sidebar: ~250–260 px at normal desktop width.
- Page padding: 28–32 px on large desktop; reduce progressively at smaller window sizes.
- Card radius: 12–16 px.
- Input/button radius: 8–10 px.
- Standard card padding: 18–22 px.
- Inter-section gap: 16–24 px.
- Main control height: 40–44 px.

### 6.3 Typography

Prefer a local/system UI stack for predictable Chinese rendering and offline desktop packaging:

`Segoe UI Variable / Segoe UI / PingFang SC / Microsoft YaHei / Noto Sans CJK SC / sans-serif`

Code/endpoints/logs use a mono stack such as `JetBrains Mono / Cascadia Code / Consolas / monospace` when available.

Do not introduce a mandatory runtime dependency on remote web fonts.

### 6.4 Theme behavior

- Light theme follows the supplied references.
- Dark theme is a first-class equivalent, not a CSS inversion.
- “Follow system” can be exposed only if its persistence semantics are implemented cleanly; the existing two-state theme toggle must continue to work until then.
- All visual regression scenarios include both themes where applicable.

## 7. Functional invariants — must survive the UI rewrite

The following v0.4.0 behavior is release-blocking if broken:

- Workspace CRUD and current-workspace selection.
- MCP and Actions start/stop/restart state and endpoints.
- OAuth configuration, PKCE/refresh behavior and discovery metadata.
- Default single-owner conversation lease.
- Local fingerprint confirmation and reduced-scope approval.
- Silent denial of non-owner conversations.
- Refresh-token rotation/reuse handling.
- Long-running task admission/draining/recovery behavior.
- Task/log/health access.
- FRP profile management and tunnel lifecycle.
- Secret masking, reveal/copy/regenerate/save semantics; no secret leakage in DOM logs, toast or screenshots.
- Update/download/software actions currently implemented by the backend.
- Existing close-to-tray, global approval host and native notification behavior.

The refactor may change layout and presentation, not these contracts.

## 8. Feature-parity policy for mock-only controls

The supplied references contain controls that are not necessarily implemented in v0.4.0, including some combinations of:

- language selection,
- startup-on-boot and reopen-last-workspace,
- update channel selection,
- editable data/log directories,
- notification sound preferences,
- “remember local confirmation” behavior,
- richer software component/version inventory.

For UI Refactor v1:

1. **Never render a working-looking control with no backend contract.**
2. Reuse the reference composition with only real capabilities.
3. Record missing capabilities as optional follow-up product work.
4. If the user later asks for feature parity with the mockups, implement those as separately scoped backend+UI features with their own tests.

## 9. Page-by-page target

### 9.1 Workspace page

Keep `/workspace/[id]`.

Above the fold:
- breadcrumb;
- workspace title + runtime status + destructive delete action;
- workspace metadata edit row;
- session startup prompt card;
- authorization summary card;
- MCP / Actions segmented switcher;
- selected service overview card.

Below the fold:
- service configuration/policy;
- tasks;
- logs;
- health;
- advanced tunnel/auth details.

The active-service switch must not destroy unsaved drafts without warning.

### 9.2 General settings

Keep `/settings/general`.

Use a responsive two-column card grid. First implementation should arrange existing real capabilities such as:
- about/version/repository/update check;
- theme/appearance currently supported;
- UI-memory maintenance;
- network proxy;
- existing notification/security settings if backed by current code.

Mock-only features remain absent or explicitly marked outside this version; no fake toggles.

### 9.3 Credentials / shared keys

Keep `/settings/keys`.

Visually follow R3 while retaining actual key semantics:
- MCP OAuth client ID/client secret/token-signing secret;
- Actions equivalents;
- clear descriptions;
- reveal/copy/regenerate;
- partial-read failure state must continue to fail closed;
- unsaved drafts must survive unrelated key failures.

### 9.4 FRP configuration

Keep `/settings/frp` for the first refactor.

Use R4's split layout:
- main profile/config area;
- contextual workspace mapping when a workspace is selected;
- right-side tunnel state/public endpoint/config preview when real data exists.

Never display “公网可访问” unless a real health/state source supports it.

### 9.5 Software management

Keep `/settings/software`.

Convert current list into a structured table/card layout modeled on R5. Only show actual returned software entries. Add version/release/diagnostic sections only from existing APIs or after separately approved backend work.

## 10. State and interaction rules

Every interactive control must have:
- default;
- hover;
- focus-visible;
- active;
- disabled;
- loading;
- success;
- error states.

Additional rules:
- destructive actions require explicit confirmation where current behavior does;
- async save/start/stop operations prevent double submission;
- workspace changes fence late async responses;
- secret reveal state is never persisted unnecessarily;
- keyboard navigation must reach all actions;
- modal focus is trapped and restored;
- `prefers-reduced-motion` is honored;
- status cannot rely on color alone.

## 11. Responsive desktop targets

Primary visual reference: **1586×992** (matches supplied references).

Required implementation/test sizes:
- 1586×992 — high-fidelity comparison;
- 1280×800 — current default Tauri window;
- 960×640 — current minimum supported window;
- 1920×1080 — large desktop sanity check.

At minimum width:
- two-column cards may collapse to one;
- right-side FRP status pane may move below configuration;
- tables may use horizontal scrolling only where unavoidable;
- sidebar may become compact only if it remains discoverable and keyboard-accessible.

## 12. Testing and evidence strategy

### 12.1 Frontend contract tests

Maintain existing tests and add tests for:
- route preservation;
- service switcher state;
- unsaved-draft protection;
- approval modal/inbox behavior;
- secret masking and copy/reveal semantics;
- loading/error/disabled states;
- responsive navigation behavior.

### 12.2 Browser visual regression

Use the production Svelte components, not hand-built static replicas.

Capture deterministic screenshots for:
- five reference page families;
- light/dark mode;
- default and minimum window widths;
- running/stopped/error states where feasible;
- authorization pending/active/draining states with synthetic non-secret fixtures.

Reference comparison is structural/high-fidelity rather than blind pixel identity because OS font rendering differs.

### 12.3 Native gates

After browser checks:
- Windows installed NSIS UI/navigation/approval acceptance;
- Ubuntu 22.04/24.04 DEB/AppImage UI/navigation/approval acceptance;
- no sandbox disabling;
- no secret-bearing screenshots/logs;
- verify existing v0.4.0 functional acceptance remains green.

## 13. Iteration plan

The implementation should use **14 main rounds, up to 20 only for reproduced failures**.

| Round | Scope | Exit evidence |
|---:|---|---|
| 00 | Archive references + save plan | Reference manifest and plan committed; no product UI change |
| 01 | Baseline UI inventory and screenshot harness | Current routes/components/states captured at exact base SHA |
| 02 | Token/primitives foundation | No page redesign yet; old UI renders with new semantic tokens |
| 03 | Desktop shell/sidebar/breadcrumb | Navigation parity, focus/keyboard, selected workspace correctness |
| 04 | Workspace header/meta/prompt | Workspace CRUD/edit/session-copy parity |
| 05 | Authorization summary + global approval integration | Existing exclusive/local approval semantics unchanged |
| 06 | MCP/Actions service switcher + overview | Start/stop/endpoints/state parity |
| 07 | Service configuration/tasks/logs/health | Existing operational panels migrated without behavior loss |
| 08 | General settings | Existing capabilities mapped to reference card grid |
| 09 | Credentials/keys | Secret safety and partial-failure regressions green |
| 10 | FRP page | Profile/tunnel/public state/config preview parity |
| 11 | Software page | Actual software actions/version/status parity |
| 12 | Dark theme, minimum-size, accessibility polish | WCAG/focus/reduced-motion/responsive evidence |
| 13 | Legacy CSS/component cleanup | No duplicate competing primitives; route files substantially slimmer |
| 14 | Full browser + Windows/Ubuntu native acceptance | Exact SHA, screenshots, functional regressions, no deferred security gates |
| 15–20 | Only reproduced defects / acceptance gaps | One documented defect-hypothesis-fix-test loop per round |

No “rerun until green” behavior. A failure must be preserved and explained before the next candidate.

## 14. Acceptance criteria

UI Refactor v1 is complete only when all of the following hold:

1. The five page families visibly follow the supplied design language and hierarchy.
2. Existing v0.4.0 security/runtime behavior remains intact.
3. No fake settings or fake runtime status were introduced.
4. New code filenames are English.
5. Main route contracts remain compatible.
6. Workspace page no longer acts as one monolithic presentation component.
7. Global styling is token-driven; route-specific one-off styles are minimized.
8. Light/dark themes and 960×640 minimum layout are usable.
9. Keyboard/focus/modal behavior passes browser/native checks.
10. No secrets appear in screenshots, logs, test artifacts or toast bodies.
11. Existing frontend/Rust/native suites remain green for the final exact SHA.
12. User performs visual review before merge/release.

## 15. Rollback strategy

- Develop on a dedicated feature branch based on the then-current `main`.
- Keep state/domain/API contracts unchanged where possible so visual commits can be reverted independently.
- Migrate page-by-page; do not delete old component implementations before replacement tests pass.
- Do not mix independent PR #11 public-OAuth-routing work into the UI branch unless explicitly rebased and reviewed as a separate integration decision.
- If a native UI regression appears, roll back the affected presentation slice without reverting v0.4.0 security/runtime fixes.

## 16. Decision requested from user

Before implementation, confirm the following design decisions:

1. **Visual direction:** treat the five supplied screens as the primary target language, not strict pixel-for-pixel copies.
2. **Route strategy:** keep existing URLs during the first refactor.
3. **Feature parity:** do not fabricate mock-only settings; backend additions are separate follow-up work.
4. **Theme:** light theme matches references; dark theme receives an equivalent native design.
5. **Implementation order:** shell → workspace → settings pages → cleanup → native acceptance.

After approval, create/continue the implementation branch from this planning branch and begin Round 01. No product code should change before that approval.

## 17. Tooling note

The repository requires `start_ui`/mcp-probe-kit and GitNexus for managed UI/impact workflows. In this planning environment the pinned `mcp-probe-kit@4.0.1` launcher was absent and the required pinned self-install attempt timed out. Therefore this document uses an explicitly declared manual source/layout review. This is sufficient for a plan-only documentation change, but before implementation the managed tool path should be retried and any actual symbol edit must follow the repository's required impact-analysis discipline.
