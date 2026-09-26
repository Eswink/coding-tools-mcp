# Dependency-driven delivery

Tracking: GitHub #48; overall Epic #32. This scheduler is not a coding model or an
external worker. A packet means **queued work**, never execution started or an
issue's acceptance automatically passed.

`manifest.json` records bounded engineering components separately from the
36-task roadmap. A verified component references an immutable Git revision, CI
run ID and file digests. The scheduler checks Git/current file identity and
propagates stale dependencies. CI run references must also be independently
checked before changing a component to verified. Editing a status or closing a
GitHub issue alone is not proof. Review scope completeness before accepting a
file fingerprint; hashing one unrelated file is not meaningful verification.

Only dependency-ready tasks are selected; an in-progress lane or overlapping
source subtree is reserved, and conflicting active writers fail closed. Packets
have deterministic priority/id ordering, no arbitrary executable command, and
at most eight tasks. Unknown fields, missing dependencies, cycles, ambiguous
IDs, path traversal and missing release gates are rejected.

```sh
python tools/delivery/dispatch.py --manifest tools/delivery/manifest.json \
  --repo-root . --output /tmp/cloud-delivery-new-report.json
python -m unittest discover -s tests/delivery -v
```

The output file must not already exist. `--require-release-ready` returns status
2 when gates are incomplete, while preserving the report. Even a clear report
is only eligibility for release review, not authority to publish. The final
publisher independently verifies exact candidate CI, packaging hashes, review,
rollback and release truth. There is no release upload, token, network call or
shell command in this program.

`cloud-delivery.yml` tests and computes packets with a read-only token. Its
separate issue-metadata job has no checkout and never executes candidate source,
issue text or artifact binaries. It validates fixed packet fields and bounds,
rechecks the current feature head, deduplicates issue markers, and posts bounded
queue receipts. It does not launch coding agents, close unverified work, deploy
to a VPS, create a release, bypass branch protection or import secrets. Only the
trusted feature branch's push event can mutate issue metadata; PR runs are
read-only. New issue tasks must still be picked up by an authorized coding
execution channel and verified before completion.

The real-ChatGPT, installed-host and supported-server gates remain deferred or
blocked when not observed. Neither code tests nor a queued issue changes them
into PASS. CentOS Stream 8's unsupported-host risk is not fixed by containers.

Security references checked 2026-09-22:
- https://docs.github.com/en/actions/reference/security/secure-use
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://github.blog/security/supply-chain-security/four-tips-to-keep-your-github-actions-workflows-secure/

The workflow is push-driven on the feature branch; default-branch-only issue,
schedule and workflow_run triggers are intentionally not claimed active here.
