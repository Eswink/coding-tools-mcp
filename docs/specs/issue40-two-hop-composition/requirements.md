# 需求文档：issue40-two-hop-composition

## 功能概述
增加只读 `engineering/issue40-two-hop-composition-v1`，使已独立审计原生源码P及有限组合可被当前工程校验接受；依据批准的COMPOSITION-AMENDMENT-DESIGN-PROPOSED.md与其INVENTORY-PROPOSED.json。规格是验收约束，不是实现或矩阵通过声明。

## 历史经验与坑（来自记忆库）
未依赖记忆库经验。旧187项执行中有七个失败条目，分属当前树检查六个subtest及旧nginx九源检查；保留真实失败，不能用452通过掩盖。旧fixture须取固定历史blob；当前adapter变长时，旧行数负例须基于冻结fixture而非当前文件。

## 术语定义
- F=`44b9f9b16f6981297bd1252eb3ab238ae581eccc`，tree=`99916334cc77fcc22209c99661e40ba1fd2e1276`，有序parents=[`310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`,`0a2554230a1523b0e6e5b43f0574897f4ed3b8a9`]
- P=`f8d187dfe9fe30e8641c7f8906d615265811c107`，tree=`0989ac3fc24839e0e83a3003abc41fe4f202ac64`，唯一parent=F；此最终P已获独立原生审计
- R=`e2e011f7f2a3a1df838bbd588106205b999db610`，tree=`c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3`；A=唯一一层amendment；I=[F,P或A]；L=[R,I]

## 范围边界
In Scope：仅三个旧测试适配器、新profile、新22项测试及三规格，共八路径，修改3/新增5；完整路径和预算见tasks。P1665项来自F1664项的六替换一新增；A1670项来自P的三替换五新增。
Out of Scope：三个历史profile及pins、旧fixture/runner/collector、P原生七源、workflow/runtime/Rust/auth、版本、依赖、发行文档及其它文件；无新增reader、证据格式或原生权限。
允许本地审查commit objects与fixture refs以物化精确A/I/L，及本地暂存/tree snapshot/staged detect_changes；不授权push、PR操作、远端merge、dispatch、tag、Release、真实部署、权限扩张或PR98/Issue86变更。

## 需求列表
### FR-1: 封闭拓扑与终结式分派
**优先级:** Must；**用户故事:** 作为审查者，我要精确有限组合而非放宽历史准入。
#### 验收标准（EARS）
WHEN 调用selector THEN SHALL 只解析一次可变ref，依次探测ownership、desktop、nginx拓扑；任一接受即在异常捕获外调用未修改selected_profile，其AssertionError或TopologyError内容失败都终结；仅三个拓扑均拒绝才进入新语法。
WHEN 新语法成立 THEN SHALL 独立验证F精确commit/tree/有序parents及未变nginx.selected_profile(F)完整旧链，验证P精确commit/tree/唯一parent[F]，仅接受P、A=[P]、I=[F,P或A]、L=[R,I]；I完整树等于第二parent，L仅覆盖四个固定R文档。
IF 未知profile/锚点、同树替身、缺失/反转/重复/额外parents、A2、后继、squash/rebase、嵌套release或[R,A] THEN SHALL 拒绝；不允许循环或一般祖先遍历，非法拓扑在内容读取前拒绝。
### FR-2: 原生七源与完整历史保护
**优先级:** Must；**用户故事:** 作为审查者，我要精确原生源码与所有受保护条目的字节身份。
#### 验收标准（EARS）
WHEN 校验P THEN SHALL 检查design列出的七路径各mode/blob/SHA256/bytes/lines，全部100644/blob；六替换一新增后恰1665项，其余1658项逐项等于F，不能把七项当新增。
IF 七源任一字段、每个历史保护条目、六个0.6.0-rc.4版本槽、唯一历史desktop collector可执行位或四发行文档的路径/模式/字节/删除变化 THEN SHALL 独立拒绝；旧不安全inner ingress renderer及被替代源码不能冒充P。
### FR-3: 八路径预算与无环完整pin
**优先级:** Must；**用户故事:** 作为审查者，我要可独立认证的有界amendment。
#### 验收标准（EARS）
WHEN 校验A THEN SHALL 唯一parent[P]、仅八路径变化且原生七源不变；先定稿三适配器、新测试、三规格的七完整blob/SHA256，再写入profile；外部独立manifest绑定全部八文件、自身profile字节及候选完整tree/parents。
IF 使用自hash循环、候选派生预期pin、可变branch pin或仅行数预算认证validator THEN SHALL 拒绝；所有旧profile/source/amendment pins和更严预算保持，ownership.budgets仍检查原路径，旧desktop/nginx预算只作用于各自冻结锚点。
IF 超过composition500/Δ24、desktop400/Δ48、nginx480/Δ128、profile360/Δ360、new tests480/Δ480、每spec80/Δ80或总Δ1300 THEN SHALL 回到设计评审；binary/non-numeric numstat及缺失/畸形diff字段也拒绝，不能新增helper文件绕过范围。
### FR-4: 窄适配与完整历史逆变换
**优先级:** Must；**用户故事:** 作为维护者，我要全部历史断言仍真实有效。
#### 验收标准（EARS）
WHEN 修改composition THEN SHALL 仅import、当前树test selector、disjoint EXPECTED_GROUPS三片段；逆变换精确恢复F全文件，其它方法、_feature_profile/_selected_profile、Git/index/worktree及run_inventory/InventoryResult/_flatten字节或AST不变。
WHEN 修改desktop THEN SHALL 仅两个兼容方法，setUp不变；先逆新composition层恢复F，再完整执行旧nginx→desktop→X逆变换/AST断言；明确保留147/167/187历史子集并另验新增22及209。
WHEN 修改nginx THEN SHALL 仅design列出的六方法；固定F父/tree并经旧selector验证后从F七历史条目构造fixture；九源当前字节读取改取F blob而保留全部旧pins；行数负例用冻结blob长度减一；完整新层逆变换后继续全部历史inverse、断言和167+20检查。
IF inverse片段零次/重复、片段外任意字节变化、历史blob/hash变化、旧方法增删改名、非allowlist方法变化、旧断言删除/弱化、ID缺失/重复/替换或冻结budget负例不再失败 THEN SHALL 独立拒绝；不得用泛化AST豁免或断言计数代替全文件inverse。
### FR-5: 冻结209项与独立拒绝边界
**优先级:** Must；**用户故事:** 作为审查者，我要完整执行证据而非过滤后绿灯。
#### 验收标准（EARS）
WHEN strict runner与独立普通discovery执行 THEN SHALL 各恰好冻结147+20+20旧ID和design逐字列出的22新ID，declared=loaded=executed=209唯一项；禁止skip/xfail/xpass、遗漏、重复、过滤或发现结果生成expected；两次是418执行而非418唯一案例。
WHEN 测非法parents THEN SHALL 先独立证明完整内容有效再spy内容reader零调用；内容负例先证明合法parents，再逐一变异七源所有字段、全部历史保护/六版本/四文档/amendment pins及每文件/总预算；覆盖binary、模式/类型、symlink/gitlink、增删改名、未知版本、移动ref及ambient Git重定向。
### FR-6: 当前矩阵与证据权限边界
**优先级:** Must；**用户故事:** 作为root，我要独立候选证据且保留最终授权。
#### 验收标准（EARS）
WHEN 验证定稿候选 THEN SHALL 在分别物化的干净A、I=[F,A]、L=[R,I]各执行209 strict及209 discovery、452=244+208且保留audit22、deployment86=68+2+16、desktop129=40+45+34+10、source-backport39；记录SHA/有序parents/完整tree-mode-blob表、命令、ID、数量、退出码和日志SHA256。
WHEN 建立fixture THEN SHALL 使用独立完整对象库，无共享index/commondir/alternates/元数据hardlink或symlink；清除GIT_*重定向并禁全局/系统config、hooks、fsmonitor、replace与自动元数据写入；官方GLib SHA256固定为233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5，不改旧fixture helper。
WHEN 汇报 THEN SHALL 把原生34/45/57、每job deployment86、Rust128、audit22及run/attempt/artifacts仅绑定实际P；A/I/L本地通过不转移原生证据。engineering_only保持true，全部旧false flags不提升；authenticated Agent/WSS/reconnect/revocation/drain、real VPS/DNS/TLS/WAF/ChatGPT、supported-host、Windows/Issue86、installed/security/release/publish门槛仍开放。

## 非功能需求
- NFR-1：仅标准库、惰性常量和只读注入callback；无import-time执行、process/network/filesystem writer或副作用
- NFR-2：语义信任边界HIGH；fresh impact与逐字diff/外部self-pin独立审查，不以过期图谱或静态LOW替代
- NFR-3：失败、阻断、未运行分别记录；保留历史红灯与全部旧false flags，包括old_ingress_two_hop_supported、production_touched、raw_zero_claim

## 依赖关系
复用未改ownership/desktop/nginx/库存runner/发行overlay；独立原生P审计、Probe4.0.1 check_spec、fresh graph、完整矩阵和外部manifest审查构成交付闸门。规格冻结后不为勾选进度而改变被pin字节。

## 检查清单
- [ ] FR-1至FR-6与全部NFR须由当前候选证据逐条验证，不以规格文字推定完成
- [ ] 外部独立审查确认八路径、七非self pin、自身profile、209库存及A/I/L矩阵后才报告本地验收
