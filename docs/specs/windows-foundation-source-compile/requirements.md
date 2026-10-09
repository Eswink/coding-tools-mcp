# Requirements: Windows foundation source compile

## 功能概述
A management-only temporary CI carrier validates independently reconstructed frozen source. It cannot authorize VM execution or qualify an RC.

## 需求列表
### FR-1 Exact source restoration
Restore D6 c60f9667fa8431e27fabbc497c19b4abfef5b965 plus independently verified 73 payloads to d4bd2d9813176afd83270ba39971d3204e350105 /1913 then SHA-verified full43 patch to 19bb292004e0fd4ed02374b35bcd2f22469779f0 /1953. Validate path, mode, blob, bytes and SHA before compiler. Management seven files remain outside SUT.
### FR-2 Actual compiler and data tests
Windows2025 runs Rust1.98.1 whole library test no-run then only fixed data families; Ubuntu24.04 runs Go1.24.13 explicit five-file std-only tests. Raw exit codes and source before/after hashes survive failures.
### FR-3 Safety and provenance
No HCS/VM/privilege/nativefixture or user machine effects. No Stage11, no credentials persisted, no arbitrary source/path input, fixed backup commits, action pins and temporary branch. Protected positive SHA and three scopes preserved. Native tests NOTRUN and RC still BLOCKED.
### FR-4 Guard validation
Locally test source restoration and corrupted source/patch rejection without compiler installation. Source leases distinguish manager commit, backup commit and pure SUT tree; never embed manager SHA as candidate native source.

## 非功能需求
Fail closed on every mismatched byte and unexpected path/mode; outputs bounded to compiler logs and sanitized receipts. Runtime timeout 45 minutes; read-only repository permissions.

## Acceptance Criteria
- [ ] FR-1 trees/counts and complete worktree digest verified.
- [ ] FR-2 actual GitHub compiler logs and explicit data results retrieved.
- [ ] FR-3 native execution absent, protected positive bytes unchanged.
- [ ] FR-4 actual local good/bad guard tests; detect_changes/gencommit before management commit.

## 依赖关系

Immutable exact73 and full43 backups, native Git, pinned compiler Actions. WHEN a mismatch occurs, the guard SHALL refuse compiler execution. WHEN compiler fails, logs SHALL preserve actual failure and candidate SHALL remain BLOCKED.

## Frozen01 peer-review delta (FR-1, FR-3, FR-4)
WHEN a probe runs, it SHALL verify all seven management source blobs/modes against actual HEAD equal to GITHUB_SHA before and after compilation. WHEN Rust proxies resolve payloads, it SHALL bind actual rustup which --toolchain1.98.1 rustc/cargo payload paths/SHA before and after alongside proxy hashes. Git SHALL have empty system/global configuration, disabled hooks/replacements, and its executable pinned before first restoration. Immutable backup commits/prefixes SHALL match literal approved47adc/155e leases. Frozen01 is prelaunch blocked; these fixes need fresh source-only02 and necessary guard tests before actual CI.
