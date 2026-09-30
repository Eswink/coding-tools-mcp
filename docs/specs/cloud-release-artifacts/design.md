# 设计文档：cloud-release-artifacts
## 概述
Separate release artifact family, sharing the exact-source integration authority with desktop packaging.
## 技术方案
FR-1: read actual Cargo package and matching lockentries, product version fromexisting strictRC gate. Components report their ownversions.
FR-2: Ubuntu22 release lockedbuild, deterministic allowlist of4ELF binaries; actualCLI probes with boundedtimeouts.
FR-3: archive only bin/coding-tools-gateway,bin/coding-tools-agent,bin/coding-tools-control-gateway,bin/coding-tools-mcp-gateway,manifest.json,README.md. Allregularmembers; fixedmodes; archivehash in outerreceipt; beforeextraction reject extras/links/pathtraversal. SHA256 binds eachbinary.
FR-4: Ubuntu24 consumes samearchive, existing serviceHTTP andAgentWSS scripts with fresh disposablePG16; finalreport rejectsfailure/missingcases. No targetbuild substituted.
FR-5: no releasepublisher. No staleCentOS/Baotadeploymentclaim. Parentpublication requiresdesktop+server evidence.
## 数据模型
Manifest sourceSHA/tree/run/product/component versions,target,OS, fourbinarydigests/CLI observations. Outerarchive receipt includeshash/size. Process report containsactual existingfixtureJSON only.
## 文件结构
.github/workflows/full-rc-cloud-binaries.yml; scripts/cloud_release_bundle.py; scripts/cloud_release_bundle_tests.py; docs/releases/cloud-binary-install.md; three specs.
## 测试策略
Syntheticunit tests forversiondrift, ELFshape,archive traversal/extra/symlink/digest/source mismatch andprocessreportfailure. actionlint. No localreleasebuild due diskconstraint; actualCI pendingfinalcandidate.
## 风险与决策
Ubuntu22glibc build is not proof ofCentOS8compatibility. Deploymentsecrets/config/provisioning remainexplicitoperatorrequirements; no automaticVPSaction. Windowsruntime remainsblocking overallrelease.
