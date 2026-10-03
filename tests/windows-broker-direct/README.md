# Separate broker-direct LPAC pilot

This is a CI-only comparison of direct process creation by the native broker. The
20 required nested Rust-child rows and all original native foundation files remain
byte-identical. Their failures continue to fail the job. Nothing here is a
production fallback, a release acceptance reduction, or a Python packaging change.

## Additive cmd exit sentinel

The pilot preserves the six original cases and appends `cmd-exit23`, followed by
the separately identified `cmd-batch-exit23` comparison.
It launches a fresh private copy of the original cmd case's verified executable
bytes with exactly `/d /q /c exit 23`. The experiment identity remains distinct
from its `Launcher.Kind=cmd` runtime family. Its own suspended target must satisfy
the unchanged token, private stdio, job, deadline and cleanup predicates.
An observed exit 23 records only that builtin result; it never sets the original
script's positive result or establishes runtime support or network denial.

Before the original cmd case creates a profile or process, it captures the actual
generated `direct.cmd` bytes to `generated-direct.cmd.bin`. A bounded no-follow
regular-file read records the exact identity, byte count and SHA256; the fresh
capture is flushed, read back and compared without text conversion. All capture
handles close before profile creation. Missing, replaced, oversized or uncertain
evidence stops progression. These bytes describe what was generated, not proof
that cmd subsequently opened or executed the batch.

The original six-case and seventh command-line sentinel verdicts are reduced
independently, including after a later case, evidence-write or final-cleanup failure.
Sentinel success cannot repair an original failure. The full allocated and cleaned
path now has eleven case journals and one run journal; blocked or unprepared rows do
not invent case journals. Contained nonzero exits may complete cleanup while
their observations remain failed. Any ownership, capture, marker or cleanup
uncertainty retains recovery and prevents further launches.

## Minimal cmd batch delivery comparison

`cmd-batch-exit23` uses a fresh private copy of the same original cmd executable
bytes and the original `/d /q /c direct.cmd` route, with the same private workspace
current directory. Its batch contains exactly nine ASCII bytes, `exit 23` followed
by CRLF, with SHA256
`cab50bf1c23956b80d898c7af8f1c1e853e5bba6b14b8a2fbe4981d382fb7e8a`.
The original batch generator and command-line sentinel remain unchanged.

The new case has its own profile, root, case identity, evidence directory and
journal. Its separately bound capture adapter requires the actual source's exact
nine bytes and fixed hash, validated ordinary-file identities, byte-identical raw
destination readback and every confirmed close before profile/process creation.
Its copied executable hash must equal the original cmd case before assignment or
resume. All authority, stdio, deadline and cleanup gates remain the same.

An observed queried exit 23 means only that this minimal relative batch route
reached the expected builtin exit. It does not prove that the original batch was
opened, that any original operation succeeded, or that access was denied. Other
exits or timeout leave lookup, opening, parsing and batch initialization unresolved.
The new observation cannot change either earlier aggregate or earn script-entry,
mutation, runtime-support or network-denial credit. Overall evidence or cleanup
failure still retains the failed run journal.

The `/c` string remains the unquoted literal `direct.cmd`, and `/s` remains absent.
Microsoft's [cmd parsing rules](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd#remarks)
describe `/s` quote stripping; adding it would change this comparison. Plain
[`exit 23`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/exit)
terminates cmd with the supplied process exit code. The test adds no `/b`, `call`,
redirection or fallback command.

## Raw cwd and nine-byte read observations

The two appended cases are `cmd-cwd` with exactly `/d /q /c cd` and
`cmd-read-direct` with exactly `/d /q /c type direct.cmd`. Each receives a fresh
profile, workspace, PID and three regular stdio handles under the same unchanged
policy. Its cmd bytes must match the current run's original cmd case. These are
independent objects; the experiment does not claim the same token or directory.

After stop, drain and mandatory evidence capture, four bounded, non-inherited
read-only handles independently reread source/evidence stdout and stderr. Source
identities must equal the original stdio identities; evidence copies have their
own measured and rechecked identities. Every read and single-attempt close must
be confirmed. Cwd expects the exact ASCII workspace plus CRLF; non-ASCII cwd is
unsupported/inconclusive. TYPE independently expects exactly `exit 23\r\n` and
empty stderr, with queried exit zero. No BOM, newline or whitespace conversion
is allowed, and no code-page or shell-flag fallback exists.

These two case observations use `CmdCwdObserved`/`CmdReadObserved`, and run fields
`CmdCwdRawObservationMatched`/`CmdReadRawObservationMatched`. These facts can
remain true after later persistence or cleanup failure. They are never accepted
run verdicts. The pure `evaluate_cmd_observation_artifact` evaluator separately
derives `CmdCwdObservationPassed`/`CmdReadObservationPassed`, default false, from
trusted exact-source/run provenance, all raw bytes and stage-correct committed
case/run journals. A completed filename commits an unchanged `state=pending`
body; preconditions and favorable matrices alone cannot establish completion.
There is no producer accepted field or post-Resolve persistence action.

Run `python tests/windows-broker-direct/cmd-observations-audit.py` for the unified
source and synthetic artifact tests. Its seven local Python modules contain no
acquisition, network or OS lifecycle operation. Synthetic failure-shaped artifacts
cover case.json, matrices, run-root removal, final scans, selected-parent closes,
final writes and journal bind/verify/rename; they are not Windows fault injection.
The evaluator bounds and validates raw member hashes, exact schemas, journal
linkage and stage projections. Trust context must come from independent artifact
verification, never self-asserted receipt fields; hashes alone are not provenance.
Opaque legacy JSON contributes no prerequisite or accepted-result truth. Its bytes
are hash-verified only; semantic checks cover the parsed contributing receipts and
named wrappers, including rejection of new accepted-result fields.

The full allocated path is eleven case plus one run journals; actual profile, pin
and recovery-boundary counts must be read from that run. Scoped confirmation does
not assert universal CleanupConfirmed. All eight original observations and their
reducers stay independent. TYPE success proves a read of those bytes only; it is
not original batch execution or runtime support. Direct class46 failures and
TokenVerified=false remain; observed AppContainer/SID/zero-capability/LowIL and
AccessCheck signatures are surrogate observations. NetworkDenialProven remains
false and the original native/nested/runtime aggregate failures remain failures.

## Explicit-relative nine-byte batch observation

The eleventh case, `cmd-relative-batch-exit23`, uses exactly
`/d /q /c .\direct.cmd` with the same nine-byte `exit 23\r\n` payload and current-run
cmd executable bytes. It expects a queried exit23 and empty stdout/stderr. The
new case has its own independently verified profile, workspace, PID and regular
stdio handles; preparation, grants, environment, authority, deadline and cleanup
use the existing machinery. Empty output remains supported for a non-ASCII cwd.

The producer records only `CmdRelativeBatchExit23Observed` on the case and
`CmdRelativeBatchRawObservationMatched` on the run. The existing raw readers bind
all four stream handles and the captured minimal payload without conversion.
`ScriptEntryObserved` stays false because this batch has no entry marker. Late
cleanup or persistence failure can preserve raw facts, while accepted results
remain false until all eleven cases and their final journals validate.

The pure evaluator emits protocol `cmd-cwd-read-relative-batch-acceptance-v1` and
independently derives `CmdRelativeBatchObservationPassed`/`RelativeBatchStatus`.
It requires the explicit eleven-case schema; old ten-case artifacts use their
pinned `071d559` evaluator. A clean exit1 or output mismatch in the new case leaves
otherwise committed cwd/TYPE acceptance independent. Missing or inconsistent
proof rejects completion. The fixed descriptors have independent literal audits;
fixtures cannot confirm a shared descriptor mistake by using it as their only oracle.

The preceding [071d559 diagnostic run](https://github.com/Eswink/coding-tools-mcp/actions/runs/37096520158)
provided committed cwd/TYPE observations while both retained bare-name batches
still returned1 with empty streams. Its overall runtime workflow failed; the
accepted observations did not change those failures. This new case has no measured
Windows outcome until its exact candidate is run and its artifact is verified.

This tests path qualification only. Microsoft documents current-directory search
for a bare executable name and direct qualification when a backslash is present
([NeedCurrentDirectoryForExePathW](https://learn.microsoft.com/en-us/windows/win32/api/processenv/nf-processenv-needcurrentdirectoryforexepathw)).
Neither a changed result nor another exit1 establishes the failed internal
operation, an omitted search, a quoting defect, or a root-cause fix. No `/s`, `call`,
marker batch, chained command, fallback, capability or production admission is added.
The original native/nested/runtime failures and direct class46 failures remain.

## Independent AppLocker record observation

The diagnostic workflow brackets its unchanged pilot invocation with UTC and
monotonic timestamps. A separate observer in `tests/windows-applocker-observation`
queries only existing records in `Microsoft-Windows-AppLocker/MSI and Script` for
the explicit-relative case's exact recorded PID, generated `direct.cmd` path and
bounded invocation interval. Provider, IDs 8005/8006/8007, SCRIPT policy, PID, path
and both time bounds are conjoined in one service-side selector. Query tolerance
is disabled and batch size is one; at most two records are read. No policy, audit,
permission or logging setting is changed, and no broader query follows a miss.

The separate `evidence/applocker-observation` files contain the invocation bracket,
fixed status/reason, input/query hashes and at most one decision ID/time. They
contain no raw event XML, formatted message, user/rule details or new accepted
control fields. The summary is first created as observation-pending.json, fully
flushed and closed, then renamed without overwrite to observation.json as the last
observer persistence action. Pending evidence is retained after uncertainty;
review requires the final name and rejects pending, extra or conflicting siblings. The original pilot exception and native exit state are preserved;
the pilot's final journal action and every command/security helper remain unchanged.

An ID 8007 match describes a recorded AppLocker block; 8006 is audit would-block,
and 8005 records permission only. Exact PID/path/time correlation does not prove a
process creation instance, script entry or the cause of every exit 1. Logged paths
may use variables such as `%OSDRIVE%`, and delayed, absent, unavailable or malformed
records remain inconclusive. The read timeouts do not bound query construction or
rendering; the existing job deadline remains the outer limit.

The checkout step disables automatic LF-to-CRLF conversion only for that action,
so the immutable-source audit checks exact Git-blob bytes without changing global
or repository Git configuration.

Run `python tests/windows-applocker-observation/audit.py` for the new strict input,
query, source and synthetic artifact contracts. PowerShell 5.1 executes the
separate `contract-tests.ps1` scenarios without querying a real channel. These
fixtures are not real event evidence. The pure new evaluator requires independently
authenticated artifact identity and the unchanged old `RunCompletionValidated`
gate before reporting a reviewed match. Missing final journals or late persistence
failure remain inconclusive even when a raw event match survives. Old observation
verdicts continue to be derived separately by their unchanged evaluator.

Primary references: [Microsoft AppLocker event meanings](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/using-event-viewer-with-applocker),
[Microsoft's field selectors](https://github.com/microsoft/AaronLocker/blob/main/AaronLocker/Get-AppLockerEvents.ps1),
[event query subset](https://learn.microsoft.com/en-us/windows/win32/wes/consuming-events),
and [query error-tolerance behavior](https://learn.microsoft.com/en-us/windows/win32/api/winevt/ne-winevt-evt_query_flags).

## Explicit LocalApplicationData Temp selection

The current workflow invokes `run-pilot.ps1` with ten retained cases and one
explicit-relative batch observation, and the fixed
`localappdata_temp_ci_v1` parent policy. The wrapper and C# helper independently
resolve only `Environment.GetFolderPath(LocalApplicationData, DoNotVerify)` plus
the literal `Temp` child, require exact agreement and fresh unchanged owner/DACL
checks, and never choose an alternate parent. No existing ACL is changed.

A bounded lease opens only that directory's exact drive-root-to-leaf chain, at
most32 handles. Each ancestor requests FILE_READ_ATTRIBUTES|FILE_TRAVERSE
(0xA0); the endpoint keeps READ_CONTROL|FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES
(0x20081). All opens are noninheritable, OPEN_EXISTING, share-read only and
OPEN_REPARSE_POINT|BACKUP_SEMANTICS. Root-to-leaf acquisition and each recovery
guard recheck same-handle identities, volume, directory type, final paths and
absence of reparse points. The endpoint also rechecks its unchanged strict DACL.
No ancestor is enumerated, and the target HANDLE_LIST remains exactly its three
fresh private stdio handles.

FILE_TRAVERSE's0x20 bit participates in the documented sharing algorithm;
FILE_READ_ATTRIBUTES alone would not pin deletion/rename. Attribute-only writes
are not universally excluded by sharing. The directory reparse-set contract
requires an empty directory, while each held nonterminal ancestor contains its
pinned next child; the endpoint has the separate strict write-trust check. This
is bounded ordinary-directory reasoning, not protection against arbitrary
privileged OS operations. See Microsoft's
[sharing algorithm](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/8c0e3f4f-0729-49f4-a14d-7f7add593819)
and [reparse-set contract](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/4aeefef8-92c3-4abc-af7a-a610caf8a165).

Every existing recovery boundary includes the exact selected Temp namespace as
well as evidence and the retained RUNNER_TEMP/GetTempPath control roots. Immediate
metadata enumeration rejects hidden, wrong-type, duplicate, reparse or unknown
markers, then recurses only through existing diagnostic-name families and evidence.
Unrelated Temp subtrees are never traversed. The depth32/100000-entry limits remain.
A short lease protects pre-allocation checks. After the run journal exists, a
long lease remains held through all eleven cases and owned-root removal. Any failed
scan, metadata check or uncertain close stops progression and retains recovery.

The final recovery scan and independent reverse single-attempt pin closes precede
final evidence and immutable cleanup-precondition writes. No selected-namespace
operation occurs afterward; unchanged journal verification and no-replace rename
remain the final required C# actions. A completed journal additionally covers these
metadata handles, while listener/preparation/upload outcomes remain separate.
The selected-parent and cmd-sentinel audits enforce the complete executable union, exact
new sources, partial-class loading boundaries and effective negative mutations.
New managed tests inject all operations and do not exercise Windows APIs locally.
Windows compilation, actual pin acquisition and any runtime results require the
next exact CI run; the original20 failed nested rows remain required.

## Retained read-only parent observation

The preserved `run-parent-candidates.ps1` entry point observes exactly
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
required/preserved. The selected pilot above was separately reviewed for fresh
checks and that exact recovery namespace. `parent-candidate-audit.py` enforces the
exhaustive union of all preserved and new C#/PowerShell sources; its managed tests
exercise pure observation gates, not Windows compatibility.

## Explicit observed-token pilot

`run-pilot.ps1` selects only the CI policy `accesscheck_signature_v1_ci`. The same
invocation first checks a suspended ordinary-AppContainer native control and proves
that its actual identification-token signature is rejected as LPAC. It then checks
and resumes the unchanged LPAC native reference, followed by exactly Node, cmd,
Windows PowerShell, pwsh, the two earlier cmd exit comparisons, cwd/TYPE and the
explicit-relative batch. Every target's own suspended primary token must pass
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

The completed journal commits only the eight required case outcomes, any subject/
profile scopes actually created, the disposable run root and selected-parent metadata
handles. Preparation evidence,
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
cleanup mutations. The selected-parent audit enforces exhaustive union
coverage together with all preserved source pins. Portable audits do not execute
Windows APIs; C# compilation and the real paired matrix remain distinct CI stages.

Primary implementation reference: Chromium
[CheckLpacToken](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/sandbox/win/src/app_container_test.cc#109),
[identification duplication](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/base/win/access_token.cc#211),
and [AccessCheck wrapper](https://chromium.googlesource.com/chromium/src/+/a1fa952ac0a8487e1b9c77fbdd856af78f2116ff/base/win/security_descriptor.cc#437).
Microsoft documents [DuplicateTokenEx](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-duplicatetokenex)
and [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck).
