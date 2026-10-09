# Design

## 概述

Corresponding requirements: FR-1, FR-2, FR-3, FR-4, FR-5. Finite source correction, no native activation.

## 技术方案

A NativeRawBudget owns perchannel saved and reserved quantities and combined remaining capacity. Reserve before issuing a read; OVERLAPPED owns its immutable submitted bytes. Native completion releases reservation and accounts actual transferred count; pending/UNKNOWN never releases. At exactcap with no EOF, refuse newread and use existing independent cancellation/job/close machinery, producing FAIL. Git gives the collector a stage total from the actual remaining shared source counter. This bounds both live submitted capacity and savedbytes, rather than merely measuring overflow after writing.

ZIP metadata is fully inspected before extraction, with new finite entry/expanded/member resource limits; officialarchive compatibility is unmeasured. Exact pinned archive identity is checked twice. Each actual member/output is opened, held, read/written in bounded chunks, independently closed exactly once, and quarantined on close no-return. Archive is independently closed after any member error. All error/cancel objects preserve identity. Real WinAPI controls are still required for the collector's budget/EOF/cancel behavior; ordinary Python ledger tests prove only arithmetic/source logic.

Runtime root lstat reparse checks supplement leaf checks. Receipt exclusive open replaces exists/write_text; exact stream holder is retained if actual close cannot be observed returning. Afterclose actual time checks reject a late return; they do not imply arbitrary syscalls can be interrupted or provide atomic filesystem ownership. Keep tripleDISABLED and all immutable originals.

## 文件结构

Existing six management files only; original seven/v12/nine design files and cp88 source freeze remain unchanged. Work-only spec/controls and subsequent source mirror are separate metadata.
