# 云网关完整执行桥

对应Epic #32与Issue #81。基线2c5d133；恢复的14文件候选树2960722f仅为未集成的路由增量。完整计划仍为交付目标。

## 子规格索引

- [持久领取及认证路由](subspecs/dispatch-core/spec.md)：FR-1, FR-2, FR-3
- [本地批准及工具执行](subspecs/local-authority/spec.md)：FR-4, FR-5, FR-6
- [故障与发布验收](subspecs/integration-gates/spec.md)：FR-7, FR-8

## 里程碑

先验证持久领取和通道，再接通现有本地批准和真正工具执行；最后完成真实传输故障回归和所有完整计划工程门槛。不创建缩减范围的预发布。

## 原则

云端认证不授予本地执行权限，传输可用性不代替本地批准；完整Issue81及Epic32才是交付范围。

## 依赖关系

dispatch-core → local-authority → integration-gates，见spec-manifest.json。
