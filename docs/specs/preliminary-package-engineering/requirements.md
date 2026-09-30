# 需求文档：preliminary-package-engineering
## 功能概述
Reuse existing Windows/Linux installer workflows for exact-source engineering diagnostics before final release decisions.
## 范围边界
Two existing workflows only, plus this specification. Final RC gates, installers and native assertions unchanged.
## 依赖关系
Current committed six-field0.6.0-rc.4 source; final version decision remains pending and independent.
## 非功能需求
No release/tag/publication, no sandbox weakening, no accepted claim for raw builds.
## 需求列表
### FR-1: Bounded trigger
The workflows SHALL add only ci/preliminary-packages-* to their existing push branches and preserve explicit dispatch support.
### FR-2: Reproducible tool/source preparation
The workflows SHALL pin Rust1.98.1, Windows2025 and source-only Rust caches; normalize checkout line endings and retain exactSHA/version checks.
### FR-3: Existing acceptance unchanged
The workflows SHALL retain all full Rust, raw startup, installed native and privacy assertions; Linux installed execution uses the supported system Python PATH without broadening sandbox policy.
### FR-4: Diagnostic artifact truth
The workflows SHALL upload a separate unverified build artifact before installed acceptance, marked NOT_FINAL and NOT_PUBLISHABLE with sourceSHA/version/tree and package hashes. Accepted native artifacts remain separately labelled engineering-only.
### FR-5: No release inference
The workflows SHALL never choose the next version or relax final-rc integration/security/audit gates. CurrentRC4 artifacts are disposable engineering evidence only.

Parent review addition: required Rust regression remains a failing step and keeps the workflow red. Only independently successful source/frontend prerequisites permit diagnostic package build. Native smoke may continue only from verified build/driver outcomes; no continue-on-error. Linux regression uses private D-Bus/Secret Service and system Python. Failure-propagation tests cover these conditions.
