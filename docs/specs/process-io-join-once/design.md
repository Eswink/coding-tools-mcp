# Design: take each joined process I/O handle once (#103)

## 概述

FR-1..FR-5 reuse the reviewed PR104 correction on immutable M 9c5c031d24aadc5d704160bb5a5a65bff126c10c, tree dafa6aa8dce10cf396971329244aeb8ac36d4ed3. Sequential await consumes a JoinHandle result; the original timeout branch retains and awaits that handle a second time if a later task is pending. The cause is ownership bookkeeping, independent of native process/Job completion.

## 技术方案

Wrap stdout, stderr and stdin JoinHandles in Options. A private helper awaits a borrowed present handle, removes it immediately after receiving Result, then maps JoinError to false as before. The readers future preserves stdout/stderr/stdin order. On unchanged READER_WAIT expiry, first abort every remaining Option, then await only remaining handles. Return the original default IoCompletion with exactly three false Boolean fields. No join-proof field or outcome-classification change is introduced.

Move the original ProcessManager::start and read_bounded/IoCompletion/join_io/take_stream/confirm_group_exit definitions mechanically to process_supervisor.rs. Keep the public types in process.rs; only helper visibility and test imports support existing tests. Move the original inline unit tests, including their nested ErrorAfterData implementation, to process_tests.rs without changing tokens or assertions. Preserve all existing process/PTY/group tests and process-tree implementations byte-for-byte. Verify extraction against M; review join_io separately. All changed source files remain at most500lines.

## 测试与基线证据

One process_io_join_tests.rs contains exactly four tests: stdout ready with stderr pending; both readers ready with stdin pending; panicked stdout and cancelled stderr consumed before pending stdin; all-pending timeout control. Each asserts the same original all-false timeout result. Tests run under a named io_join_tests module, directly below process in the baseline and below supervisor in the candidate. Filtering uses the shared module name; no duplicate or rewritten baseline bodies.

CI uses a separate runner-temp worktree at immutable M with its exact tree pinned with line-ending conversion disabled. It checks the canonical production Git blob, reads and hashes the exact production prefix, appends only the cfg(test) module declaration, copies the same test bytes and verifies the exact overlay. Build the baseline library tests successfully before running the four tests with one test thread. The gate requires the three exact named FAILED results, repeated-poll panic in each named failure block, one control ok and the exact1passed/3failed/0ignored summary. Raw failure logs are reproduced baseline failures, not passed production tests.

Then the candidate checkout runs fmt, locked all-target Clippy -Dwarnings, full test inventory, full locked --no-fail-fast tests, and locked all-target check. Parse exact positive test inventory/result counts and reject failures, ignores, filters or missing new tests. Preserve source/tree/toolchain and raw logs for both Windows2025 and Ubuntu24.04. Never substitute tree-sitter syntax or baseline instrumentation for actual candidate validation.

## 风险与边界

Fresh exact graph sees join_io -> ProcessManager::start -> run/process_runtime tests, but Rust reexports can hide broader callers. Independent HIGH/manual review covers supervisor publication, capacity/cancellation and NativeToolHost consumers. Only join ownership changes semantically. No Windows completion APIs, Job methods, process launch, sandbox/authority, PTY, dependency or original timeout-budget change. The external Windows feature remains blocked separately.

## 集成准入（FR-5）

Use the existing publication selector and isolated Git reader. Add only D=[M], I=[M,D] with the whole D tree, and J=[R,I] with the four existing frozen R documents. Validate exact M commit/tree/parents through the historical publication path. Resolve mutable refs once; catch topology mismatch only during selection, then treat any content error as terminal. Preserve old C/I/J shapes and historical pin maps. Bind sixteen non-self changed paths using independent mode/blob/SHA256/bytes/lines pins and bind the profile itself in the independently reviewed external full-tree manifest.

Exactly seventeen paths differ from M, adding eight entries for 1693 total. The aggregate changed-line cap is 2400; all remaining modes/blobs match M. In particular, all ten held assembly paths, other local-agent files, ownership tests and both pretag workflows are unchanged. The cancelled assembly correction is not part of this adoption.

Mechanically extract the old publication_tests lines19-85 block into rc_pretag_publication_adapters.py. Preserve its historical bodies and re-export names; the existing inverse_adapter API first restores complete M bytes, then applies the historical inverse. Old fixtures and guard pins read frozen M bytes, never the new working tree. Separately inverse the new profile section/dispatch and publication-test extraction to exact M bytes, retaining method IDs and assertion AST multisets. The historical missing/duplicate-fragment negative test first restores current adapter bytes to exact M and invokes the mechanically preserved M-to-N inverse, so all original fragment mutations and assertions remain meaningful; current-to-M mutation coverage is separate.

The test fixture reuses one verified immutable M map only for its captured root, callable identities, release/tree and independently copied document values, returns fresh copies, and delegates changed contexts, callbacks, kwargs and errors; every candidate/budget check stays fresh, while anchor, historical-failure and mutable-ref selected() tests stay uncached.

The same integrated inventory runner registers one new JoinOnceCompositionTests class with exactly twenty frozen IDs. Original283 SHA2568c511a659163f2e88a60246b95f9fbf077efde6d1679f28814ca014a48b3a907 remains; new20 SHA256ef9d08cd31005ec4a23fb4a3326d1257997815846641ff694ec2bfe7b2f21535 gives303 SHA2560ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125. All old452 remain (digestd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372). Existing strict/contracts workflow commands and twenty-minute budgets are unchanged.

## 原生工作流与证据限制

The donor native workflow changes only two lines (new push branch fix/process-io-join-once-m9c5c031 and BASELINE=M) and adds the M tree constant/assertion. Its exact inverse recovers donor blob89602b2cb8508326f08eba6c96e6523d869caf70. Four Rust files and the four regression bodies remain exact donor blobs. Fresh source-bound Windows/Ubuntu validation is mandatory; historical run37208085202 remains donor-only evidence.

Test the actual embedded witness/positive parsers with fixtures, retaining their actual guarantees and limitations. The positive parser compares listed/executed names and all four regression IDs but accepts matching duplicate ordinary names. Independent artifact reconciliation must reject duplicates, missing/extra expected tests and any source/tree/hash mismatch before native completion. Source identity and successful-baseline-build conditions are workflow/provenance checks, not properties of a text parser.

## 文件结构

Runtime/source caps (final lines / changed lines): process.rs450/392; process_supervisor.rs316/316; process_tests.rs81/81; process_io_join_tests.rs40/40; local-agent-runtime.yml243/196. The three process-io-join-once specs have caps90/90,110/110,90/90 for requirements/design/tasks.

Composition caps: rc_pretag_composition_tests.py500/8; desktop_tests400/12; nginx_tests480/12; two_hop_tests500/14; authenticated_two_hop_tests500/14; publication_profile400/180; publication_tests500/190; publication_adapters240/240; join_once_tests500/500 (all under scripts/rc_pretag_ prefix). These nine paths plus the eight runtime/workflow/spec paths are the complete scope. No other path or cap expansion is implicit. Tool evidence stays outside committed source.
