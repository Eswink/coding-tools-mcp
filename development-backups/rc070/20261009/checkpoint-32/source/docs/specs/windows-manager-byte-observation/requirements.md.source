# Requirements: finite manager source-byte observation

## 功能概述
Observe the seven original public management source files without changing or authorizing them. Actual run37916193914 failed Windows manager admission before restoration. Its artifact contains no actual workflow bytes/hash/counts, so CRLF cause is UNKNOWN.

## 需求列表
### FR-1 Fixed public source identity
WHEN an observation runs, it SHALL require the real management HEAD equal to GITHUB_SHA and read only the seven literal existing verify_manager source names. It SHALL record expected native Git blob, byte length, SHA256, LF/CRLF counts and actual raw byte length, SHA256, framed Git blob OID, LF/CRLF counts. It SHALL reject symlink, nonregular/missing files and files over2MiB without reading arbitrary contents; diagnostic JSON stays below32KiB. No source bytes or environment/config/host data are serialized.
### FR-2 Explicit diagnostic comparison
WHEN raw bytes differ, the diagnostic SHALL record raw equality and whether CRLF-to-LF transformation alone equals expected Git bytes, plus exact expected-LF-to-CRLF equality. These observations SHALL NOT change admission; inferred Git config remains UNKNOWN even if byte transformation matches. Byte normalization SHALL be comparison-only.
### FR-3 Preserve delegate and failure evidence
WHEN a non-cancellation before/after observation fails, its error SHALL be recorded without skipping or replacing original verify_manager admission/rejection. WHEN Before observation is cancelled, new admission/restoration/compilation SHALL stop; only the original required finally cleanup SHALL run, with no new After observer child. WHEN After observation is cancelled, it SHALL occur after the original manager-after check and before the original runtime-after loop, preserve its typed cancellation until the original receipt is written, then propagate it. WHEN both an original primary failure and an observation cancellation exist, an AggregateException SHALL retain both original exception objects; cancellation SHALL not replace the original error receipt. Existing strict raw blob verifier function SHALL remain exact original AST. Existing whole1953 manifest, source restores, original data vectors, tool/action pins, permissions and45minute budget SHALL remain unchanged. A failed observation SHALL prevent carrier final PASS, while the original delegate error remains separately preserved.
### FR-4 Necessary ordinary controls and independent review
WHEN validating this increment, it SHALL run real owned-file/native-Git controls for exact LF, CRLF, arbitrary mutation, missing/symlink/oversize, wrong HEAD and observation failure versus original raw admission; no fake CI, native VM, source compiler or owner launches. Fresh checkout-specific impact and independent source peer precede committing and parent-only push. Original a20 FAIL and35daff FAIL receipts remain immutable. Diagnostic success is never compiler or RC qualification.

## 非功能需求
Read only fixed public paths. No source rewrite, budget expansion, private values, token or runtime-package collection. Only bounded hash/count metadata is retained.

## Acceptance Criteria
- [ ] FR-1 seven-source raw metadata correct with fixed Git identity and bounded public JSON.
- [ ] FR-2 CRLF-specific observations do not admit changed raw source.
- [ ] FR-3 original verify_manager AST and strict failure semantics remain intact.
- [ ] FR-4 ordinary controls, isolated impact, independent peer and source-only frozen backup recorded; real CI observation remains separate.

## 依赖关系
Existing exact Git management commit, pinned Python action and original source guard. WHEN the Git identity or fixed public input is invalid, the observation SHALL fail without granting admission. WHEN observation fails, the original delegate SHALL still run and determine its own error.
