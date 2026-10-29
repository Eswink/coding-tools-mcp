# 设计文档：cloud-image-build-preparation
## 概述
Add an image job after accepted cloud binary process tests; consume same-run archive.
## 技术方案
FR-1: runtime Dockerfile uses required BASE_IMAGE digest, copies only verified binaries/manifest/readme, labels source/version.
FR-2: Docker USER65532 and test docker run flags enforce no network/read-only/capdrop; inspect and actual id confirm user.
FR-3: hosted-CI-only helper creates own temp config and intentionally invalid noncredential JSON. Private ownership/mode mutation uses only these two new files; exact public error codes distinguish file gate from parse gate.
FR-4: docker save local artifact, SHA256, no push/login. Existing Compose2.27/Nginx config tests remain separate syntax proof.
FR-5: deployment audit explains binary loopback-only bind versus obsolete0.0.0.0 blueprint and unsupported _FILE env contract. No bind relaxation.
## 数据模型
Image receipt includes immutable image/base identity, source/version, explicit tests, no production claim. Manifest references exact consumed release archive.
## 测试策略
Synthetic Docker metadata/command/error tests; actionlint. Native image build/test not run locally. Frozen prior packaging files unchanged except appended cloud workflow job in separate additive increment.
## 风险与决策
Container runtime image and local CLI proof do not establish functional ingress, liveTLS/WAF, secrets provisioning, rollback or supportedhost readiness.

## 文件结构
deploy/cloud-gateway/Dockerfile.runtime, scripts/cloud_image_gate.py and tests, existing cloud artifact workflow, issue40 image audit and three specs.
