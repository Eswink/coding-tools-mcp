# Iteration 17: initial stdin delivery and bounded process input

Parent: `a405848662b1fec1fa71fa104b895bb7f4a8540c`, tree `a657a8705205ddf16174de5d67f878e7bf0a14b6`.

## Findings and scope

Source inspection found that `run_command` returned on `yield_time_ms: 0` before delivering supplied stdin. With a nonzero yield it awaited an unbounded pipe write before starting a timeout monitor or checking the deadline. A child which does not consume input can therefore delay the call beyond its execution budget. These are independent defects; neither is asserted to explain the intermittent no-input PowerShell timeout in run `34684664507`.

That separate Windows failure was verified from artifact `10295247537` (SHA-256 `4f89c77706759f821a3c031e28feba7e5568cc367120db5b021e4154f999a226`): 313 unit tests passed, one failed, and a direct PowerShell invocation returned no output after its explicit 30-second deadline. The same unmodified test later passed in run `34685494449`. The source's managed suspended-thread path is not called by this direct-command test. Its thread-enumeration/resume-count concern remains a separate hypothesis, not a demonstrated cause or a completed fix. No timeout budget, retry-to-green, or platform exception is added here.

## Repair and manual impact review

Reserve supplied non-interactive stdin before returning a session, and deliver it in a session-owned task bounded by the process's original deadline. Empty stdin retains the existing writable-session contract. Supplying a complete input batch retains its EOF boundary; a later write cannot overtake it. TTY behavior is unchanged.

On failed/expired delivery, close the owned pipe and terminate the owned child through its existing process-management path. Join the input task with bounded cleanup before reporting terminal output, preserve an explicit user-kill or existing timeout reason, and never classify partial delivery as command success or a spawn failure. Return structured `STDIN_WRITE_FAILED` evidence without the input contents and without automatic-retry advice. Retained monitors also join I/O after a natural exit.

Manual upstream/downstream trace covers `call_tool` -> `exec_command` -> `run_command` -> `ExecSession`, retained `write_stdin`/`kill_session`, async managed jobs (which do not accept initial stdin), and HTTP/native consumers of the same tool kernel. Risk is HIGH for execution and cancellation. Command parsing, authorization, filesystem policy, shell flags, Job Object ownership, production timeout defaults, native assertions and release gates are unchanged. MCP/GitNexus unavailability and the manual fallback remain as documented in prior iterations; no graph-tool success is claimed.

## Verification and limits at submission

Six new integration cases execute actual Python children: zero-yield exact UTF-8 input, waiting-call input plus EOF, blocked input deadline, responsive zero-yield with blocked input, early child exit/partial-write failure, and preserving explicit kill while input is pending. The blocked-input fixture exits after four seconds even on the baseline, bounding test failure cleanup.

The OAuth CI matrix first checks the zero-yield case against the two unmodified parent source files. It requires an actual test failure (not a compiler error), restores the exact candidate with a shell trap plus `git diff --exit-code`, and then runs all six candidate tests three times before the unchanged complete Rust baseline. Both platforms must pass. It does not treat the intentional baseline failure as candidate acceptance.

Local frontend tests **124/124**, authorization helpers **105/105**, release-readiness tests **13/13**, and release-gate tests **19/19** pass. YAML parsing and whitespace checks pass. Rust and native execution are NOT available in this container; their exact-head results are pending CI, including the failure-first characterization. Source inspection is not represented as a completed red/green native experiment.

Scoped self-review: **91/100**, candidate pending real cross-platform execution. No merge, release, overall completion or explanation of the unrelated intermittent PowerShell timeout is implied.
