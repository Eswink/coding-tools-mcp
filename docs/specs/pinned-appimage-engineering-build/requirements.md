# 需求文档：pinned-appimage-engineering-build

## 功能概述
Build current Linux engineering DEB and AppImage packages with reviewed, checksum-pinned tool bytes and run the existing Ubuntu 22.04/24.04 installed tests. This increment adds preparation used by the real build. Engineering version remains 0.6.0-rc.4; successful Linux evidence does not satisfy Windows, security, FINAL or publication gates.

## 历史经验与坑（来自记忆库）
No remote memory was used. Current source and independently downloaded bytes are the basis. The previous metadata HTTP403 cause remains unknown; current official downloads succeeded. The old five-file acquisition packet was not recovered. New acquisition independently matched its retained sizes. The separately acquired stock AppRun is comparison data: the project beforeBundleCommand installs its own launcher before Tauri's fallback.

## 术语定义
- M: feeaf299df6c3729285c91511ece18e9984a2503, tree81abcfdbe1bea9ab3a0baae252d4ad86db8b15c5
- D: sole-parent-M reviewed candidate; I: ordered [M,D] feature merge; J: ordered [R,I] release-context synthetic
- Original: inert downloaded tool bytes; cache copy: separately staged tool permitted to run in engineering CI
- Pin: source URL/identity, exact length and SHA256, with upstream-digest versus first-observed provenance distinguished

## 范围边界
In scope: five-tool preparation, focused tests, exact existing Linux workflow amendment, three specs, finite source admission and exact historical inverses.
Out of scope: application/Windows/snapshot implementation, ten held86b531 paths, PR98 ref or correction, dependencies/versions/credentials/security settings, main/release/FINAL/tag/Release/publication activation.

## 需求列表
### FR-1: Exact bounded acquisition
**优先级:** Must
**用户故事:** As a build maintainer, I need exact official tool inputs so mutable upstream release names cannot silently change the build.
#### 验收标准（EARS）
1. WHEN preparation starts THEN it SHALL acquire exactly the five frozen inputs totaling30,717,127 bytes and verify individual sizes/SHA256 before any executable cache copy.
2. IF TLS, HTTP status, final host, timeout, size or digest verification fails THEN preparation SHALL terminate without retry or fallback.
3. WHEN receipts describe linuxdeploy THEN they SHALL label its SHA256 first-observed because the official asset API digest was null.
4. WHILE downloading THE helper SHALL use fixed public HTTPS URLs, normal TLS, no credentials/config/netrc, at most3 HTTPS redirects,60 seconds per file and300 seconds total.

### FR-2: Separate originals and exact normalization
**优先级:** Must
**用户故事:** As a reviewer, I need preserved original bytes and an explicit cache transformation.
#### 验收标准（EARS）
1. WHEN preparing tools THEN the helper SHALL require fresh owned original/cache directories, reject linked parents/files and hardlinked inputs, and create no archive paths.
2. WHEN staging linuxdeploy THEN only offsets8 through10 SHALL change from414902 to000000, yielding SHA25620eebde3c18ae2e44279bd624fc72482503aece216d5d77f10932235342f71c1.
3. WHEN before/after checks run THEN all originals SHALL retain exact pins and nonexecutable modes; cache files SHALL match their exact expected names/content/modes.
4. IF any tool is absent, extra, linked or changed THEN the build SHALL fail before successful package upload.

### FR-3: Project launcher and explicit runtime
**优先级:** Must
**用户故事:** As a desktop user, I need the existing reviewed launcher and runtime behavior preserved.
#### 验收标准（EARS）
1. WHEN staging tools THEN the helper SHALL not install stock AppRun; the unchanged project hook SHALL remain responsible for AppRun-x86_64.
2. WHEN post-build verification runs THEN cached AppRun SHALL equal the1,319-byte project launcher SHA256726a50e47cdbc011f6eef6bcf655e1e2eec236f6750cadaff170a8f74c202c2c.
3. WHEN Tauri invokes the AppImage plugin THEN LDAI_RUNTIME_FILE SHALL name the exact verified local runtime; implicit runtime download is not the selected path.

### FR-4: Actual build and installed regressions
**优先级:** Must
**用户故事:** As the release engineer, I need real package results rather than another detached validator.
#### 验收标准（EARS）
1. WHEN native CI runs THEN existing frontend/source prerequisites, full Rust regression, DEB+AppImage build, driver and all four Ubuntu22/24 installed jobs SHALL remain enabled.
2. IF full regression fails but engineering package prerequisites pass THEN existing diagnostic-build behavior SHALL remain, while the overall required regression failure stays visible.
3. WHEN the amended package step runs THEN it SHALL prepare and verify tools before the existing Tauri command and verify them again before existing package verification/upload.
4. WHEN historical guard tests run THEN only the build checkout SHALL gain fetch-depth0; branch triggers, permissions, timeouts and installed checkout behavior SHALL remain unchanged.

### FR-5: Closed source admission and preserved cases
**优先级:** Must
**用户故事:** As a source reviewer, I need the new engineering delta admitted without broad ancestry or historical weakening.
#### 验收标准（EARS）
1. WHEN selecting a candidate THEN admission SHALL accept only D[M], I[M,D] with the complete D tree, or J[R,I] with exactly four existing pinned R documents.
2. IF selected content fails THEN failure SHALL remain terminal; no historical fallback, correction chain, alternate anchor, unlisted path or budget overflow is accepted.
3. WHEN historical adapters are normalized THEN exact-once inverses SHALL recover complete M bytes and preserve all historical method/assertion inventories.
4. WHEN validation completes THEN old775 plus helper20 and guard20 SHALL remain815 distinct canonical IDs, with no missing/duplicate/unknown/skip/expected-failure cases.

### FR-6: Evidence and authority boundaries
**优先级:** Must
**用户故事:** As a maintainer, I need results bound to actual source and bytes with honest limits.
#### 验收标准（EARS）
1. WHEN recording preparation/build receipts THEN source SHA/tree, original/cache digests and actual results SHALL identify this candidate.
2. WHEN reporting embedded appimagetool identity THEN its observed SHA/version SHALL not imply reproducible source-to-binary equivalence.
3. WHILE this engineering workflow runs THE system SHALL not create tags/releases, enable FINAL, alter held refs or infer security/release approval.

## 非功能需求
- NFR-1: Existing workflow65/35 minute timeouts stay unchanged; observe actual timing before any amendment.
- NFR-2: Maximum source-file length500; eleven paths and aggregate changed-line cap2200.
- NFR-3: Linux amd64 build tools only, normal TLS, bounded curl subprocess output and no credential transmission.
- NFR-4: Fresh immutable baseline validation in production; any test-only baseline cache excludes mutable/custom/candidate calls.

## 依赖关系
Existing linux-rc-packages workflow, package/installed validators, project AppRun hook, Tauri CLI2.11.4, fixed official tool assets, exact historical composition and R documents. Windows/security/FINAL blockers remain independent.

## 检查清单
- [x] Current source and acquisition provenance reconciled
- [x] Requirements have stable IDs, priorities and measurable failure behavior
- [x] Scope and existing hold boundaries explicit
- [ ] Actual candidate implementation, native build and installed results verified
