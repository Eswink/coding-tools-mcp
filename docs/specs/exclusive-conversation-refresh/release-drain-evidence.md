# Release drain-startup evidence

## Round 1: unchanged failure gate with diagnostics

Candidate c7f3a2a98f46d6cb3994b6be638d0619416d73fd; run34761133754. Three predeclared isolated Windows samples succeeded with actual ResumeThread previous count1 and readiness1069/105/95ms. Artifact10319350874 digest33ba991ef2806a34de8ff85a1167dd9589e1869dd76f04dbe2294d074776f7a7 verified locally.

The parallel Windows full suite reproduced the original failure:346 passed,1 failed,0 ignored/filtered. At the original8s gate the task was running with empty output and no persistence failure. Three seconds later it was terminal timed_out, no output and no marker. Artifact10318843917 digest72c3597a701da5fa8b04888fc90f90b4e5c04ccc03a82e4fe1bc8834316fa73e verified locally. This is not a mere missing external Python executable: an execution session existed and the child deadline terminated it. The original release failure remains open.

Rust's captured test output did not include the global executor thread's ResumeThread trace with the failing test. Round2 changes the diagnostic job from isolated sampling to one full parallel library run with --nocapture and adds only a cfg(test) PID/cwd association. It preserves8s readiness and10s actual task timeout, all default parallelism and production behavior. Root cause is still unassigned; the count0/first-thread hypothesis needs correlated evidence. No rerun-until-green and no publication.

## Round 2: distinguish a proven API-contract defect from incident attribution

The one full parallel uncaptured sample at f256844 succeeded (347 library tests, 10.76s); the HTTP child signalled readiness at2482ms, and all15 observed ResumeThread counts were1. Artifact10318749882 SHA256a0c5eaa68a9f53cd7d0d96f7cff7b1fb1560d239140c94c6c9e3b943ced26255 was verified. This does NOT prove count0 caused either historical failure. The intermittent failure is preserved, not relabelled PASS because a later sample succeeded.

The production function nevertheless has a demonstrable Windows API-contract defect: it returns successful suspended startup after ResumeThread reports0 (no thread resumed) or>1 (still suspended). Round3 requires exactly1, continues enumeration after0, rejects extra suspension depth/errors, and verifies the opened thread still belongs to the held child process before mutation. Job assignment remains before execution and failure still kills/reaps the owned child; no policy/scope/time-limit relaxation.

A self-contained actual Windows child regression waits for a cmd.exe child to announce readiness while holding stdin, then invokes the startup gate again. That second call cannot count as a suspended-to-runnable transition. The same new test is compiled against original main1c0395da: it must fail the exact no-op assertion AFTER successful readiness/cleanup. Candidate adds this native case and three result-contract tests. These are not OS-toast, installed UI or real-ChatGPT tests.

The HTTP drain test keeps the original8s startup and10s execution limits. It now fails immediately with authoritative local task diagnostics if the child terminates before readiness, verifies the actual ready marker, gives the separate drain phase its own8s observation deadline, and demands succeeded/exit0/complete output/no running process plus the child's drained output before allowing the successor. A timeout can no longer masquerade as successful drainage. The local observer is test-only read access; neither revoked A nor B gains access.

Impact is limited to managed Windows spawn/resume, the HTTP fixture, native regression and repair orchestration. Existing deadline/cancel/process-tree/local-approval controls are unchanged. Manual review replaces unavailable pinned Probe/GitNexus as already recorded; it is not graph validation. Candidate/full-source/failure-first/native/package gates remain required. Do not claim incident root-cause certainty without correlated evidence.
