# 设计文档：issue40-nginx-composition

## 概述
对应FR-1至FR-6、NFR-1至NFR-3；在未变ownership/desktop外增加版本化只读组合层。固定锚点见requirements；评审packet SHA256=`0f41eacae6296c7e6db6d8c7f5b86f419102ae686f79ded2711735c970be067b`。
## 技术方案
### 架构设计
FR-1：caller ref→一次commit解析→ownership.topology→若接受则原content终结；否则desktop_topology→若接受则原desktop内容终结；仅两个拓扑拒绝后进入nginx_topology。不可捕获内容AssertionError改走其它校验器。
新语法为P(parent F)、A(parent P)、I'(parents[F,P或A])、L'(parents[R,I'])；无通用递归。先验证F有序父/tree及desktop.selected_profile(F)的ownership/J链，再固定P父/tree/九新增，最后A精确七路径与merge全树；R固定tree/四文档。
FR-2：P1659=F1650+九项；A1664=P1659+五项且替换两个旧测试。I'全树等于第二parent；L'全树等于I'加四精确R文档替换，禁止其它覆盖。
## 数据模型
所有映射使用完整path→(mode,kind,blob)，源pin另含SHA256/bytes/lines；新七项和P九项全为100644/blob。旧唯一collector100755保持不变，六版本槽完全等于F的0.6.0-rc.4。
### 固定源码映射（FR-2）
- `.github/workflows/issue40-current-nginx-include.yml` = `7f098353cb5101a7744b2fcb0457b1b50f040b47`
- `deploy/cloud-gateway/current_nginx_include.py` = `b44258e8b2e87bb9c5fa756b2cba99578246d757`
- `docs/deployment/current-nginx-include.md` = `e6bcf7d9855a2c78a6d04dfd3bbee35551d74045`
- `docs/specs/issue40-current-nginx-include/design.md` = `c7f11244ebed6684ccc1d2428a241b2a555cebf0`
- `docs/specs/issue40-current-nginx-include/requirements.md` = `d4322c2789e47b2cd1076eae0af075ca61a1351c`
- `docs/specs/issue40-current-nginx-include/tasks.md` = `c44e5e985a77be08bd15a76b28c7b060f21de675`
- `tests/cloud-gateway-deployment/run_current_nginx_checks.py` = `0d213532d6101f5146756a0806aa5f4bb4a7f7e5`
- `tests/cloud-gateway-deployment/run_current_nginx_runtime.py` = `3e666fe7ffff945e51db50e96937b1b92aeff3af`
- `tests/cloud-gateway-deployment/test_current_nginx_include.py` = `67c01e305babd19986ae8b64b76a26dcee3befdf`
九项SHA256/bytes/lines复制已评审source manifest字面量并独立复核P，不从待验候选派生预期值。
### 固定发行覆盖（FR-2）
- `docs/releases/next-rc-ledger.md` = `f44a9b8abf0dac1e35cea0e23b36750b297d0704`
- `docs/releases/next-rc-notes.md` = `c5cffd2d3dba5ce70f4dbe41167cf9f699c807d3`
- `docs/releases/source-acceptance-audit.md` = `7dd36643c0931fd5c8b6e2c2de8152b2f4c0366c`
- `docs/releases/verification-v0.6.0-rc.4.md` = `de0f6f90e184bb41af7bb714ad425e51f0a9d819`
## API 设计
`nginx_topology(ref,root,git,release)`只读父对象并返回封闭形状；`nginx_content`验证固定F/P及完整source；`amendment_content`验证七路径/六pins/预算；`selected_profile`注入只读git/entries/historical callbacks并终结式分派。未知requested profile discriminator在任何content前拒绝；仅已知engineering/issue40-nginx-composition-v1有资格进入新profile。
## 文件结构
仅修改`scripts/rc_pretag_composition_tests.py`和`scripts/rc_pretag_desktop_tests.py`；仅新增`scripts/rc_pretag_nginx_profile.py`、`scripts/rc_pretag_nginx_tests.py`及`docs/specs/issue40-nginx-composition/{requirements,design,tasks}.md`。完整路径/预算见tasks。
## 设计决策
### 决策1：无环信任引导（FR-3）
先定稿两适配器/新测试/三规格，再固定六完整blob/SHA256。profile不能认证自身最终blob或commit；外部独立manifest绑定七完整blob及candidate tree，尤其profile自身。预算与源码内自称通过不能代替外部认证；不使用候选派生预期或可变branch pins。
### 决策2：窄适配与可逆验证（FR-4）
composition仅import、当前树selector、追加disjoint EXPECTED_GROUPS三片段；保留其它所有代码。desktop仅setUp及test_composition_adapter_reconstructs_frozen_x/test_legacy_inventory_and_new_named_inventory_are_exact；验证F后从F六项构造旧fixture，当前adapter三片段逆变换必须精确恢复F，然后原F→X/AST全部运行；旧147+desktop20保持并追加20。
### 决策3：固定预算与不扩权（FR-3、FR-6）
composition≤500/Δ24；desktop tests≤400/Δ80；profile≤400；new tests≤480；spec各≤80；七路径Δ≤1250；保留所有更严旧预算。超限回设计评审，不分散到未批准文件；不改workflow/runtime/版本，不给予commit/push/merge/dispatch/release权限。
## 测试策略
FR-5：class=`rc_pretag_nginx_tests.NginxCompositionTests`，固定以下20方法，合并原167得到187；strict/discovery必须同一ID集合，loaded=executed，无skip/xfail/xpass/重复/过滤。
1. `test_exact_historical_profiles_and_pins_remain_unchanged`
2. `test_exact_f_anchor_parent_tree_and_legacy_validation`
3. `test_p_source_has_only_nine_exact_additions`
4. `test_exact_p_and_single_reviewed_amendment_accept`
5. `test_exact_ordered_feature_merge_equals_source_tree`
6. `test_exact_release_overlay_contains_only_four_pinned_documents`
7. `test_missing_unknown_and_same_tree_impostor_anchors_reject`
8. `test_reversed_duplicate_missing_and_extra_parents_reject_before_content`
9. `test_amendment_chains_nested_merges_and_postmerge_descendants_reject`
10. `test_each_nine_source_blob_and_sha256_mutation_rejects`
11. `test_missing_extra_renamed_mode_symlink_and_gitlink_entries_reject`
12. `test_each_historical_protected_entry_and_version_slot_remains_exact`
13. `test_release_document_byte_mode_path_and_deletion_drift_rejects`
14. `test_amendment_pins_scope_individual_and_total_budgets_reject`
15. `test_composition_adapter_inverse_recovers_exact_f`
16. `test_desktop_fixture_adapter_preserves_historical_assertions`
17. `test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids`
18. `test_mutable_refs_and_ambient_git_redirection_cannot_change_identity`
19. `test_topology_only_dispatch_keeps_legacy_content_failures_terminal`
20. `test_unknown_profile_versions_and_native_release_claims_reject`
parents负例先独立验证全树内容有效，再spy内容reader零调用；含同树fake F/P/R、[P,F]、[F,F]、三/重复/缺失parent、[R,A]、[R,L']、[F,I']、[A]、未知40hex。内容负例先合法parents，再逐个九源blob/hash、四文档、历史条目、六版本槽、六amendment pin变异；含binary/mode/type/symlink/gitlink/delete/rename/extra及第六第七未知spec。
FR-6：独立clean A/[F,A]/[R,feature]均运行187 strict+discovery、452(含exact-build-audit22)、deployment68、desktop129、source-backport39；两次187不是374唯一项。复制完整对象库，不共享commondir/alternates/hardlinks/index；禁Git全局/系统配置、清除GIT_*重定向、PYTHONDONTWRITEBYTECODE=1、PYTHONUTF8=1及官方GLib SHA256=`233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`。
记录每context的commit/ordered parents/tree/完整mode-blob表、loaded/executed/discovery ID、每command/count/exit/log SHA256。保留旧P/I/L1红灯；新profile承认P不表示旧guard曾通过。
## 风险评估
语义信任边界HIGH；旧ownership.release_content静态HIGH但只读复用且固定R输入，旧文件字节不变。新符号需index后fresh impact；最终精确diff、caps、inverse与外部profile-self hash独立审查；允许本地暂存、tree snapshot及staged detect_changes用于精确候选评审；source commit及publication仍需未来授权。
P的native37284577334 attempt1只属于P；合成通过不证明A原生。生产/unsupported-host/installed/security/release/publish/raw-zero未证；将来授权push自动触发现有Issue40及三hermetic workflow，无需编辑/dispatch；授权merge后只观察feature composition/consumer与PR89 composition/contracts/consumer五lane。
## 检查清单
- [x] 六项FR、七路径、精确pin引导、固定20测试和闭合拒绝边界已映射
- [ ] 当前实现/矩阵/外部独立评审仍须实际运行与核验，不由规格勾选推定通过
