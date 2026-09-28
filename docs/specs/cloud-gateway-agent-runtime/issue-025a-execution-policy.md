# ISSUE-025A — Deterministic Execution Policy Foundation

Status: **ENGINEERING_VERIFIED / PURE_POLICY_LAYER / NO_PROCESS_SIDE_EFFECTS / HOST_DEFERRED**

Published source: `5ff668fd9557f7d6156313cb311b1ba513c04520`.

## Delivered

- structured argv-only policy input; no shell-string parsing or expansion;
- bounded prefix rules with exact token or explicit alternative slots;
- explicit `Allow`, `Prompt`, `Forbidden`, and explicit no-match;
- strictest severity across all matching rules: Forbidden > Prompt > Allow;
- bounded human justification;
- load-time `must_match` / `must_not_match` rule examples;
- opt-in host executable basename fallback with exact absolute rule precedence and optional path allowlists;
- deterministic command fingerprinting;
- opaque scoped-approval validation bound to command fingerprint, request/conversation/workspace/tool context, local admission generation and expiry;
- prompt cannot execute without a matching scoped approval; Forbidden cannot be overridden.

This increment independently adopts architectural ideas from OpenAI Codex execpolicy. No Codex implementation code was copied.

No process spawn, shell, filesystem, Git, PTY, sandbox, network execution, desktop UI approval path, or cloud-generated approval was added.

## Verification

- Exact-source run `35737237159`: Windows 2025 + Ubuntu 24.04 PASS.
- Feature runtime run `35737499058`: Windows 2025 + Ubuntu 24.04 PASS.
- 21 tests pass per platform, including the existing 9 Tool Runtime tests.
- rustfmt, Clippy `-D warnings`, locked Cargo tests/checks pass.
- Exact verified local-agent tree from one-shot CI: `483ded342aeaa4161457603cf0a99ab4257dafc3`.

Retained failures:
1. initial run failed at rustfmt before compile;
2. next run reached compilation and exposed an `Option<ExecDecision>` type-inference error;
3. both were fixed without reducing warning/test strictness.

## Boundary

The policy is a contract layer only. A future process runtime must invoke it again at the final local start boundary. Approval issuance remains deliberately absent from public production API in this increment.
