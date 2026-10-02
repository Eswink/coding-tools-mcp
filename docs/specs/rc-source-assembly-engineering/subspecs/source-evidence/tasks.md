# 子任务：Immutable source and exact engineering producer evidence

- [ ] 1.1 Recreate properly gated merges and implement exact immutable-anchor/linear-source guard with positive correction and negative history/scope tests
  - 证据块: AGENTS.md pre-edit/pre-commit rules; docs/specs/rc-source-assembly-engineering/subspecs/source-evidence/spec.md
  - 涉及文件: scripts/rc_source_assembly.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py
  - _需求: FR-1_
- [ ] 1.2 Adapt only exact second engineering producer tuple and explicit root plumbing after HIGH warning and independent maintainer review; retain original16 tests
  - 证据块: scripts/engineering_dependency_capture.py:26-35,103-196,199-237; the required fresh upstream impact report before editing
  - 涉及文件: scripts/engineering_dependency_capture.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py
  - _需求: FR-2_
