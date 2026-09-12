# Iteration 7: frontend configuration application authority

Base: 5215182ebea383543a6e9b89d233df376f5a9f39 / tree 61f99f2d99e7b223c4b766399c4cf8ab945ab93d, downloaded exact source artifact and independently reconstructed content tree. Iterations 5 and 6 already exist remotely; they were preserved, not reimplemented or attributed to this iteration.

## Findings and repair

The route re-started MCP/Actions after the backend had already applied authentication, and swallowed those secondary errors. Other policy/path saves still requested manual restarts. Updates speculatively assigned the submitted draft instead of reading canonical state even though persistence can succeed and restart fail. A directory-picker or delete confirmation could resume after navigation using the new workspace identifier. Port validation accepted non-finite/fractional numbers; trimming directory separators damaged filesystem roots.

Non-tunnel saves now await one backend operation and refresh the original workspace on either result. The original apply rejection survives a failed readback; successful persistence with failed readback does not report success. Identity-bound callbacks refuse obsolete actions, and directory/delete dialogs capture the selected workspace. Invalidation counters fence configuration/runtime changes without storing secret or configuration bytes. Health and quick-copy panels invalidate even when credentials or runtime change within the same workspace. Port/directory form errors are visible, with integer validation and exact picker paths.

## Scope and risk

HIGH: authentication/lifecycle UI wiring. Graph indexing and exact-symbol impact were run; Svelte-local handlers/template edges are missing from the graph, so the route-component callback connections were inspected manually. That gap is not represented as a successful graph proof. New local tooling and generated rule/index files are excluded from the patch.

Tunnel credential-only saves still have a separate legacy restart path and require the next iteration to coordinate backend token application before removing it. Credential-form async reads/regenerations, native confidential-client fixtures, installed matrices and release remain mandatory. No dependency/version changes and no skipped CI gates.

## Tests and self-review

Eight new behavioral/AST tests first failed (seven red cases, one compiler pass); implemented helper and wiring now pass. Together with existing UI-state tests: 16/16 pass. Full frontend local attempt: 83 pass and one test-file setup failure because the offline review archive does not contain the `cookie` dependency. That failure is NOT a full-suite pass; complete npm-ci/check/build/test still required on both CI platforms. Local compiler checks use Svelte's official same-version bundled CommonJS compiler via an external review-only loader, not a product module replacement.

Initial self-review 89/100: rejected for unhandled form failures and stale FRP assignment before identity check. Corrected both, added protected original-context callbacks and full readback. Revised candidate 94/100, pending real Windows/Linux CI and native installation gates. No score permits intermediate merge/release.
