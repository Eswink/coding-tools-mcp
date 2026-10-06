# Requirements: Linux package provenance and scoped RELRO preservation

## 功能概述
The current engineering AppImage moves the main ELF and four GLib families' dynamic tables outside their original GNU_RELRO ranges. This increment preserves those authenticated inputs and captures compiler/package/runtime observations during the existing real build and installed tests.

Baseline M: fd7b303839aa648d33456f7aaeec6388bfb696c4; tree e4ab19e2fe4bfbb1fef9e0cd713a6fbb18d03995. Existing static proof belongs to D23be745924cc85da84901da8cdd4a65db1673734/run37447375708 and does not certify a new build.

## Facts to preserve
- Documented/tested AppImage and extract-and-run entrypoints use AppRun; no new environment-free extracted-ELF promise is introduced
- Pinned linuxdeploy may swallow setter failure status, so wrapper exit status alone cannot enforce acceptance
- There are nine protected destinations: main plus eight regular aliases from four signed-origin Ubuntu GLib families
- The observed hardening difference is neither a proven exploit nor automatic security approval
- Historical compiler proof, current package proof and new-candidate proof have distinct source identities

## Scope
Use the existing Linux workflow's one Tauri build and four Ubuntu22/24 × DEB/AppImage installed jobs. Reuse the compiler collector, scoped original-tool delegation and bounded runtime observation. Keep project AppRun, five tool/cache pins, runtime pin, marker normalization, dependency copying and all original behavior.

Application Rust, DEB linker/search behavior, Windows/snapshot implementation, credentials, capabilities, system trust/security settings, held PR98 correction paths and FINAL/main/release/publication activation are excluded. Other bundled DSOs and complete lifetime closure remain outside the scoped preservation claim.

## 需求列表

### FR-1: Preserve historical producer contracts
Priority: Must
As a release engineer, I need new observations without relabeling historical proof.
1. WHEN the historical entrypoint runs THEN its producer, argv, environment, inventory and failure semantics SHALL remain exact
2. WHEN engineering evidence is verified THEN a trusted caller SHALL select its closed profile and authenticate source/tree/workflow/run/attempt independently of the envelope
3. IF a profile, producer, source or override is unsupported THEN verification SHALL reject it

### FR-2: Preserve only authenticated protected inputs
Priority: Must
As a package maintainer, I need protected bytes and RELRO while normal discovery/copying continues.
1. WHEN an exact reviewed RPATH addition targets an authenticated protected file THEN the wrapper SHALL preserve its bytes and record that decision
2. WHEN a query or legitimate unprotected operation runs THEN original argv and status SHALL be delegated to the authenticated pinned backend
3. IF a protected identity, alias, destination, path or mutating request is outside the contract THEN failure SHALL latch before mutation
4. WHEN main is admitted THEN expected bytes SHALL derive from this build's retained compiler output and the exact unique APP marker change
5. WHEN an imported protected library is admitted THEN its hash SHALL match the reviewed signed-Ubuntu input; names and versions alone SHALL NOT authorize it

### FR-3: Enforce sticky failure and final protection
Priority: Must
As a reviewer, I need upstream error swallowing to remain a failed package result.
1. WHEN an operation is handled THEN owned bounded records SHALL preserve every failure as sticky state
2. WHEN packaging completes THEN the post-build gate SHALL require complete operation state, exact protected inventory, original protected bytes and effective dynamic-table RELRO coverage
3. IF a backend, receipt, target, identity or cap check fails or is absent THEN engineering package upload SHALL be blocked and failure evidence retained
4. IF optional GStreamer calls are outside the reviewed hook route THEN they SHALL NOT be silently treated as covered

### FR-4: Capture the single necessary build
Priority: Must
As a dependency reviewer, I need actual current compiler observations.
1. WHEN Tauri builds the product THEN the existing runner/capture algorithm SHALL retain compiler JSON, input/output traces, pre-bundle ELF and GLib rlib from that single invocation
2. WHEN paths are prepared THEN target, evidence and control roots SHALL be fresh, disjoint, owned and outside tracked source; every participant SHALL use the same authenticated target/triple
3. WHEN DEB repacking occurs THEN raw and RC archive identities SHALL remain distinct with exact payload equality
4. IF compiler/source/target evidence is incomplete THEN no second build, post-hoc search or older artifact SHALL substitute for it

### FR-5: Bind final package bytes
Priority: Must
As a package reviewer, I need a concrete compiler-to-package relationship.
1. WHEN evidence is emitted THEN it SHALL bind source/tree/attempt, tools, compiler observations, raw DEB, final packages and bounded AppImage ELF inventory
2. WHEN AppImage payload equivalence is claimed THEN the exact reviewed transformation SHALL be checked without normalizing away unknown changes
3. WHEN artifacts are consumed THEN actual artifact identity/digest/owned bytes SHALL authenticate them; self-declared JSON hashes SHALL NOT authenticate themselves
4. IF any source, attempt, archive, member or payload binding differs THEN verification SHALL reject it

### FR-6: Observe mapped files without new authority
Priority: Must
As a security reviewer, I need observed file identities rather than inferred loading.
1. WHILE existing sessions run THEN bounded observers SHALL follow owned PID/start-time identities and record mapping checkpoints
2. WHEN bytes are hashed THEN opened descriptors SHALL match device/inode and stable process/mapping identity; a same-named host file SHALL NOT substitute
3. IF a mapping is deleted, inaccessible, transient, ambiguous or over budget THEN the result SHALL remain incomplete or unobserved
4. WHEN distro ownership is reported THEN it SHALL remain separate from authenticated archive-byte correspondence
5. WHEN observation stops THEN workers/descriptors SHALL close without masking original test or cleanup failures
6. IF a required observation needs elevated access, ptrace/security changes or sandbox weakening THEN the claim SHALL remain blocked instead

### FR-7: Preserve installed behavior and environment
Priority: Must
As a maintainer, I need existing native acceptance to retain its meaning.
1. WHEN any installed job runs THEN startup-before-driver installation, all four startup cases and every native permission/OAuth/foreign-request/expiry/restart/drain/cleanup stage SHALL remain intact
2. WHEN native observation is attached THEN actual desktop/WebKit descendants across both sessions SHALL be distinguished from the driver PID
3. WHEN environment evidence is retained THEN only a bounded explicit projection SHALL be recorded; whole environment and credential dumps SHALL be forbidden
4. IF the existing HTTP fixture does not load a TLS module THEN that module SHALL remain unobserved
5. WHEN preservation is enabled THEN AppRun and its existing loader environment SHALL remain unchanged, with no DEB link/search change

### FR-8: Admit a finite reviewed increment
Priority: Must
As a reviewer, I need exact source scope and honest evidence limits.
1. WHEN source is admitted THEN fixed anchors, trees, ordered parents, paths, modes, hashes and budgets SHALL be enforced
2. WHEN old guards read changed current source THEN exact inverses SHALL recover historical bytes and preserve assertions/pins
3. WHEN tests run THEN original815 cases and mandatory affected supplemental cases SHALL remain with a disjoint exact new inventory and no skip substitution
4. WHEN results are reported THEN source specificity, sampled coverage, other-DSO limits, raw advisories and open Windows/snapshot/security/FINAL/publication gates SHALL remain explicit

## 非功能需求
- Fix extraction, operation, ELF, process, mapping, byte and time caps before implementation; exceeding them is never silent truncation
- New helpers are consumed by the existing build/tests; no standalone framework, daemon or generic executable proxy is introduced
- Source files stay at most500 lines through explicit finite module splits
- Workflow permissions, real regression failure semantics, cleanup authority and historical native evidence are preserved

## Acceptance boundary
The source-grounded starting inputs are current-D static comparison, signed-Ubuntu origin comparison and pinned-tool source analysis. The new candidate must produce its own compiler, protected-byte, installed-runtime and authenticated artifact evidence. Collection success is not global security or release approval.


## 依赖关系
Use the existing compiler/link/probe/DEB helpers, fixed five tool inputs, official Ubuntu squashfs-tools, current AppRun and existing native harnesses. No credential, capability or system-trust dependency is added.
