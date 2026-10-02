# 子规格：Immutable source and exact engineering producer evidence

## 精确源码组件
- PR96: 43cc4fcfcee45b65be6faa79c33fedc3dce2407c; tree 3ddac4a2aacb718a9113b31eb0513713f5c525bb; parent e2a0e08fe490a18f9aa60efc400b60c9dbe22c89
- PR93: bd3053eca83cb0fcc07468abb3b81bf6fada1bcf; tree a12999503397d7ad13e8f1ec198b3c84c17e484a; parent 171e8e87b735800a629049ddc35c563f748f73f2
- PR94: e26e36aedb7db7458adbf17ec5185b998e5641f7; tree 51c00c50e05b4c2cf5fb25029bbe8a4f380fdf95; same parent 171e8e87b735800a629049ddc35c563f748f73f2
- First merge parents must be PR96+PR93 with tree 7355b842eb2b266de8da4424f30c9d0e2b11bc31; second parents must be that compliant first merge+PR94 with tree 4e55549810e74236e14eb28a48785c3268ae107d
- Frozen compliant anchor: 049ff5d381f345bf681ac3501b952269531b7045, with first merge c959ef5e6e9913ccb5eeb3139e7d7ecb72358378 and the exact parent/tree constraints above. Both source merges completed the staged review gates before commit. Do not move this anchor for corrections

The connected Git-data transport created the remote object identities above using its default commit metadata, preserving exact trees and ordered parents. Pre-publication local equivalents 2139a7aefb811ca2c219c1dffc2db88f38c0abdf (assembly) and 3c1914cdc149b80528c07564fed3e8fcd78d646c (first merge) remain historical validation provenance only; they are not accepted runtime anchors. No branch publication or release approval follows from object creation.

## 范围
Exact reviewed component ancestry, two correctly gated source merges, one immutable compliant assembly anchor, bounded linear descendant scope, and exact producer identity.

## 需求回链
- FR-1
- FR-2

## 验收标准（EARS）
1. WHEN compliant source merges are proposed THEN the gate SHALL require exact PR96/PR93/PR94 parents and trees from the parent requirements.md and subspecs/source-evidence/spec.md; unreviewed assembly merges SHALL be rejected as approved anchors.
2. WHEN an implementation or authorized correction is checked THEN the gate SHALL allow 1–32 one-parent descendants from the fixed compliant anchor, require the exact published first descendant 46f88c60f3a5f8726e4c28cee73e941a7f15a36d/tree1412f9e1408b1dbb7beefa2db37f70b5965fea65 with exactly fourteen added files plus one modified helper, and require exactly fifteen added files plus that modified helper at every subsequent descendant, preserve all other blobs/modes, and record each SHA/parent/tree/delta blob. The additional file SHALL be scripts/rc_source_assembly_dispatch_tests.py and SHALL never be dropped in a later descendant. No other fifteen-path predecessor or optional fifteen/sixteen-path choice is accepted. It SHALL reject any forged legacy identity/tree, merged/foreign descendant, reverted intermediate forbidden edit, missing path, symlink, mode change, anchor movement or forced history rewrite.
3. WHEN a follow-up push occurs THEN GitHub before SHALL be the validated prior branch head on this chain and an ancestor of actual HEAD; forced=true SHALL reject. Initial all-zero before SHALL only be used for initial branch creation verified independently against published history. An approved append-only correction SHALL pass without moving/rebasing the anchor.
4. WHEN the assembly producer is used THEN it SHALL match exactly Eswink/coding-tools-mcp/.github/workflows/rc-source-assembly.yml@refs/heads/ci/rc-source-assembly-v2-20261001 plus actual repo/ref/push event/GitHubActions/source/workflow SHA/run/attempt, explicit root and source invariants. collect SHALL require actual job capture; verify SHALL operate as actual job verify without spoofing. Legacy exact tuple/rejection behavior SHALL remain unchanged.
5. WHEN producer identity, source, receipt digest, parent chain or artifact is tampered THEN collect and independent verify SHALL both fail. Raw RSA/yank and every original engineering test SHALL remain preserved.

## 涉及文件
scripts/rc_source_assembly.py; scripts/engineering_dependency_capture.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py; scripts/rc_source_assembly_dispatch_tests.py.

## 不做项
No PR89/schema/PR97 stack, Windows security driver, Issue86 opened-root binding, consumer malformed-redirect cleanup, runtime production edits, secrets, security weakening, main/canonical advancement, tag or Release. Preserve every original workflow/guard/test/lock/payload. No held-action retry.

## 设计要点
Use producer(sha,root=None) with legacy-compatible default; only exact new tuple requires root/source gate. No arbitrary workflow input, wildcard, opt-out or CI monkeypatch. The source gate receives real checked-out root and verifies immutable Git data; the reviewing maintainer independently approves actual final/correction SHAs.
