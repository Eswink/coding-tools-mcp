# 设计文档：nonproduction-container-topology
## 概述
A fixed non-root namespace anchor owns the container network namespace. Gateway and Nginx both join it; only the anchor publishes host127.0.0.1:port to internal8080. The anchor uses the existing gateway image with init plus sleep, no extra image or credentials. Nginx forwards validated originalHost to unchanged gateway127.0.0.1:28880.
## 技术方案
FR-1/FR-2: separate runtime renderer, protected whole-directory binds, fixed actualCLI, DBprivateinternal network, explicit resource/restart/stop limits; trusted canonicalorigin validated and no arbitraryforwardedHost trust.
FR-3: disposable fixture startsPG, creates non-superuser appDB role, uses shipped bootstrapCLI, no example enrollment. Password/key documents held only privatefiles/memory/pipes.
FR-4: actualOAuth token thenlegacyMCP initialization/tools list proves header transport; pendingWebSocketupgrade exercisesactualchannelroute andshutdown. Collision sentinel proves existinglistener preserved. Restart retainsOAuth; shippedrevocation survivesDBrestart and preventsMCPstart.
FR-5: fresh random Compose project and tempdirectory; cleanup only matchinglabels; sanitizedreceipts only. No daemonsettings/hostnetwork/persistentgrants.
FR-6: independent CI branch permitsengineering tests before RCversionchoice; labels recordcomponentversion andsource, notproductrelease readiness.
## Alternatives
Widening GatewayConfigbind weakens establishedtrustboundary; hostnetwork violatesprivateDB/hostisolation design. A namespace-sharing fixedproxy preserves both while adding a testable ingressprocess. No generic portforwarder witharbitrarytargets is introduced.
## 数据模型
Compose+Nginx paths are boundedfixedoutputs innewdirectory. Images exact localsha256 orregistrydigest. Config/private mounts matchactualUID checks. Report recordsfixedcase names/source/platform/Docker/Composeversions, no secretorHTTPpayload.
## 文件结构
runtime_topology.py; container_fixture.py; run_container_topology.py; test_runtime_topology.py; issue40-container-topology.yml; issue40-topology.md;3specs.
## 测试策略
Pure renderer mutation tests andactualDockerGHA: nonrootUID, loopbackport/privatenetwork inspect, sourceversion,realHTTP/OAuth/MCP/WebSocket,collision andshutdown/revocation. LocalDocker notclaimed.
## 风险与决策
Requires newshippedbootstrap commands present onfinalcandidate. A stable anchor prevents ordinary gateway restart from stranding ingress in an obsolete namespace. Replacing the anchor requires recreating both dependents; the native test verifies application restart without replacing ingress. Externalhost/TLS/WAF acceptance remainsseparate.
