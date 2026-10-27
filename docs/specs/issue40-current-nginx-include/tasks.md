# Tasks: current existing-vhost Nginx include

## 交付物清单 / Deliverables

Three checked specifications; source-bound five-location current include renderer; pure contract tests; two native harnesses; one scoped workflow; operator documentation. Exact nine source paths are listed below.

## Plan

Probe plan: `feature-issue40-current-nginx-include-steady-07c2e52db3`. Baseline F: `310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`. Nine additive paths; all existing tracked blobs remain unchanged. Checkpoints must distinguish performed checks, unavailable native checks and historical evidence.

## 任务列表 / Ordered finite tasks

- [x] T1: Read AGENTS/Probe/project context, resume lookup then finite feature plan; independently clone exact F with sanitized Git and own objects (NFR-4)
- [x] T2: Reconcile historical include, current private topology and actual transport/identity contracts; run baseline 42 deployment tests; fresh GitNexus query/context/upstream analysis (FR-2/FR-3)
- [x] T3: Write concrete requirements/design/tasks and external preimplementation packet; no production code edits (all FRs)
- [x] T4: Run check_spec and estimate; obtain root manual design review, retaining HIGH semantic and read-only CRITICAL graph warning (NFR-4)
- [x] T5: Implement separate offline source-bound include renderer and pure/CLI drift/adversarial tests within approved paths (FR-1/FR-2/FR-3)
- [x] T6: Implement private actual Nginx mechanics, raw duplicate/empty-header preservation, namespace regex precedence, bare-path guard, raw-URI destination checks and exact Compose2.27 harness; then separate real-current-service fixture harness with mandatory raw-wire gateway rejection negatives with separate duplicate Authorization/Host Nginx400+zero-echo-upstream cases (FR-4/FR-5)
- [x] T7: Add scoped fresh native workflow/operator documentation; audit triggers and safe artifact contents; run affected tests/static checks and unchanged baseline regressions (FR-4/FR-5/NFR-2)
- [ ] T8: Independent code review and fresh staged GitNexus detect_changes; rectify only reviewed defects, verify nine additions/zero existing modifications (NFR-4)
- [ ] T9: Root review candidate, then authorized commit/push/draft feature-target PR; verify remote expected SHA/tree and all actual native jobs to terminal state (FR-5)
- [ ] T10: Authenticate job logs/raw artifact ZIP/source bindings, publish bounded evidence summary with live-host gates still open; checkpoint and converge only when declared evidence passes (FR-5)

## Commands and acceptance

- Pure baseline/current contracts: `python -m unittest discover -s tests/cloud-gateway-deployment -p 'test_*.py' -v`
- Compile new Python and actionlint new workflow; run exact-source cleanliness/path mode scope checks
- Native historical harness: `python tests/cloud-gateway-deployment/run_native_config_checks.py --compose <exact2.27> --nginx <private-binary>`
- Native current mechanics: `python tests/cloud-gateway-deployment/run_current_nginx_checks.py --compose <exact2.27> --nginx <private-binary> --output <new-safe-report>`
- Native current runtime: `python tests/cloud-gateway-deployment/run_current_nginx_runtime.py --compose <exact2.27> --gateway-image <source-id> --ingress-image <official-digest> --postgres-image <official-digest> --output <new-safe-report>`
- Portable current Rust service: `cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --lib --test service_contracts --test enrollment_contracts`

Local Docker/Nginx/Cargo are unavailable; local pure success is not native acceptance. Workflow must build exact current source and run both real native stages. Never reuse old source proof, skip required failures, loosen auth/header gates or substitute mock results for native tests.

## Stop and review conditions

Stop before code until manual review. Stop for any new path, auth/runtime modification, source compatibility failure, trigger expansion or provenance change. No production credential requests, host/DNS/TLS/WAF/service reload, 443 listener, publication/main/release merge, PR98 retry or Issue86/snapshot change. If all engineering tests pass, Issue40 remains open for live-host/security/deployment/rollback gates; report exactly what the new include proves.

## 需求覆盖矩阵 / Requirement coverage

| Requirement | Implementation and tests |
|---|---|
| FR-1 | T5 offline exclusive renderer, CLI/input/output refusal cases |
| FR-2 | T2 current reconciliation; T5 source-shape and digest drift cases |
| FR-3 | T5 native end-to-end header directives; T6 real Nginx and actual gateway duplicate/empty/Host/nonupgrade/regex cases |
| FR-4 | T6 mechanics/Compose2.27; T7/T9 current hosted execution |
| FR-5 | T6 actual service; T7 workflow; T9/T10 authenticated native evidence |

## 文件变更清单 / File changes

All additions, zero existing modifications:

- deploy/cloud-gateway/current_nginx_include.py
- tests/cloud-gateway-deployment/test_current_nginx_include.py
- tests/cloud-gateway-deployment/run_current_nginx_checks.py
- tests/cloud-gateway-deployment/run_current_nginx_runtime.py
- .github/workflows/issue40-current-nginx-include.yml
- docs/deployment/current-nginx-include.md
- docs/specs/issue40-current-nginx-include/requirements.md
- docs/specs/issue40-current-nginx-include/design.md
- docs/specs/issue40-current-nginx-include/tasks.md

## Current implementation checkpoint

Local deployment contracts68 (26 new +42 unchanged) and unchanged exact-build-audit22 pass with zero failures/skips. Python compilation and actionlint pass. Raw-wire tests use an owned local stdlib receiver; they do not establish native Nginx/Docker acceptance. Both hosted native jobs and final candidate review remain pending.
