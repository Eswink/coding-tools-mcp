# Requirements: cooperative FINAL archive budget
## 功能概述
Carry the existing activation controls through owned FINAL ZIP and cloud-tar validation.
## 历史经验与坑
PR137 supplies a shared checksum helper. Archive work can still continue between download/checksum checkpoints; stream ownership must precede new callbacks.
## 术语定义
Budget means the original absolute deadline and identical check_active callback. A cooperative checkpoint rejects late success without interrupting a synchronous call.
## 范围边界
Two runtime files, finite source admission and real parser/worker tests. Receipt parsing, Git, metadata, later contracts/copies and global publication eligibility remain outside scope.
## 需求列表
### FR-1: Preserve one budget across FINAL archive work (Must)
As the owner, I need archive work to observe the same activation controls.
WHEN validating FINAL ZIP and cloud tar THEN the system SHALL pass the original deadline/callback through parser loops, bounded reads/decompression, copies, EOF/close and cloud hashes without renewal.
WHEN controls are omitted THEN the system SHALL preserve old no-keyword calls, bytes/results, error behavior and no clock reads.
WHEN stdlib work finishes late THEN the system SHALL reject at its next supported checkpoint without claiming interruption inside that call.
### FR-2: Preserve error order and stream ownership (Must)
As the owner, I need cancellation without leaked newly acquired streams.
WHEN a stream is acquired THEN the system SHALL enter its close scope before polling a callback.
WHEN an operation establishes invalid content THEN the system SHALL preserve its diagnostic before that operation's post-success budget check, retaining existing close-error precedence.
WHEN failure already exists THEN the system SHALL perform no budget poll from failed unwind or finally.
WHEN staging unwinds THEN the system SHALL retain existing root/API lifetime, one-shot retirement and sticky cleanup uncertainty, with no transition/mutation.
### FR-3: Bind exact finite source after PR137 integration (Must)
As the maintainer, I need actual baseline identity and unchanged historical behavior.
WHEN final source admission or publication begins THEN the system SHALL bind actual merged PR137 F and verify its complete tree equals the reviewed provisional D tree; unknown/different F blocks those actions.
WHEN selecting D2[F], I2[F,D2] or J2[R,I2] THEN the system SHALL verify exact parents/trees, five whole-byte inverses, eight prior identities and the four pinned R documents.
IF selected or historical content is invalid THEN the system SHALL terminate without fallback or mutable candidate caching.
### FR-4: Exercise real parser boundaries and regressions (Must)
As the maintainer, I need source-bound actual outcomes.
WHEN validating this change THEN the system SHALL preserve old1376/strict303/consumer452 IDs and add exactly15 runtime plus12 composition cases.
WHEN checking inverse negatives THEN the system SHALL prove both the exact lower checksum fragment diagnostic in an isolated test and unpatched outer rejection.
WHEN publisher engineering CI runs THEN the system SHALL execute219 unique cases on Ubuntu22/24 with source/ID receipts before integration.
## 非功能需求
NFR-1: Exactly12 paths,5 replacements,7 additions;1783 entries over verified F. Per-file≤500, sum delta ceilings1866, aggregate1900.
NFR-2: Reuse unchanged IO helper, modes, limits, owners and error vocabulary; no deletion, supervisor/Git/authority change or new dependency.
NFR-3: ZipExtFile second-pass internals and other synchronous operations remain non-preemptible; no hard parser/full-bundle/native/security or live-release claim.
## 依赖关系
PR137 integrated normally after fresh explicit retry approval; retain that history and do not reuse it for unrelated held actions. Reuse existing archive, checksum and real-worker fixtures.
## 检查清单
FR-1–FR-4 require actual F binding, exact design/source review, mandatory repository gates and real current-candidate tests; local isolated-D runtime preparation may proceed after exact review, without refs or CI.
