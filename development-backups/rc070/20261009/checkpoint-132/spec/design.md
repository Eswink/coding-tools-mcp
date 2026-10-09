# Design

## 概述
对应需求：FR-1、FR-2、FR-3。One standalone Python source module plus ordinary controls and three spec documents. No original source is modified.

## 文件结构
collector.py, ordinary_controls.py, spec/{requirements,design,tasks}.md, safe source/controls status and manifest. Only root later runs exact compiler argv after a distinct runtime/startup review.

## 技术方案
Use a prelinked ordinary holder, Popen(new session, stdin DEVNULL, stdout PIPE, stderr PIPE), nonblocking descriptors and selector. Each read calculates shared remaining byte capacity before writing to corresponding exclusive raw file; overflow sets partial flag, retains prefix and original error, then initiates cleanup. Never merge stderr into JSON stdout. Reserve4s within the fixed maximum480s. True returned child provides process group context; integer PID is not accepted as owner input. Separate TERM2/KILL2 bounded wait phases and mandatory descriptor/selector/file closes preserve original exceptions. after_fence and final monotonic check run independently even after primary failure. Unknown holders remain strongly reachable; success requires exact native0, both EOF, no primary/cleanup/guard errors, raw cap, all closes and whole deadline. No native-family proof is minted. File reads or Python callbacks can block outside enforceable async interruption; deadline-late or unknown completion fails and cannot become PASS.

Root compiler additionally seals current2033/lockf1789/toolchain/system support/config leases, fresh target, exact env/argv and independent startup. This source never resolves tools through PATH, builds or parses native Cargo events. Ordinary controls exercise real Python processes and explicitly labelled mock effect/cancel paths. Public freeze includes source and safe status only.
