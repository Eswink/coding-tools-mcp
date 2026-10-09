# 设计

## 概述
本轮有限授权已包含外部第10 factory hook源码与普通负控，原方法启动另行审查。diag5真实FAIL和终态独立核验保持；observer0不是TLS未执行。新的独立目录未恢复纯checkout，后续使用已核实纯源只读，任何新observer源都不得写入原SUT。

## 技术方案
对应需求：FR-1、FR-2、FR-3。
原_CredentialOwner.__init__创建Selection(deepcopy(input.subject),原artifact字段)，因此input.selection与credential._selection为不同真实对象。GitHub.__init__先调用原factory再赋self._credential；PublisherSession使用api.selection形成native SessionOwner。原ArtifactTLS保存输入f.selection；旧observer要求fixture.selection is api.selection可能拒绝这种真实克隆路径，需组件failure-first实证，不能反推diag5原因。

普通组件用原publisher_fixture、ArtifactTLS、PublisherSession constructor，保持全部original callable；不patch新factory或任何authorizer，不调用_session_owner直接工厂。检查克隆与原引用链后，直接真实TLS connect→close验证socket/fixture线程退出；只记录boolean/安全typename/计数，实际selection/credential/token/socket/端点不序列化。组件runner用真实owned process/kernel原语，预算45/7/2/2，真实native exit/ECHILD与cleanup单独核实。

待授权设计：原factory返回时bounded strongref记录PENDING，后续realclient已赋credential后按精确identity推广为provenance；输入fixture.selection仍须是原input，同时returned clone/client/owner/session链一致。不能将与clone值相等的外来input推广。记录证明来源不是权限，既存operation scope仍须全部原检查。工厂成功后的观察cancel必须在真实constructor赋值和真实资源cleanup后保原对象传播，不从函数返回前取消造成赋值/cleanup缺口。上下文强ref终末清理，所有alias逐个逆序restore，任一失败invalid；取消原对象不可归一化丢失。

## 文件结构
- docs/specs/publisher-native-clone-diagnostic6/{requirements,design,tasks}.md：本阶段规格。
- native-clone-readonly-child.py/supervisor.py/安全结果：真实8组件checks完成；串行关闭成功不证明关闭异常路径。
- 第10 factory observer与普通负控：源码授权；launcher/seal/原方法启动待独立review与root最终literal授权。
- 旧diag5封存与cp77只读保持，不复写。

## 取消与真实关闭保护
对应需求：FR-2、FR-3。成功factory后取消只保存原对象并返回原credential，使原GitHub constructor实际赋值。原delegate异常立即bare raise不改对象，delegate BaseException sticky留到终末防原unittest归一丢失。factory观察本身不操作socket/session，也不追加authenticate。registry直到原runner和原fixture/session cleanup结束后清理；全部十alias仍每个独立逆序restore。finish将原primary/实际cancel/restoreerror去重按对象identity聚合。普通负控必须分别attempt sock.close与session.close/fixture.close，前关闭抛错不能跳后关闭；同时保全原primary和每个实际close异常对象。assignmentmissing/foreign-equalinput/credential/client/clone/session/owner/fixture引用漂移/退休/128cap/多记录歧义均不推广UNKNOWN。
