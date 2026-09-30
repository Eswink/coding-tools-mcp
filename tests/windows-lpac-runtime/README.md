# Windows zero-capability LPAC runtime diagnostic

This is an isolated CI investigation, not a production sandbox implementation.
It does not change `NativeToolHost.prepare`, `SANDBOX_REQUIRED`, the release
matrix, runtime capabilities, trusted roots, existing installation ACLs, or any
registry/security setting. Run only in the dedicated GitHub Actions workflow.

## Retained evidence and source

The three files in `baseline/` are byte-for-byte recoveries from
[`7dc2aed2082932ca2822265f4ec455f2292d3714`](https://github.com/Eswink/coding-tools-mcp/commit/7dc2aed2082932ca2822265f4ec455f2292d3714):

| Recovered file | Original repository path | Git blob SHA |
| --- | --- | --- |
| `NativeLauncher.cs` | `tests/windows-sandbox/NativeLauncher.cs` | `4d26f231eac08a4f2ea0e565c0ea22cccbfa8c43` |
| `run.ps1` | `tests/windows-sandbox/run.ps1` | `1359d68f0c47cbd402b614e82afd6d31ab67d906` |
| `windows_sandbox_fixture.rs` | `services/local-agent/src/bin/windows_sandbox_fixture.rs` | `003f1cd970ebb7b0e28d2f33e99cba50f0f39274` |

Retained run: [36695185909](https://github.com/Eswink/coding-tools-mcp/actions/runs/36695185909),
artifact `11088250421`. That run established LPAC process startup and the
pre-network filesystem assertions. It failed at `WSAStartup(10107)`, encoded
as fixture exit `15107`, before the socket assertion. An initialization failure
is not successful network-denial evidence. Broad `registryRead` necessity was
not established by the retained fixed-key open diagnostics.

`audit.py` pins SHA-256 for all recovered files and compares both adapted sources
against exact, enumerated transformations of that baseline. Its mutation tests
reject capability changes, LPAC opt-out removal, ACL expansion, native failure
laundering, and ignored workflow failures. The diagnostic has its own Cargo
manifest/lock; no production dependency manifest is edited.

## Execution and differences

1. Run the unmodified baseline first, including its unsandboxed *native fixture*
   positive control, ordinary AppContainer outside-AAP-read witness, LPAC modes,
   token checks, filesystem canaries, network assertions, and cleanup. Its
   failure remains a failed workflow step. No language runtime is warmed up.
2. Copy the runner's Python 3.12 and Node 22 installations, npm shim, Git,
   Windows PowerShell, PowerShell 7, and cmd into disposable fixture storage.
   Read file-version metadata/npm package metadata and hash every copied file;
   no version command or runtime initialization is used for preparation.
3. For each fixed case, the adapted launcher copies just that runtime beneath
   a new fixture code root whose path includes a space, exercising cmd quoting.
   Only the original private package ACLs are applied:
   code read/execute, workspace modify, outside-canary AAP read/execute. No
   host-installation/system/registry ACL changes occur. Reparse points fail.
4. The launcher preserves zero capabilities, LPAC opt-out, suspended creation,
   no inherited host handles, job assignment before resume, original environment
   creation requirements, termination, and zero-active-process verification.
   Only the runtime adapter permits a 45-second fixture wait (baseline stays
   15 seconds); each child has a 30-second deadline. Evidence is collected after
   confirmed job drain, including outer timeouts, before deleting owned files.
5. The augmented Rust fixture adds exactly one bounded offline observation
   after the original pre-network checks and before the original registry/DLL
   diagnostics, `WSAStartup`, and socket test. Those original assertions and
   failure exits are unchanged. Its child inherits the LPAC process/job and
   uses private output files, HOME/profile/cache/TEMP directories and a fixed
   PATH. The stdout handles originate *inside* the LPAC fixture, not from the
   unsandboxed host. No token, inherited host handle or trust bypass is added.
6. Each case records real spawn result/raw exit, full fixed argv, timeout,
   exact stdout comparison, required workspace mutation/readback, and the
   launcher job-drain result. Original outside canaries are checked again.
   Any completed native receipt containing a false assertion stops the matrix.

## Bounded case matrix

| Case | Positive evidence required |
| --- | --- |
| `python-budget` | Exact existing `-c print('budget')` command exits 0 and prints `budget`; this name refers to the blocked regression payload, not a timeout test |
| `python-workspace` | Isolated Python writes/reads a private file, exits 0, prints exact marker |
| `node-workspace` | Node built-in `fs` writes/reads the private file, exits 0, prints exact marker |
| `npm-cmd` | The actual copied `.cmd` shim and its Node child perform offline `npm pkg set` and `pkg get`; require exact output and changed package JSON |
| `git-local` | Copied Git initializes a synthetic local repo and writes a known blob; require the exact blob hash and object file |
| `cmd-workspace` | Copied cmd writes/reads its private file and emits exact marker |
| `powershell-workspace` | Copied Windows PowerShell inline command writes/reads its private file and emits exact marker |
| `pwsh-workspace` | Copied PowerShell 7 runs the same inline operation separately |

These are observations of the exact hashed binaries and copied distributions,
not support claims for an entire version range. A nonzero exit, spawn error,
missing runtime or deadline expiration is retained as a failed observation;
deadline expiration alone does not establish intrinsic incompatibility.

## Reading outcomes honestly

- `offline_passed` requires successful process exit, exact output, its required
  mutation, parent fixture filesystem checks, and confirmed job drain
- `network_denial_proven` is separate and requires all five original native
  assertions. `exit=15107` remains `winsock_initialization_failed_10107`, never
  connectivity denial. A true offline row cannot override a failed native step
- Parent fixture canaries are explicitly labeled. Runtime-child-specific
  outside access/token assertions are not independently measured by this probe
- This does not cover production gate integration, workspace ACL lifecycle,
  ConPTY, npm lifecycle/build scripts, every Python module/Unicode/session
  contract, deliberate timeout/descendant test cases, or `.ps1` routing parity
  (production currently uses `-ExecutionPolicy Bypass`; this probe does not)
- Expected on the retained environment: foundation stays red at LPAC WinSock
  initialization. Python/cmd/Git/PowerShell results are unknown until CI; Node/npm
  may fail during runtime initialization, which must be observed rather than
  inferred from the prior `SANDBOX_REQUIRED` failures
- Even an all-positive offline matrix leaves all production and full RC gates
  unchanged. No new Windows sandbox support is declared here

Current source anchors: `.github/workflows/dot-rc-integration.yml` (Windows-2025,
Node 22, Python 3.12, Rust 1.98.1); `src-tauri/src/tools/exec.rs` (direct argv and
Windows script routing); `src-tauri/src/tools/execution_sandbox.rs` and
`docs/releases/final-rc-gates.md` (fail-closed production boundary).

## Local versus Windows validation

Portable checks are `python tests/windows-lpac-runtime/audit.py`, actionlint,
Cargo formatting, and Linux host checking/clippy for the standalone crate.
Those host Rust checks do not compile or execute `cfg(windows)` bodies. The
workflow performs locked Windows compilation/clippy followed by the actual
native matrix. No Windows runtime result is claimed before that run completes.
