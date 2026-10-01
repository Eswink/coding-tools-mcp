# Separate broker-direct LPAC pilot

This is a CI-only comparison of direct process creation by the native broker. The
20 required nested Rust-child rows and all original native foundation files remain
byte-identical. Their failures continue to fail the job. Nothing here is a
production fallback, a release acceptance reduction, or a Python packaging change.

## Current read-only parent observation

The current workflow invokes `run-parent-candidates.ps1`, which observes exactly
RUNNER_TEMP, the current broker's documented LocalApplicationData path, and its
literal Temp child. LocalApplicationData is retrieved with `DoNotVerify`, never
`Create`; each candidate must be an exact local absolute path before an
`OPEN_EXISTING` handle is requested. The same bounded parent owner/DACL/identity
checker is reused without modification. No directory, sandbox root, profile,
listener or target process is created by this observer. Only bounded create-new
receipt files are written into the existing workflow evidence area.

The full RUNNER_TEMP ACL observation at2153687/run36790412270 recorded seven ACEs.
The unchanged first rejection remains the inherit-only CreatorOwner entry3, while
unresolved trustee entries5/6 also carry effective directory-write grants. No
pilot root, profile or target was created in that run. A CreatorOwner-only change
would not satisfy the unchanged trust policy.

A favorable `candidate_trust_verified` observation requires normal checker
completion, final same-handle identity verification and confirmed cleanup.
`selected_for_execution=false` remains explicit. There is no candidate fallback,
selection, permission repair, marker resolution or runtime attempt. Missing paths
are reported only from the initial open's errors2/3; later metadata errors cannot
be recast as absence. Uncertain cleanup stops remaining observations. The original
20 nested controls, native foundation failures and old pilot sources remain
required/preserved. A future parent selection requires separate review of fresh
checks and that exact recovery namespace. `parent-candidate-audit.py` enforces the
exhaustive union of all preserved and new C#/PowerShell sources; its managed tests
exercise pure observation gates, not Windows compatibility.

## Explicit observed-token pilot (retained entry point)

`run-pilot.ps1` selects only the CI policy `accesscheck_signature_v1_ci`. The same
invocation first checks a suspended ordinary-AppContainer native control and proves
that its actual identification-token signature is rejected as LPAC. It then checks
and resumes the unchanged LPAC native reference, followed by exactly Node, cmd,
Windows PowerShell and pwsh. Every target's own suspended primary token must pass
AppContainer/SID/zero-capability/LowIL checks and its own noninheritable query-only
identification duplicate must pass all four fixed AccessCheck descriptors. All
observer/source handles close before assignment/resume. Requested flags and the
known Win32/native class46 failures never become authority proof; those failures
remain recorded, and changed method-diagnostic results halt for review.

The unchanged eight-row qualification was measured at f5a4d7b in run36779515843.
That run resumed no target. The separate old entry points remain unchanged and
still prohibit resume. Current pilot compatibility conclusions require its own
Windows execution; portable source tests and managed synthetic tests are not
runtime support evidence.

The native reference can qualify the offline launch/filesystem route with exact
preliminary receipts plus WSAStartup10107/exit15107, while its full native gate stays
failed. Even exit0 and all five native booleans do not prove a precise network
authorization denial: the fixture records connect failure through is_ok(). Every
pilot receipt keeps network_denial_proven false. The original20 nested rows and
foundation failures remain required and independently fail the workflow.

A current-owner run journal survives all case receipt/matrix writes. Case journals
bind planned profile/root names and immutable nonce-bound cleanup preconditions;
actual root/profile/process ownership is recorded as it becomes known. Hidden,
wrong-type, reparse, old, failed or unknown markers stop allocation, resume, cleanup
or final completion. No prior marker is repaired or cleared. Every subject must
stop, every job drain, every owned handle close, and capture pass before the exact
owned profile is deleted through DeleteAppContainerProfile S_OK. This is documented
API-confirmed profile deletion, not independent inspection of all OS-managed
storage. Exact newly created private roots are disposed via identity-checked
no-follow handles, with bounded parent enumeration proving root-name absence.
Unknown ACL/object shapes or cleanup errors retain recovery without repair.

The cleanup parent-owner check uses an explicitly bounded current-broker
TOKEN_QUERY-only TokenUser read. It is separate from target authority verification,
never duplicates or impersonates the broker, does not log its SID, and each query closes
before its helper returns and before any later target creation/resume. No new ACL template or privilege is introduced.

The completed journal commits only the six required case outcomes, any subject/
profile scopes actually created, and the disposable run root. Preparation evidence,
PowerShell loopback-listener teardown, outer workflow capture and artifact upload
are separate outcomes. New journal/ownership/precondition/case/matrix records use
Flush(true). The unchanged bounded raw capture helper provides validated copying
and confirmed close; it does not claim power-loss-durable raw files. Final C#
journal resolution binds its immutable preconditions record and is the last
required fallible C# pilot action. No later launch is possible.

`pilot-audit.py` retains its original pilot-source contract and pins
preserved entry points, rejects partial-class load-time initializers/member
collisions, and tests authority/lifecycle mutations independently of hash pins.
Managed policy, commit-order, cleanup-gate and classification tests execute the
same pure C# predicates during Windows CI; they never open a real token or process.

## Original direct-method boundary (retained source)

1. Require the retained native live control and ordinary-AppContainer AAP-read
   witness. Refuse another launch while an earlier owned diagnostic recovery
   marker exists.
2. Launch the unchanged native foundation binary first through the new method.
   Require its four exact pre-network assertions, verified target token and clean
   lifecycle. Exit 15107 is still WSAStartup 10107, an initialization failure.
3. Only after that matched reference, launch exactly Node, cmd, Windows PowerShell
   and pwsh. Each uses a fresh owned workspace and disposable hashed runtime copy.
   No runtime is warmed up outside LPAC. Standard setup-action version queries are
   ordinary CI setup, not diagnostic runtime warm-up.
4. Use the same zero-capability AppContainer profile, LPAC opt-out, private code RX,
   workspace Modify, outside-AAP RX canary and kill-on-close job templates. The
   environment matches the nested private-EOF/headless cases, including private
   LOCALAPPDATA. This differs from the older outer native fixture environment and
   is why the matched reference is required.
5. The only inherited objects are exactly three fresh empty regular workspace
   files: readonly input, write-only output and error. Validate disk type, final
   path, link count, identity and initial length. The explicit HANDLE_LIST contains
   those same three real handles. Close every broker copy before resume.
6. Query the actual suspended child's token with TOKEN_QUERY only. Require
   AppContainer=1, LPAC=1, exact newly created profile SID, zero capabilities, and
   integrity SID S-1-16-4096. Validate returned buffer headers and embedded SID
   pointer/span bounds before dereferencing. Close the token handle before resume.
   No token, capability, privilege, desktop or window-station adjustment occurs.
7. Assign the suspended child to the job before resume. Wait at most 30 seconds;
   terminate/reap and verify activeProcesses=0. Never resume on setup uncertainty.
   A recovery marker exists before resource preparation and survives all throwing
   cleanup/capture paths. Only complete confirmed cleanup clears it.
8. Broker evidence capture waits for both target stop and job drain. It uses a
   no-follow handle, validates the exact private regular object (including original
   stdio identity), and reads from that same handle. Missing validated stdio is an
   evidence failure; only optional script receipts may be absent. Each capture has
   a hard 1 MiB metadata and actual-stream limit, with explicit failure rather than
   silent truncation. Any uncertainty retains the
   owned recovery scope rather than deleting it.

## Interpretation

Receipts distinguish native CreateProcessW failure, suspended-token/setup failure,
child exit, script entry, stdout, workspace mutation, exact runtime canary results,
and lifecycle. Missing user-code receipts cannot prove access denial. Node records
EACCES; PowerShell records the full UnauthorizedAccessException type and HResult
0x80070005. cmd errorlevel remains explicitly inconclusive as raw denial evidence.
Actual target token verification and host outside-canary checks are independent.

The direct pilot does not cover Python, npm.cmd, Git multistep/nested behavior,
ConPTY or production integration. A directly launched executable is not evidence
that its nested child creation works. None of these process observations establish
network denial. The unchanged native network probe remains separate.

## Validation

`python tests/windows-broker-direct/audit.py` performs portable source and mutation
checks; it does not execute Windows APIs. The Windows workflow separately compiles
all C# helpers under PowerShell 5.1 and executes the measured pilot. Source SHA/tree,
binary hashes, source/destination copy hashes, exact environment/argv, per-case
receipts and an artifact-wide SHA256 manifest accompany the run.

Primary API contracts:
- [Attribute handle lists and security capabilities](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
- [Token information classes](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class)
- [AppContainer process implementation](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
- [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)

Known loader/initialization status names come from the [Microsoft NTSTATUS table](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55). Absence of a script-entry receipt remains inconclusive about the exact failure phase.

## Token-query call-shape diagnostic

The first broker-direct run (208b34f / 36768242988) created its native reference
suspended, verified private stdio and TokenIsAppContainer, then failed the class46
null/zero sizing call with error87. It did not resume or attempt any runtime.
The observation remains in the receipt. A separate single initialized four-byte
class46 query records API success/error, exact returned size and raw storage.
Only success plus returned size4 makes the value valid; only value1 satisfies the
mandatory LPAC predicate. Other required token observations run independently,
with explicit success flags and nullable missing values. Every predicate and the
token close still must pass before resume.

The [Win32 buffer API](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation)
and enum do not establish per-build support or a class46-specific output contract.
The DWORD hypothesis comes from the [native/driver enum](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ne-ntifs-_token_information_class),
which is a different documented surface. This is a bounded read-only call-shape
observation, not a claim of portable Win32 support. A failed fixed-size query stays
unverified/no-resume; it is not retried through reserved attributes or native APIs.

## Native query comparison, observation only

The next bounded comparison uses the same already-open TOKEN_QUERY handle to the
suspended reference: one class 29 control and one class 46 NtQueryInformationToken
call, each with aligned initialized four-byte storage. Raw NTSTATUS, returned
length, buffer value and unchanged sentinel flags are recorded independently.
The native return-length storage is also initialized so an unwritten value is
visible. No native result contributes to the unchanged Win32 acceptance expression.

An explicit observation-only guard before job assignment prevents resume even if
the Win32 predicate unexpectedly passes. The existing termination, drain, handle
closure and retained recovery path then applies; no direct runtime is launched.
This is not a native fallback or permission to replace the verification policy.
No alternate-class search, token duplication/impersonation, additional rights or
security changes are involved.

[NtQueryInformationToken documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntqueryinformationtoken)
provides the read-only TOKEN_QUERY contract and native status distinctions. It does
not prove class 46 support on the measured runner. The results are confined to this
exact API shape, token and runner image.

## Paired AccessCheck qualification, still unadopted

The qualification commit f5a4d7b routed the single observation invocation to
`run-qualification.ps1`. The old single-reference source and evidence remain;
its retained failure is not followed or bypassed by a second invocation. The new
entry refuses any prior recovery marker, prepares exactly two native references
(ordinary AppContainer and LPAC-configured) suspended in independent fresh fixture
scopes, and gathers both sets within one bounded unit. It has no job-assignment
or resume path. Cleanup attempts both exact-process stops, drains and all owned
closes even if another operation fails; empty jobs are not process-stop proof.

Only the new target's actual primary token is opened with QUERY|DUPLICATE (0xA).
After primary/AppContainer/SID/zero-capability/LowIL checks, DuplicateTokenEx requests
QUERY only (0x8), NULL attributes, SecurityIdentification and TokenImpersonation.
The returned handle is verified non-inheritable and property-matched. It is used
only for token inspection and AccessCheck, never thread impersonation, resource
access or process creation. Failed API outputs do not establish ownership and are
never blindly closed. All original Win32/native class46 failures remain recorded.

Each verified identification duplicate is tested against four fixed absolute
in-memory descriptors, all owned by/grouped to LocalSystem, with no SACL, no NULL
DACL or inherited ACE. Concrete World/AAP/ARAP allow masks reproduce Chromium's
mixed test and three controls. DesiredAccess is MAXIMUM_ALLOWED only inside
AccessCheck; generic mapping is zero and checked after MapGenericMask. Neither
these descriptors nor their results alter any real object's ACL.

Expected candidate signatures (API success is mandatory in every row):

| Descriptor | Ordinary access status / mask | LPAC access status / mask |
| --- | --- | --- |
| World3 + AAP1 + ARAP2 | true / 3 | true / 2 |
| World1 + AAP1 | true / 1 | false / 0 |
| World2 + ARAP2 | true / 2 | true / 2 |
| World3 only | false / 0 | false / 0 |

The ordinary/supplementary expectations are hypotheses requiring this exact
qualification, not previously measured results or a versioned IsLPAC contract.
Unknown/error/wrong-mask output rejects qualification without recalibration.
AccessStatus/GrantedAccess/privilege outputs use non-passing sentinels; only
API-success and bounded valid output are interpreted. A fixed20-byte privilege
buffer must describe zero privileges; this deliberately stricter limit can fail
inconclusively. Denied AccessStatus retains its immediate last-error observation.

An eight-row matching signature is evidence about the verified duplicates of these
actual targets only. It never changes TokenVerified, adopts a verifier, resumes a
reference or runs a runtime. Individual cleanup receipts are separate from the
intentionally false full CleanupConfirmed and retained recovery marker. The step
remains failed and all original20 rows/foundation gates remain required.

`qualification-audit.py` retains qualification source pins and authority/output/
cleanup mutations. The current parent-observation audit enforces exhaustive union
coverage together with all preserved source pins. Portable audits do not execute
Windows APIs; C# compilation and the real paired matrix remain distinct CI stages.

Primary implementation reference: Chromium
[CheckLpacToken](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/sandbox/win/src/app_container_test.cc#109),
[identification duplication](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/base/win/access_token.cc#211),
and [AccessCheck wrapper](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/base/win/security_descriptor.cc#437).
Microsoft documents [DuplicateTokenEx](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-duplicatetokenex)
and [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck).
