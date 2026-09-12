# Iteration 14: remove the skipped-native-validation gap

Verified versioned parent: `83da7383756a6198b51f9600168268a9883f27be`.
Verified source tree: `d7157d3f2afdffc80f0d21071730936e3da18848`.

The version preparation run `34684388936` completed successfully. Its source archive outer and inner digests were checked, all six application version fields report 0.3.2, and all five changed files match independently regenerated output from the existing version helper. Reconstructing every tracked path produced the exact remote tree above. Dependency versions and unrelated files are unchanged.

## Failure and impact

The reusable native validation workflow accepted several exact historical branches but not `fix/oauth-discovery-runtime`. A caller on the repair branch would therefore skip its source job and dependent validation jobs. A green or skipped wrapper would not establish native acceptance. The new contract reproduces this gap: **four pass, one fails** before the allowlist repair.

The fix adds only the exact repository-scoped repair ref to that allowlist. No wildcard is introduced. The legacy Windows waiver remains restricted to its old local-acceptance branch. A read-only wrapper calls both existing validation and installer workflows with `windows_local: false`, after exact-source, six-field version, source archive and helper-contract checks. The installed matrix remains Ubuntu 22.04/24.04 times DEB/AppImage, plus real Windows NSIS installation.

Manual impact review: workflow dispatch reachability, required-job dependencies, source provenance and installed artifact validation. Risk is HIGH because skipped native validation can create a false completion claim. This change does not alter application behavior, native harness assertions, security checks, or publication code. Unavailable MCP/GitNexus tools remain disclosed in the preceding iteration record; their execution is not claimed.

## Local evidence and review

After repair: **5/5** new native-entry contracts, **99/99** existing authorization helper contracts, **19/19** release contracts, and **124/124** full frontend regressions pass. Both changed/new workflows parse as YAML. `git diff --check` passes. These are source/helper tests, not actual installed UI acceptance.

The earlier product-fix run `34684140665` completed all five jobs successfully, including Windows/Linux full Rust and frontend gates. Native installers for this exact 0.3.2 source are still pending execution. No merge, release or overall-complete decision is implied.

Scoped self-review: **94/100**, eligible to run strict native CI, not a substitute for its outcome.
