# 设计文档：rc070-product-metadata

## 概述
FR-1 through FR-3 extend existing release metadata contracts without modifying production validators or application symbols.

## 技术方案
FR-1: replace only uniquely anchored own-version tokens in the seven authoritative files. Root npm lock has two fields. The gateway is the product authority for its four binaries and serverInfo; cloud-agent/local-agent remain independent 0.1.0 libraries. Update only the two existing engineering RC_VERSION constants.

FR-2: extend the existing Python test module while retaining both original tests and historical/stable fixtures. Synthetic tests cover every desktop field, gateway manifest/self-lock/product mismatch, independent components and byte-preserving transitions. A read-only test helper compares current files with exact Git blobs at the pinned baseline after only the expected own-version token replacements; unrelated dependency/checksum/whitespace changes fail. CI explicitly fetches that baseline, runs full locked metadata without --no-deps, and builds the gateway binaries. Their complete version output must include the existing capability suffix and correct binary identity; Windows uses .exe. Separate step outcomes and always-uploaded evidence preserve partial failures.

FR-3: the guide is ENGINEERING ONLY, prefreeze, unreserved and not a final release receipt. A future final guide must be in the reviewed-source manifest; any later guide/source edit invalidates that freeze.

## 数据模型
Existing version formats and evidence schemas remain unchanged. Transition evidence records baseline SHA, product version, per-file original/current SHA256 and unchanged independent files. Hosted evidence adds exact source SHA/tree, run ID/attempt, OS and tool versions. No runtime configuration, authorization or protocol model changes.

## API 设计
Production APIs are unchanged. Test-only transition verification accepts a root, exact baseline commit and expected RC version, reads Git blobs/current files and returns evidence or raises on mismatch; it never writes metadata.

## 文件结构
Seven metadata files: package.json, package-lock.json, src-tauri/Cargo.toml, src-tauri/Cargo.lock, src-tauri/tauri.conf.json, services/cloud-gateway/Cargo.toml and services/cloud-gateway/Cargo.lock.
Two existing workflows: .github/workflows/linux-rc-packages.yml and .github/workflows/windows-rc-packages.yml.
Tests: scripts/rc_version_gate_tests.py. New validation: .github/workflows/rc-product-version-validation.yml. New guide: docs/releases/verification-v0.7.0-rc.1.md. Three scoped specifications in this directory.

## 设计决策与风险评估
Fresh GitNexus reports LOW and zero upstream callers/flows for the modified test class/methods. The unchanged RC version reader has 29 upstream symbols/two flows and the cloud reader 22 symbols, both raw LOW. The repository's greater-than-15-symbol rubric makes the wider release-contract review surface HIGH. The user was notified before edits and an independent design review approved this bounded approach. Production readers/consumers are not edited.

## 测试策略
Run focused mutation/byte-transition and existing release contract suites; actionlint all affected workflows. Run real npm ci/check/build/full frontend regressions locally and on the three hosted OSes. Local Cargo is unavailable; only hosted full metadata and actual four-binary version results establish Cargo/build proof. Verify release_preflight only as release-inputs-only, first without a clean-source claim and again on the committed source. Hosted artifacts and clean-source receipts must match the exact new head; no earlier source pass is inherited.
