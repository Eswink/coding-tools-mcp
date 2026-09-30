# Separate broker-direct LPAC pilot

This is a CI-only comparison of direct process creation by the native broker. The
20 required nested Rust-child rows and all original native foundation files remain
byte-identical. Their failures continue to fail the job. Nothing here is a
production fallback, a release acceptance reduction, or a Python packaging change.

## Boundary and order

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
