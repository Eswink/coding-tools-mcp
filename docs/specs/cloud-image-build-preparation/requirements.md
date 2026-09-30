# 需求文档：cloud-image-build-preparation
## 功能概述
Add missing #40 image build preparation without weakening runtime or deployment boundaries.
## 范围边界
Image recipe, CI job, native fixture helper, unit tests and gap documentation. No production bind change or Compose readiness claim.
## 依赖关系
Exact successful standalone cloud release artifact from same run; final product version and full integration gates.
## 非功能需求
Only official digest-pinned base; no embedded credentials; no registry push; no production host/ACL changes.
## 需求列表
### FR-1: Exact image input
The gate SHALL build only the verified same-run four-binary archive with source/product labels and a resolved immutable official Ubuntu22 base digest.
### FR-2: Non-root runtime
The gate SHALL verify actual UID65532, read-only rootfs, all capabilities dropped, no-new-privileges, bounded resources and no networking for image CLI tests.
### FR-3: Protected file fixture
The gate SHALL mutate only a freshly generated two-file fixture, verify private config acceptance, secret-file read reaching invalid synthetic input, and exact readable-file rejection. No credentials are generated or supplied.
### FR-4: Truthful build artifacts
The gate SHALL save the image archive, image ID, base digest, source and test receipts without registry publication, port binding or service deployment.
### FR-5: Remaining deployment gaps
The report SHALL preserve unsupported CentOS8/liveVPS blockers and identify unimplemented executable Compose ingress/config-loader mapping as engineering work, not as a completed template.
