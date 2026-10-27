# 设计文档：issue40-two-hop-composition

## 概述
对应FR-1至FR-6、NFR-1至NFR-3；采用批准八路径方案，固定最终原生P及F/R锚点见requirements。新增工程组合层不修订三个历史profile或转移原生资格。
## 技术方案
### 架构设计
FR-1：caller ref只解析一次；immutable commit依次探测ownership.topology、desktop_topology、nginx_topology。拓扑接受后于catch外调用原selected_profile；内容AssertionError/TopologyError均终结，仅全部拓扑拒绝进入two_hop_topology。
新语法只有P=[F]、A=[P]、I=[F,P或A]、L=[R,I]；无遍历/递归扩张。独立核验F精确父/tree并调用未改nginx.selected_profile(F)，保留ownership/J/desktop/nginx链；P精确commit/tree/父及全部源码须独立于候选形状验证。
FR-2：P1665=F1664−六旧条目+六替换+一新增；保留其余1658项。A1670=P1665−三旧适配器+三替换+五新增；I全map等于第二parent；L全map仅为I覆盖四固定R文档。
## 数据模型
全树为path→(mode,type,blob)；七原生pin另含SHA256/bytes/lines，全部100644/blob，固定审核字面量来自P不可变对象；六rc.4槽及唯一历史100755 collector完全保留。所有旧profile、source/amendment pins及更严预算不变。
### 固定原生源码（FR-2）
- `.github/workflows/issue40-current-nginx-include.yml`：替换
- `deploy/cloud-gateway/runtime_topology.py`：替换
- `tests/cloud-gateway-deployment/run_current_nginx_runtime.py`：替换
- `docs/deployment/current-nginx-include.md`：替换
- `tests/cloud-gateway-deployment/test_runtime_topology.py`：替换
- `tests/cloud-gateway-deployment/test_current_nginx_include.py`：替换
- `tests/cloud-gateway-deployment/test_current_nginx_two_hop.py`：新增
### 固定发行覆盖（FR-2）
- `docs/releases/next-rc-ledger.md` = `f44a9b8abf0dac1e35cea0e23b36750b297d0704`
- `docs/releases/next-rc-notes.md` = `c5cffd2d3dba5ce70f4dbe41167cf9f699c807d3`
- `docs/releases/source-acceptance-audit.md` = `7dd36643c0931fd5c8b6e2c2de8152b2f4c0366c`
- `docs/releases/verification-v0.6.0-rc.4.md` = `de0f6f90e184bb41af7bb714ad425e51f0a9d819`
四项均100644/blob，复用旧release_content；拒绝额外覆盖、路径/模式/字节漂移与删除。
## API 设计
仅公开two_hop_topology、two_hop_content、amendment_content、selected_profile与窄private helpers；分别负责闭合父形、F/P完整源码、A精确八路径/七pins/预算、终结式分派。仅标准库/常量/只读callback，未知profile discriminator在content前拒绝；无导入时执行、写入或新证据reader。
## 文件结构
仅tasks列出的八路径；三个适配器、一个profile、一个22方法测试文件、三份spec。新helpers只在两新Python文件，不改变旧fixture、库存runner、workflow、runtime或历史profile。
## 设计决策
### 决策1：无环pin与有限预算（FR-3）
先定稿三适配器/新测试/三规格七文件，再将完整blob/SHA256固定于profile；外部独立manifest认证八文件、profile self-bytes及候选tree/parents。禁自hash环、候选派生期望、mutable branch pins；预算不认证validator。
composition≤500/Δ24、desktop≤400/Δ48、nginx≤480/Δ128、profile≤360/Δ360、new tests≤480/Δ480、spec各≤80/Δ80、总Δ≤1300，Δ以最终P计；继续原ownership.budgets，旧desktop/nginx预算只对冻结fixture；binary/non-numeric/malformed/missing numstat字段拒绝，超限回设计评审。
### 决策2：三适配器窄逆变换（FR-4）
composition只import/selector/EXPECTED_GROUPS三片段；逆后全文件等于F。desktop只test_composition_adapter_reconstructs_frozen_x与test_legacy_inventory_and_new_named_inventory_are_exact，setUp不变；先逆新层再执行原nginx→desktop→X检查，保留147/167/187子集并附209检查。
nginx仅六方法：setUp；test_p_source_has_only_nine_exact_additions；test_amendment_pins_scope_individual_and_total_budgets_reject；test_composition_adapter_inverse_recovers_exact_f；test_desktop_fixture_adapter_preserves_historical_assertions；test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids。
setUp验证新F父/tree及旧nginx选择，再取F七历史amendment条目；九源方法只把当前树读取换为已验F blob，旧P/tree/parent/nine pins全部保留；预算负例基于冻结fixture长度减一。逆composition/desktop新层先精确恢复F，再执行旧inverse、AST、Counter及167+20断言。
新tests固定composition1/desktop2/nginx6 changed-method allowlists、方法集合、未变方法AST、旧断言与全文件inverse；独立拒绝缺失/重复片段、片段外注释/空白变化、历史blob/hash漂移、增删改名/非allowlist改动、断言弱化、ID替换及不再触发的旧预算负例。
### 决策3：保留旧信任域（FR-1、FR-6）
不改旧SOURCE_PINS、ALLOWED/CAPS、拒绝改旧nginx准入任意后继或content失败fallback；不另建runner/collector，不删除/跳过/mock-away历史测试。所有旧false flags及engineering_only=true不变；P原生证据不移记A/I/L。
## 测试策略
FR-5：冻结原187完整ID及以下22，class=`rc_pretag_two_hop_tests.TwoHopCompositionTests`；strict与普通discovery各209唯一ID，declared=loaded=executed，零skip/xfail/xpass/重复/遗漏/过滤。
1. `test_frozen_historical_profiles_and_pins_remain_exact`
2. `test_exact_f_parent_tree_and_nginx_validation`
3. `test_native_p_sole_parent_tree_and_seven_path_delta`
4. `test_exact_p_and_one_reviewed_amendment_accept`
5. `test_ordered_feature_merge_requires_complete_source_tree`
6. `test_release_overlay_contains_only_four_exact_documents`
7. `test_unknown_missing_and_same_tree_impostor_anchors_reject`
8. `test_reversed_duplicate_missing_and_extra_parents_reject_before_content`
9. `test_amendment_chains_nested_merges_and_descendants_reject`
10. `test_each_native_source_blob_digest_size_and_line_pin_rejects_drift`
11. `test_missing_extra_rename_mode_symlink_and_gitlink_entries_reject`
12. `test_every_historical_protected_entry_and_six_version_slots_remain_exact`
13. `test_release_document_byte_mode_path_and_deletion_drift_rejects`
14. `test_amendment_pins_scope_binary_and_individual_total_budgets_reject`
15. `test_composition_inverse_recovers_exact_f_and_rejects_fragment_drift`
16. `test_desktop_adapter_inverse_preserves_all_historical_assertions`
17. `test_nginx_adapter_inverse_preserves_historical_fixtures_and_budget_negatives`
18. `test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed`
19. `test_mutable_refs_and_ambient_git_redirection_cannot_change_identity`
20. `test_topology_dispatch_keeps_all_legacy_content_failures_terminal`
21. `test_unknown_profiles_and_native_release_approval_claims_reject`
22. `test_old_inner_ingress_and_superseded_source_cannot_replace_native_pins`
非法parents先证明独立全内容有效，再spy reader零调用；内容负例先验合法parents。逐一覆盖全部source字段、protected entries/六版本/四docs/amendment pins、各caps/总cap、binary/mode/type/symlink/gitlink/增删改名，same-tree impostor、A2/后继/嵌套、移动ref及ambient Git。
FR-6：独立clean A、I=[F,A]、L=[R,I]各209 strict+209 discovery、452=244+208含audit22、deployment86=68+2+16、desktop129=40+45+34+10、source-backport39；418只是每context双执行总数。完整对象库隔离及官方GLib固定hash见requirements，不改fixture helper。
每context记录SHA/有序parents/完整tree-mode-blob、exact commands、loaded/executed IDs、counts/exits/log SHA256；保留七个旧失败。原生34/45/57、deployment86/job、Rust128/audit22只属于最终P，不因本地组合通过而转移。
## 风险评估
语义HIGH；修改既有1+2+6方法前fresh upstream impact/context并披露图谱限制，新增四公开函数及helpers/tests建立索引后impact；staged detect_changes、精确diff/caps/inverse和外部profile self认证为独立闸门。
Unauthenticated pending-WebSocket不证明authenticated Agent/WSS/reconnect/revocation/drain；VPS/DNS/TLS/WAF/ChatGPT、supported-host、Windows/Issue86、installed/security/release/publication仍开放；本地通过不授权后续远端或生产动作。
## 检查清单
- [ ] 全部FR、八路径、固定22方法和外部self-pin以当前实际证据审查；冻结规格不表示实现完成
- [ ] A/I/L完整矩阵及独立审核完成前，不声明通过或提升原生/发布权限
