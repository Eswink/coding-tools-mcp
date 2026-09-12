use serde::Serialize;

use super::probe::{self, Contract, Probe};
use crate::workspace::WorkspaceProfile;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HealthItem {
    pub label: String,
    pub ok: bool,
    pub detail: String,
    pub code: String,
    /// Only a validated configured origin plus a fixed path, never a remote URL.
    pub request: String,
    pub hint: String,
    /// A disabled/unconfigured service is not an OAuth failure or a PASS.
    pub skipped: bool,
}

/// Snapshot of the active listener identity, not stale saved Quick-tunnel URLs.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct HealthRuntime {
    pub mcp_running: bool,
    pub actions_running: bool,
    pub mcp_origin: String,
    pub actions_origin: String,
}

fn health_item(label: &str, result: Probe, public: bool) -> HealthItem {
    let hint = if result.ok { "" } else {
        match result.code {
            "oauth_not_configured" => "响应表示监听器未启用 OAuth。核对认证配置保存结果及运行中的服务，不要仅凭 /mcp 可达判断认证生效。",
            "nginx_discovery_route_not_found" => "发现路径返回 404 非 JSON，响应头标识为 Nginx（仅为线索）。检查该站点 /.well-known/ 静态目录、ACME 和隐藏路径规则；将这三个 OAuth 发现路径精确转发到与 /mcp 相同的上游，保留 URI。不要删除 ACME 或隐藏文件保护。",
            "discovery_route_not_found" => "OAuth 发现路径返回 404 非 JSON。检查 /.well-known/ 是否完整转发到与 /mcp 相同的运行实例；仅转发 /mcp 不足以完成 OAuth 发现。",
            "frp_route_not_found" => "返回 FRP 路由错误页。核对域名、隧道目标端口及整站路由。",
            "metadata_or_identity_mismatch" => "必需字段、版本或 issuer/resource 与当前监听器身份不一致；检查旧服务、缓存和转发目标。",
            "invalid_401_challenge" => "未认证 POST /mcp 必须返回 401 和精确的 resource_metadata；检查认证是否应用及代理是否保留响应头。",
            "redirect_rejected" => "发现端点发生重定向；本检查不跟随。请直接提供正确的 HTTPS 地址并核对代理规则。",
            "response_too_large" => "响应超出诊断大小限制；检查是否转发到了错误的服务或页面。",
            "non_json_response" | "invalid_json" => "响应不是有效的 JSON 发现文档；可能是代理、登录页或错误路由。",
            "invalid_or_missing_origin" => "当前运行实例尚无有效公网身份；检查隧道状态或固定 HTTPS 地址。",
            _ if public => "本检查使用无凭据直连。核对公网 DNS、TLS、/.well-known/* 与 /oauth/* 路由；本地通过不代表公网已通过。",
            _ => "确认本地服务已启动、端口正确；检查配置保存或重启时显示的错误。",
        }
    };
    HealthItem { label: label.into(), ok: result.ok, detail: result.detail(), code: result.code.into(), request: String::new(), hint: hint.into(), skipped: false }
}

fn skipped(label: &str, reason: &str) -> HealthItem {
    HealthItem { label: label.into(), ok: false, detail: reason.into(), code: "not_run".into(), request: String::new(), hint: String::new(), skipped: true }
}

async fn oauth_checks(client: &reqwest::Client, transport: &str, issuer: &str,
    mcp: bool, public: bool, enabled: bool, configured: bool) -> Vec<HealthItem> {
    let site = if public { "公网" } else { "本地" };
    let service = if mcp { "MCP" } else { "Actions" };
    let prefix = format!("{site} {service} OAuth");
    let mut specs = vec![
        ("授权元数据", "/.well-known/oauth-authorization-server", Contract::AuthorizationServer),
        ("受保护资源", if mcp { "/.well-known/oauth-protected-resource/mcp" }
            else { "/.well-known/oauth-protected-resource" }, Contract::ProtectedResource),
    ];
    if mcp {
        specs.push(("根路径兼容发现", "/.well-known/oauth-protected-resource", Contract::ProtectedResource));
        specs.push(("401 挑战", "/mcp", Contract::Challenge));
    }
    if !enabled || !configured {
        let reason = if !configured { "服务未运行或公网地址未就绪；未执行" } else { "当前未选择 OAuth；不适用" };
        return specs.iter().map(|(name, _, _)| skipped(&format!("{prefix} {name}"), reason)).collect();
    }
    let resource = if mcp { format!("{issuer}/mcp") } else { issuer.to_string() };
    let mut items = Vec::new();
    // At most four fixed requests per route. No dynamic URL traversal.
    for (name, path, contract) in specs {
        let result = probe::check(client, transport, path, contract, issuer, &resource).await;
        let mut item = health_item(&format!("{prefix} {name}"), result, public);
        if probe::valid_origin(transport) && probe::valid_origin(issuer) {
            let method = if contract == Contract::Challenge { "POST" } else { "GET" };
            item.request = format!("{method} {}{path}", transport.trim_end_matches('/'));
        }
        items.push(item);
    }
    items
}

async fn service_checks(client: &reqwest::Client, profile: &WorkspaceProfile,
    running: bool, origin: &str, mcp: bool) -> Vec<HealthItem> {
    let local = format!("http://127.0.0.1:{}", if mcp { profile.runtime.local_port } else { profile.actions.local_port });
    let origin = origin.trim_end_matches('/');
    let issuer = if origin.is_empty() { local.as_str() } else { origin };
    let enabled = if mcp { profile.auth.oauth_enabled() } else { profile.actions.auth_type == "oauth" };
    let path = if mcp { "/mcp" } else { "/health" };
    let contract = if mcp { Contract::Mcp } else { Contract::ActionsHealth };
    let name = if mcp { "MCP /mcp" } else { "Actions /health" };
    let mut items = Vec::new();
    if running {
        items.push(health_item(&format!("本地 {name}"), probe::check(client, &local, path, contract, issuer, "").await, false));
    } else { items.push(skipped(&format!("本地 {name}"), "服务已停止；未执行")); }
    if running && !origin.is_empty() {
        let (path, contract, name) = if mcp { (path, contract, name) } else { ("/openapi.json", Contract::OpenApi, "Actions /openapi.json") };
        items.push(health_item(&format!("公网 {name}"), probe::check(client, origin, path, contract, issuer, "").await, true));
    } else { items.push(skipped(&format!("公网 {}", if mcp { name } else { "Actions /openapi.json" }), "服务未运行或公网地址未就绪；未执行")); }
    if !mcp {
        items.push(if running {
            health_item("本地 Actions /openapi.json", probe::check(client, &local, "/openapi.json", Contract::OpenApi, issuer, "").await, false)
        } else { skipped("本地 Actions /openapi.json", "服务已停止；未执行") });
    }
    let (local_oauth, mut public_oauth) = tokio::join!(
        oauth_checks(client, &local, issuer, mcp, false, enabled, running),
        oauth_checks(client, origin, issuer, mcp, true, enabled, running && !origin.is_empty())
    );
    let local_pass = local_oauth.iter().all(|item| item.ok && !item.skipped);
    let public_challenge_pass = mcp && public_oauth.iter().any(|item| {
        item.label.ends_with("401 挑战") && item.ok && !item.skipped
    });
    if local_pass {
        for item in &mut public_oauth {
            if !item.ok && !item.skipped {
                let finding = if public_challenge_pass && matches!(item.code.as_str(),
                    "nginx_discovery_route_not_found" | "discovery_route_not_found") {
                    "本地 OAuth 发现链通过；公网 /mcp 的 401 挑战也通过，但所指发现文档缺失。请优先修复入口转发，不要关闭 OAuth 或重新生成密钥。"
                } else {
                    "本地 OAuth 发现链通过，公网未通过：优先核对隧道/代理的路由与响应头。"
                };
                item.hint = format!("{finding}{}", item.hint);
            }
        }
    }
    items.extend(local_oauth);
    items.extend(public_oauth);
    items
}

pub async fn run_health_checks(profile: &WorkspaceProfile, runtime: &HealthRuntime) -> Vec<HealthItem> {
    let client = match probe::client() {
        Ok(client) => client,
        Err(_) => return vec![health_item("诊断客户端", Probe::fail("client_initialization_failed", None), false)],
    };
    // MCP and Actions remain independent; stopped services never cause probes.
    let (mut mcp, actions) = tokio::join!(
        service_checks(&client, profile, runtime.mcp_running, &runtime.mcp_origin, true),
        service_checks(&client, profile, runtime.actions_running, &runtime.actions_origin, false)
    );
    mcp.extend(actions);
    mcp
}
