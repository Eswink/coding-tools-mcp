# Iteration 18: preserve Windows path namespaces before release

Parent: `832b8c49584e2e31ddbd3e4da7f1a41deeaf6621`, tree `f12af338b1fdfdf8776c92e89f3fff082d3f6019`.

## Recovered evidence

The exact parent passes OAuth regression run `34686356193` and strict native run `34686356572`. The latter includes Windows debug and installed NSIS real-window acceptance plus both Ubuntu versions with DEB and AppImage. These are CI fixture results, not authenticated ChatGPT or public ingress acceptance. The source artifact was downloaded and its SHA-256 checked against the API; the reconstructed local tracked tree equals the recorded source tree.

## Deterministic defect and repair

The old `windows_command_path` removed every verbatim prefix. A canonical UNC path consequently became a relative path beginning with `UNC`, and device/volume namespaces were similarly reinterpreted. Convert a verbatim UNC prefix to an ordinary UNC root, retain the existing absolute drive-letter conversion, and preserve other namespaces. Handle ASCII case-insensitive UNC and non-ASCII unrecognized prefixes without slicing at invalid UTF-8 boundaries. This is a lexical correction, not a guarantee that cmd supports UNC working directories or that an SMB server is accessible.

Primary specification: https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation and https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file .

Manual upstream review: `windows_command_path` feeds `platform_command_path`, the PowerShell script wrapper and `windows_batch_command_line`, which feed direct and managed command startup. Risk MEDIUM; authorization, executable policy, stdin lifecycle, production timeout defaults and shell creation flags are unchanged. No unrelated file is edited. Native MCP/graph tools are not exposed; plugin discovery found no applicable connection. Exact-version offline MCP installation and GitNexus invocation both failed with ENOTCACHED. This is a documented manual fallback, not a claimed graph-tool success.

## Failure-first verification

Six Windows unit tests cover network roots, local drives, ordinary/relative paths, device namespaces, Unicode prefix safety, and the actual cwd/script-wrapper callers. CI runs them against the parent's unchanged implementation with only the test-module declaration appended, requires a real UNC assertion failure, restores the exact candidate, and runs them again. Existing initial-stdin failure-first checks and full Rust/native gates are retained. Five additional fixed repetitions run the existing Windows CMD/PowerShell/Python test with its original assertions and 30-second budget; no retry-to-green or timeout increase is used.

The prior no-input PowerShell timeout remains an independently observed intermittent issue without a proven root cause. It is explicitly disclosed in the version-matched release guide. A passing stress run cannot be represented as its root-cause fix.

At preparation: local frontend 124/124 passed. Rust and native execution are pending the exact candidate's CI. Self-review 92/100, CI admission only. The final user request authorizes dual-platform publication after gates pass; no stable-release or blanket bug-free claim is permitted.
