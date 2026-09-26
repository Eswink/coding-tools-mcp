# Issue delivery automation contract

Tracking #48. Refer to `tools/delivery/README.md` for the tested contract.

The execution lanes are protocol, identity, agent-client, request-admission,
tool-runtime, packaging, release-review and delivery. They are queues, not
claims of independent AI workers. The available native connector can create
issues and comments; no external coding-task provider has returned a worker
receipt. Current development is performed by the active authorized agent.

The scheduler computes the next dependency-ready packet without asking the
user to restate the plan. Actual coding starts only after reading that packet,
repository rules, current source and its impact; completion requires tests,
review and source-linked publication. CI metadata queueing and code execution
are separate privilege boundaries. At most one writer may reserve a lane or
an overlapping subtree at once. Physical tests intentionally deferred by the
user remain separate from engineering readiness and may not be rewritten PASS.

No stable release while implementation, security/packaging or external gates
remain missing. A future prerelease must state exactly what is implemented and
unverified; this scheduler is not a release publisher and cannot relax that
boundary to satisfy a deadline. Existing main and production services remain
unchanged until a tested, reviewed release operation is explicitly performed.
