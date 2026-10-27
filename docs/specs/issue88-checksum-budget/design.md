# Design: cooperative checksum budget
## 概述
M=39a9ae7e2761f419db5cace712368e5671042b5e; tree=ecf7792ca9911d969ac223227c819fbb8ef70fe7.
M parents are 981d7b23af1c5c8174352c4564aa65b1557cc546 and 9d9f5d9ee1bad13b825fd8ac1f114a578122af2a.
This is one checksum-phase capability, with three call layers and finite historical source admission.
## 技术方案
### FR-1: Original controls and checkpoints
_verify_bundle_bytes keeps its current signature and budget dictionary, forwarding it to verify_checksum_inventory.
verify_checksum_inventory and hash_file add optional keyword-only deadline=None and check_active=None.
One private _check_budget helper in IO uses existing math and a time import, with no transport cycle or new owner.
Omitted controls return without clock access; inventory calls hash_file with empty kwargs when controls are absent.
Accept only builtin int or finite builtin float deadlines; reject bool/subclasses/nonfinite values. Compare huge integers directly, without conversion or arithmetic.
The deadline is not reset, clamped or converted into a new duration. Callback-only checking never reads a clock.
Check before and after successful callbacks, before root inventory/read work, after successful reads, at every row, before coverage and each file hash, and before successful return.
Hash checks precede opening and every64KiB read, follow reads including EOF, and follow successful stream close before returning the digest.
Preserve total-size/FILE_LIMIT rejection before digest acceptance; do not poll after an established content/I/O error or from finally.
### FR-2: Fixed failures and retained owners
Callback success is exactly None. Map exact builtin-string cancelled/timeout to existing transport_cancelled/transport_deadline_exceeded; other callback failures become artifact_transport_failed.
Read exception code once, reject hostile/non-string/subclass values and raise fresh fixed exceptions outside handlers. SystemExit becomes SystemExit(1); KeyboardInterrupt is recreated without arguments.
An expired deadline wins before callback invocation; callback failure wins over expiry crossed inside that failed callback, as in the existing downloader.
No checksum helper owns or retires roots. Existing open_file nofollow/single-link/size rules and PrivateRoot retention remain.
Existing stage/session mappings retain cancelled/none or timeout/none only after reliable disposal; cleanup uncertainty still overrides as adapter_error/none.
Two download children have retired before checksum work; tests prove this and one-shot six-root/API disposal. No file deletion is added.
### FR-3: Complete source inverses
Seven modified paths reverse to complete M bytes, including one ownership source operand, seven staging-case operands and one import.
The staging profile delegates selection and normalization to one checksum profile. Only topology mismatch delegates; selected/historical content errors remain terminal.
Exactly three paths have six pinned historical passthrough identities; no broad historical allowance or self-authorizing source pin.
D has sole parent M; I ordered parents[M,D] and tree(D); J parents[R,I] with exactly four pinned R documents over I.
Full candidate tree independently binds the profile; every other scoped source has exact mode/blob/SHA256/size/line pins.
### FR-4: Real verification
Twelve runtime cases use real on-disk multi-chunk files and unchanged publisher fixtures; no inherited TestCase duplicates.
For real stage composition, append valid bounded JSON whitespace to the packaging report before fixture checksum/archive metadata creation, then use the actual validators.
Observe cancellation/expiry after actual chunk2 and EOF, original controls, two distinct exited/reaped children, unchanged receipts/handles, no transition/mutation and sticky disposal failures.
Twelve composition cases preserve all old IDs/assertion bodies and exercise inverses, finite pins, caps, exact topology and exceptional inventory rejection.
Candidate1376; actual I/local J each1037; publisher192. Hosted reuse requires exact source/setup/command/inventory joins and truthful composed-coverage labels.
Focused/source review precedes draft CI; independent full local validation may run alongside hosted jobs. Every required gate precedes integration.
## 文件结构
Tasks lists exactly13 paths and final/delta caps. Runtime changes stay in consumer, archive and IO; no publication-stage/executor change.
## Security and limits
Global eligibility and authentic bundle_bytes/native/security gates remain blocked. Caller fixture authority is never production authority.
Synchronous filesystem work, root walks, text split, ZIP/tar/JSON/TOML parsing, source/Git subprocesses, later copies/hashes and metadata calls are not globally bounded by this increment.
No supervisor expansion, process-tree promise, owned deletion, live release/main/tag action, credential/protection change, held PR98 payload/ref or snapshot change.
