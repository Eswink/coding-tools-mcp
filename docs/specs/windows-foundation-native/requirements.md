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
