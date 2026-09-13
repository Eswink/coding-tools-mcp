# Release drain-startup evidence

## Round 1: unchanged failure gate with diagnostics

Candidate c7f3a2a98f46d6cb3994b6be638d0619416d73fd; run34761133754. Three predeclared isolated Windows samples succeeded with actual ResumeThread previous count1 and readiness1069/105/95ms. Artifact10319350874 digest33ba991ef2806a34de8ff85a1167dd9589e1869dd76f04dbe2294d074776f7a7 verified locally.

The parallel Windows full suite reproduced the original failure:346 passed,1 failed,0 ignored/filtered. At the original8s gate the task was running with empty output and no persistence failure. Three seconds later it was terminal timed_out, no output and no marker. Artifact10318843917 digest72c3597a701da5fa8b04888fc90f90b4e5c04ccc03a82e4fe1bc8834316fa73e verified locally. This is not a mere missing external Python executable: an execution session existed and the child deadline terminated it. The original release failure remains open.

Rust's captured test output did not include the global executor thread's ResumeThread trace with the failing test. Round2 changes the diagnostic job from isolated sampling to one full parallel library run with --nocapture and adds only a cfg(test) PID/cwd association. It preserves8s readiness and10s actual task timeout, all default parallelism and production behavior. Root cause is still unassigned; the count0/first-thread hypothesis needs correlated evidence. No rerun-until-green and no publication.
