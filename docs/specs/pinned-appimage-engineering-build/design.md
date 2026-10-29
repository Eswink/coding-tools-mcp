# 设计文档：pinned-appimage-engineering-build

## 概述
Covers FR-1 through FR-6. Baseline M has1,698 entries. Seven additions and four replacements produce1,705 entries. Add a build helper used directly by existing Linux engineering CI; retain application and existing package acceptance code.

## 技术方案
Python3 standard library coordinates existing /usr/bin/curl and verifies owned files. No new dependency or executable tool is committed.
Flow: exact source/prerequisites -> focused cases -> full Rust regression -> five inert originals -> verified separate cache -> existing project hook and Tauri build -> tool post-check -> existing package verifier/upload -> four installed jobs.
The original workflow permits diagnostic packages after regression failure; that condition remains exact and is not completion evidence.

### Tool identities
- linuxdeploy182515537:13,264,064 bytes, SHA256e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef, first-observed digest
- plugin602435573:16,488,952 bytes, SHA25649d6a17160675a6bd1781699aae6bdf7692d98552e02a3671d2183d10547842e, API digest
- runtime596078161:944,632 bytes, SHA256156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074, API digest
- GTK commitdda522bce37387f1b853d9095713bfaa924c8423:14,622 bytes, SHA2567804c9eef13e59bf2783aad9882ef9db8f3f3f9e8d631874b1d348d550a3693f
- GStreamer commit2a2e67491c32995a3f279ad0ecbe77abd512b42a:4,857 bytes, SHA256c107b49d84edbffc6ab226ed1007e0626a4f7aa2c3a36b7782bef62351d49e94
Script URLs use exact commits. Release names remain upstream mutable, so bytes must match the frozen pins.
Static plugin inspection: embedded ELF SHA25658d3047a420e1dfa365ef0ad495b728b56627803cb6b75ed816b7a4fa9713720, build ID08f1037c357794a97308b3720e9daf48259dfe29, observed version8c8c91f. This is not reproducible build proof.

### Acquisition and ownership
Use a fresh original directory under RUNNER_TEMP and a fresh .tauri leaf under actual cargo metadata target_directory. Keep the normal Cargo target so existing package paths stay correct. Reject symlink parents, leaf links, hardlinks, preexisting outputs and unbounded data.
Curl ignores user configuration and receives an explicit PATH/locale-only environment with no inherited proxy, CA, credential or loader overrides. It uses HTTPS with normal certificate/name checks, no auth/netrc/config, at most3 redirects and an allowed final host. Parent subprocess timeouts enforce60s/file and300s total; child RLIMIT_FSIZE enforces exact output ceilings. Successful HTTP200, exact length and SHA are mandatory. No retries or optional fallback.
Originals are nonexecutable. Only separate verified cache copies receive executable mode. Failure leaves no successful readiness receipt and prevents Tauri invocation.

### Normalization and runtime
Cache names are linuxdeploy-x86_64.AppImage, linuxdeploy-plugin-gtk.sh, linuxdeploy-plugin-gstreamer.sh and linuxdeploy-plugin-appimage.AppImage.
Normalize only the linuxdeploy copy's marker bytes8..10 to zero before build; expected SHA25620eebde3c18ae2e44279bd624fc72482503aece216d5d77f10932235342f71c1. Tauri's own identical write is then idempotent.
LDAI_RUNTIME_FILE points to the verified original runtime. Prepare does not stage AppRun. Before verification requires no AppRun; the existing beforeBundleCommand installs the project launcher. After verification requires that exact launcher and unchanged selected tool bytes.

## 数据模型
Preparation/post-check records contain source SHA/tree, phase, fixed pin/provenance fields, observed sizes/digests and original/cache paths. Source identity uses explicit isolated --git-dir/--work-tree calls with ambient GIT variables removed and separate tracked worktree/index checks. Expected ignored/untracked build outputs are allowed; global worktree cleanliness is not claimed. Engineering-only flags remain false for security/release/publication approval. Records do not claim atomic filesystem or hostile same-user isolation guarantees.

## API 设计
- prepare(root, target_directory, directory, source, output): verify source, acquire fixed originals, stage verified cache and emit readiness only on complete success
- verify(root, target_directory, directory, source, phase, output): independently check originals/cache/runtime environment and launcher state before/after build
- CLI exposes only prepare/verify with fixed manifest and no user-selectable tool URL/hash
- Finite admission module owns topology, pins, exact inverses and canonical guard inventory; production has no result cache

## 文件结构
Final-line / added+deleted caps:
| Path | Caps |
|---|---|
| scripts/appimage_tools.py |450/450|
| scripts/appimage_tools_tests.py |450/450|
| docs/specs/pinned-appimage-engineering-build/requirements.md |125/125|
| docs/specs/pinned-appimage-engineering-build/design.md |200/200|
| docs/specs/pinned-appimage-engineering-build/tasks.md |125/125|
| .github/workflows/linux-rc-packages.yml |300/100|
| scripts/rc_pretag_publication_profile.py |500/14|
| scripts/rc_pretag_publication_adapters.py |250/4|
| scripts/rc_pretag_snapshot_warning_cases.py |450/24|
| scripts/rc_pretag_appimage_profile.py |300/300|
| scripts/rc_pretag_appimage_cases.py |480/480|
Aggregate changed lines must not exceed2200.

## 设计决策
### Reuse actual native workflow (FR-4)
Keep triggers, permissions, concurrency, timeouts, every original job/step/condition and existing test/build/package commands. Add fetch-depth0 to build checkout, helper20/guard20/warning20 prerequisite commands, and tool prepare/pre/post verification around the existing Tauri command. Existing branch prefix already matches ci/preliminary-packages-appimage-feeaf299.

### Closed admission with historical inverses (FR-5)
M parents are6edd4e6137a6947319183b3ac8801bfa608ac722 and851f3374871f6303b37ec7c7055936e6d74ecc1c. Admit D[M], I[M,D], J[R,I] only. Preserve R and its four document pins.
The new module pins every changed path except its own externally reviewed bytes. Publication selected_profile adds a small dispatch before warning adoption. It catches only topology mismatch; selected-content failure stays terminal.
Existing inverse_warning_adapter pre-normalizes the new exact delta. Warning cases add only one import and four read-normalization fragments. Exact inverses recover complete M profile/adapter/warning bytes, methods and assertions. Other historical source stays unchanged.
Only fixture-local exact immutable-M validation may be reused after a successful fresh read, with exact root/callback/argument checks and copied results. First-case fresh history and every altered candidate remain verified.

## 测试策略
FR-1/2/3/6:20 canonical AppImageToolsTests verify manifest/provenance, bounded curl arguments, status/host/failure/timeout/short/overflow/hash denial, fresh ownership, exact marker transformation, originals/cache, runtime and launcher phases.
FR-4/5:20 AppImageCompositionTests verify anchors/parents/trees, exact pins/budgets, inverses/terminal errors, unchanged workflow/jobs, existing775 IDs and disjoint new40. Existing preliminary package contracts remain unchanged.
Local D/I/J each run all815 named cases. Existing hosted strict303/contracts755/consumer452 remain unchanged; native prerequisites run new40 and existing warning20. Native full Rust counts are measured, never inferred from parser inventory. Actual Ubuntu22/24 installed jobs remain required.
Fresh staged GitNexus, independent source review, exact manifest/gencommit and actual remote tree/run/artifact checks precede completion.

## 风险评估
- Executable supply-chain input: fixed HTTPS sources, exact bytes, normal TLS, no fallback; linuxdeploy upstream-digest gap remains explicit
- Mutable upstream releases: exact pins fail on changed bytes
- Cache changes and source drift: fresh directory plus before/after verification; no hostile same-user atomicity claim
- Existing workflow runtime cost: retain timeouts and observe actual runs, do not skip tests
- Historical composition regression: exact inverses and full old inventories
- Linux success misreported as release: keep engineering-only and unresolved Windows/security/FINAL gates explicit

## 检查清单
- [x] All FRs mapped to actual workflow/helper/profile behavior
- [x] Exact inputs, source paths and bounds specified
- [x] Existing launcher and package acceptance preserved
- [ ] Final implementation and native evidence meet the contract
