# Windows foundation native cases (PR #147)

Workflow: `.github/workflows/windows-foundation-native.yml`. Every result here is labelled
**frozen SUT + new prepare step**. None of it was produced by the frozen harness, and none of it is RC qualification.

- SUT: union1967 overlay tree `4d42a210` plus repin overlay 01 (backup `ca629f8e`), giving tree `c8cc0cf3`. Provenance
  is guarded by the overlay tree hash.
- The frozen `scripts/prepare_windows_vm_session.ps1` is left unchanged because pretag profiles pin it. The workflow-owned
  copy is `scripts/windows_foundation_native_prepare.ps1`.
- Go test inventory: `scripts/windows_foundation_native_go_inventory.json` is the single source of truth (currently
  10 test files, 41 pure plus 18 native tests). The check compares those hardcoded expected lists by exact name with the
  actual `go list` / `go test -list` output. The JSON records why it differs from 19bb2920.
- HCS cases run serially in one binary. native_02 is gated on native_01 having fully drained.
- The broker decodes `bundle.json` strictly, so SUT identity is written to `sut-identity.json`. The broker has no
  `sutTree` variable, so a `-X main.sutTree` link flag would be silently ignored and is not used.
- The 9 `TestNativeActualGuest*` workspace cases run on the Windows runner **host**, not inside the HCS VM, and are
  labelled host-run. Only native_01/native_02 execute inside the VM. In-VM execution of these cases is deferred until
  the HCS workspace-run transport (`docs/specs/windows-creation-owned-hcs-workspace-run`, FR-3) exists; the frozen
  broker in `c8cc0cf3` only launches the fixed `guest.exe --guest` fixture, and changing it would require a new SUT tree.
- Launch timing: `finished in 10.31s` for the 6 `native_launch_*` cases in run 37858303598 (c60f9667) is a single-run host anomaly, cause unconfirmed; `launch.rs`/`launch_tests.rs`/`prepare_windows_vm_launch.ps1` and fixture source are identical to `c8cc0cf3`, and other runs of the old workflow took 0.11-0.15s (here 0.81s / 0.50s).
- Launch evidence tiers (receipts of run 38045100810): `native_launch_matching_image_retires` = **launch verified** (identity match, continue, exit 0, stdout `A`/stderr `E`). The other 5 (`wrong_image_rejects`, `same_bytes_new_id_rejects`, `junction_redirect_rejects`, `cancel_before_continue`, `wait_fault_preserves_raw_evidence`) = **reject/cancel path verified**: process created, stopped before first Continue via `TerminateProcess(.., 125)` (`launch.rs:230`), asserted by `rejection_retired()` (`launch.rs:87`) plus per-case identity/cancel/fault checks (`launch_tests.rs:421-499`); exit 125 is the terminate code, not a fixture result.
