# Issue #59 — Native PTY tasks

## 交付物清单

1. 通过 check_spec 的 requirements/design/tasks。
2. PTY common API/lifecycle。
3. Unix PTY backend。
4. Windows ConPTY backend。
5. Minimal process-tree ownership seams。
6. PTY fixture 与双平台 regression tests。
7. GitNexus pre-edit/detect evidence。
8. Windows 2025 + Ubuntu 24.04 CI artifacts、SHA-256、rollback。
9. Converged delegated Plan 与 manifest verified receipt。

## 任务列表

### TASK-1 Pre-edit evidence
- Resume Plan。
- 对 process_tree.rs::spawn、Windows process-tree startup/Job symbols、lib.rs export surface 和任何拟修改 existing symbol 做 pinned GitNexus context/impact。
- HIGH/CRITICAL 时停止 production edit 并 review。
- 记录 baseline revision 与 source line counts。
- 覆盖 NFR-5、NFR-6。

### TASK-2 Common PTY model
- 新增 pty.rs 与 pty_io.rs。
- 实现 bounded PtySpec、PtySize、session/outcome/termination/capacity/output。
- 不注册公开 Tool。
- 覆盖 FR-3、FR-4、FR-7、FR-8、NFR-1..4。

### TASK-3 Unix backend
- 新增 pty_unix.rs。
- native PTY allocate、winsize、setsid/controlling terminal、explicit env/cwd/argv、owned PGID、resize。
- 仅增加必要 process-tree seam。
- 覆盖 FR-1、FR-2、FR-6、FR-7。

### TASK-4 Windows backend
- 新增 pty_windows.rs。
- Direct ConPTY + STARTUPINFOEXW + CREATE_SUSPENDED。
- Job Object before resume，exact process/thread handles。
- ResizePseudoConsole 和 deterministic partial-failure cleanup。
- 覆盖 FR-1、FR-2、FR-5、FR-7。

### TASK-5 Fixture and regressions
- 新增 src/bin/pty_fixture.rs 与 tests/pty_runtime.rs。
- 覆盖 terminal presence、Unicode/byte echo、resize、timeout、cancel、overflow、capacity、drop、grandchild cleanup、Windows quoting、Debug redaction。
- 覆盖 FR-8、FR-9、NFR-3。

### TASK-6 Candidate verification
- rustfmt 仅 scoped PTY/local-Agent files。
- candidate-file Clippy zero errors。
- Windows 2025 / Ubuntu 24.04 focused PTY tests。
- complete local-Agent tests/check。
- staged GitNexus detect 非 false-clean。
- all changed/new source files <500 lines。
- 记录 exact SHA-256。
- 覆盖 FR-9、NFR-4、NFR-5。

### TASK-7 Review and delivery
- heartbeat implement/test evidence。
- Plan-aware code_review，处理 HIGH/CRITICAL。
- converge Plan。
- fresh-read remote feature，fast-forward/no-force-push。
- official published Windows/Ubuntu CI。
- manifest only from real evidence。
- close #59 only after published native evidence。
- 覆盖 NFR-6。

## 需求覆盖矩阵

| Requirement | Tasks |
|---|---|
| FR-1 | TASK-3, TASK-4, TASK-5 |
| FR-2 | TASK-3, TASK-4, TASK-5 |
| FR-3 | TASK-2, TASK-5 |
| FR-4 | TASK-2, TASK-5 |
| FR-5 | TASK-4, TASK-5 |
| FR-6 | TASK-3, TASK-5 |
| FR-7 | TASK-2, TASK-3, TASK-4, TASK-5 |
| FR-8 | TASK-2, TASK-5 |
| FR-9 | TASK-5, TASK-6 |
| NFR-1 | TASK-2, TASK-7 |
| NFR-2 | TASK-2, TASK-3, TASK-4 |
| NFR-3 | TASK-2, TASK-5 |
| NFR-4 | TASK-2, TASK-3, TASK-4, TASK-5, TASK-6 |
| NFR-5 | TASK-1, TASK-6 |
| NFR-6 | TASK-6, TASK-7 |

## 文件变更清单

### Planned new files
- services/local-agent/src/pty.rs
- services/local-agent/src/pty_io.rs
- services/local-agent/src/pty_unix.rs
- services/local-agent/src/pty_windows.rs
- services/local-agent/src/bin/pty_fixture.rs
- services/local-agent/tests/pty_runtime.rs

### Planned modified files
- services/local-agent/src/lib.rs
- services/local-agent/src/process_tree.rs
- services/local-agent/src/process_tree_windows.rs
- services/local-agent/Cargo.toml
- services/local-agent/Cargo.lock only if Cargo feature resolution changes

### Explicit non-goals
- No sandbox implementation。
- No Hooks/policy expansion。
- No worktree/snapshot changes。
- No cloud authority、UI、installer、package release。
- No persisted PTY/no-replay queue。
- No public Tool registration。

## 验证顺序

1. check_spec。
2. estimate。
3. pre-edit GitNexus impact。
4. implementation。
5. focused tests。
6. full local-Agent tests/check。
7. staged detect_changes。
8. Plan review/converge。
9. fast-forward publish。
10. official published CI + manifest evidence。
