# 子任务：Focused CI execution and honest artifact verification

- [ ] 2.1 Add only the exact-branch focused workflow and preserve real command/fixture/count/browser acceptance behavior
  - 证据块: .github/workflows/portable-ci-target-validation.yml; rc-product-version-validation.yml; linux-authenticated-lifecycle.yml; issue84-frontend-acceptance.yml; issue85-dependency-capture.yml
  - 涉及文件: .github/workflows/rc-source-assembly.yml; scripts/rc_source_assembly_frontend.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py
  - _需求: FR-3_
- [ ] 2.2 Verify exact-run downloaded artifacts and capture digest/source/byte/count integrity with raw findings and failure preservation
  - 证据块: scripts/engineering_dependency_capture.py:103-237; tests/delivery/test_linux_lifecycle_wiring.py; docs/specs/rc-source-assembly-engineering/subspecs/focused-validation/spec.md
  - 涉及文件: scripts/rc_source_assembly.py; scripts/rc_source_assembly_frontend.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py
  - _需求: FR-4_
- [ ] 2.3 Report source-preflight scope separately from unchanged final-release blockers and verify protected paths remain unchanged
  - 证据块: scripts/release_preflight.py:8-37; scripts/rc_version_gate.py:74-100; docs/releases/next-rc-ledger.md
  - 涉及文件: scripts/rc_source_assembly.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py
  - _需求: FR-5_
