# Consume-once private-directory ownership design

## 概述
Issue111 implements reviewed bounded v2 at exact M. FR-1–FR-8 are independently source- and inventory-bound; synthetic faults establish control flow only.

## 技术方案
FR-1: Assign child to the loop cleanup owner before attempting previous-parent close. Consume terminal local owner before cleanup; successful return transfers final ownership without closing it.
FR-2: Both created and existing child identity guards consume child before close and re-raise; enclosing parent cleanup still runs when child cleanup fails. Recorded directory entries and filesystem objects are not rolled back.
FR-3: Constructor uses local parent/root owners. Root identity is recorded before parent close; parent ownership is consumed before the attempt. Only success publishes self.fd and clears local root. Nested finally consumes root then any still-owned parent; normal parent-close failure therefore attempts parent then root without parent retry.
FR-4: Constructor OSError boundary surrounds acquisition and all cleanup, intentionally normalizing formerly raw final-parent-close OSError to unsafe_root_parent. Identity ConsumerError and non-OSError/cancellation propagate when cleanup succeeds; later cleanup exceptions have ordinary precedence and retained in-process context. No raw context enters public reports.
FR-5: Test-only helper is inert at import, verifies names/sizes/SHA256 of historical IO and unchanged C worker/transport before writing, owns temporary root, registers cleanup immediately and patches only self.h.ROOT. Test module ROOT/production() and24 original method ASTs remain unchanged. Actual corrected IO is rejected by unchanged C loader before execution/API.
FR-6: Historical profile reads frozen M Git-object bytes with original J, ALLOWED22, NARROW2, transport/supervisor/live pins and3966 budget. Separate ownership overlay pins corrected IO/proof test/fixture/workflow, permits only12 reviewed paths and caps2200 additions/deletions. No circular helper imports or runtime dependency.
FR-7: Topology-only classifier validates pure P chain1..16 to M; F has exactly[M,P] and same tree; L has exactly[R,X] with X validated by non-release classifier. Malformed valid-tree controls isolate topology; content drift remains separate. No arbitrary descendants of F or nested release acceptance.
FR-8: Current-source regression includes34 ownership and6 historical-boundary tests; pretag adds11 composition/topology and3 failure boundaries. Proposed596=542+54 requires actual unique execution, including24 explicitly historical cases. Preserve failed red evidence and compare all non-target runtime text and historical ASTs.

## 文件结构
Runtime: scripts/rc_consumer_io.py (three definitions only).
Consumer tests: scripts/rc_consumer_io_ownership_tests.py; scripts/rc_consumer_default_worker_proof_tests.py setup only.
Historical data/helper: scripts/rc_consumer_c_93c2ad95_io.txt; scripts/rc_consumer_proof_fixtures.py.
Composition: scripts/rc_pretag_composition_tests.py; scripts/rc_pretag_ownership_profile.py; scripts/rc_pretag_ownership_tests.py.
Workflow: .github/workflows/rc-pretag-evidence-checks.yml adds exact branch and six explicit push/PR inputs only.
Specifications: docs/specs/rc-consumer-close-ownership/{requirements,design,tasks}.md.
No additional runtime helper, retry, destructor, rollback, live workflow, host, permission or release change.
