# 设计文档：preliminary-package-engineering
## 概述
Minimal reuse of linux-rc-packages.yml and windows-rc-packages.yml; no duplicate packaging pipeline.
## 技术方案
FR-1: add one bounded branch pattern; existing branch and dispatch retained.
FR-2: exact Rust/action/runners and cache-targets=false; six-field source identity remains hardcoded to committedRC4.
FR-3: leave existing native test/install scripts unchanged; only pin system Python for Linux acceptance as in final packaging workflow.
FR-4: Windows copies raw NSIS plus an explicit unverified identity/hash receipt before driver/install stage. Linux existing build artifact gets an engineering marker; all artifact names include NOT_FINAL-NOT_PUBLISHABLE andsourceSHA.
FR-5: no publish job or content-write permission; final RC workflow untouched.
## 文件结构
Two existing workflows and three spec files. No new production helper or runtime changes.
## 数据模型
Engineering receipt has sourceSHA/tree/currentversion, raw installer SHA256/size, accepted=false, publish_approved=false. Native acceptance still creates its own strict receipt.
## 测试策略
Actionlint, unchanged RC/native contract suites, diff verification that every existing assertion remains. Actual installers run in GHA after parent publishes trigger branch.
## 风险与决策
A successful raw build is not an installed pass or Windows isolation proof. Final selected version must be rebuilt later.

Parent review addition: required Rust regression remains a failing step and keeps the workflow red. Only independently successful source/frontend prerequisites permit diagnostic package build. Native smoke may continue only from verified build/driver outcomes; no continue-on-error. Linux regression uses private D-Bus/Secret Service and system Python. Failure-propagation tests cover these conditions.
