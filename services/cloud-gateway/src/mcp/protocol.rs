use axum::http::HeaderMap;
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Map, Value};

pub const MODERN: &str = "2026-07-28";
pub const LEGACY: [&str; 2] = ["2025-11-25", "2025-06-18"];
pub const VERSIONS: [&str; 3] = [MODERN, LEGACY[0], LEGACY[1]];
const VERSION_META: &str = "io.modelcontextprotocol/protocolVersion";
const CAPABILITIES_META: &str = "io.modelcontextprotocol/clientCapabilities";
const INFO_META: &str = "io.modelcontextprotocol/serverInfo";

pub fn server_info() -> Value {
    json!({"name":"coding-tools-cloud-gateway","title":"Coding Tools Cloud Gateway","version":env!("CARGO_PKG_VERSION")})
}

pub fn instructions() -> &'static str {
    "Cloud MCP control plane. OAuth and the public tool catalog remain available when the local Agent is offline. Workspace execution still requires the current conversation's local approval and execution gate. On WORKSPACE_OFFLINE, CHAT_AUTHORIZATION_REQUIRED, CHAT_SCOPE_REQUIRED, CHAT_RECOVERY_REQUIRED, or EXECUTION_NOT_CONNECTED, do not request OAuth again and do not automatically retry or replay the tool call."
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WireError {
    pub status: u16,
    pub code: i64,
    pub message: &'static str,
    pub data: Option<Value>,
}
impl WireError {
    pub fn new(status: u16, code: i64, message: &'static str) -> Self {
        Self {
            status,
            code,
            message,
            data: None,
        }
    }
    pub fn unsupported(requested: &str) -> Self {
        Self {
            status: 400,
            code: -32022,
            message: "Unsupported protocol version",
            data: Some(
                json!({"supported":VERSIONS,"requested":requested.chars().take(128).collect::<String>()}),
            ),
        }
    }
}

#[derive(Debug, Clone)]
pub struct RpcMessage {
    pub id: Option<Value>,
    pub method: String,
    pub params: Map<String, Value>,
}

pub fn error_envelope(error: &WireError, id: Option<&Value>) -> Value {
    let mut e = json!({"code":error.code,"message":error.message});
    if let Some(data) = &error.data {
        e["data"] = data.clone();
    }
    let mut out = json!({"jsonrpc":"2.0","error":e});
    if let Some(id) = id {
        out["id"] = id.clone();
    }
    out
}

pub fn complete(version: &str, mut data: Map<String, Value>) -> Value {
    if version == MODERN {
        data.insert("resultType".into(), Value::String("complete".into()));
        data.insert("_meta".into(), json!({INFO_META:server_info()}));
    }
    Value::Object(data)
}

pub fn tool_result(version: &str, data: Value) -> Value {
    let is_error = data.get("ok").and_then(Value::as_bool) == Some(false);
    let mut out = Map::new();
    out.insert("content".into(), json!([{"type":"text","text":serde_json::to_string(&data).unwrap_or_else(|_| "{\"ok\":false}".into())}]));
    out.insert("structuredContent".into(), data);
    out.insert("isError".into(), Value::Bool(is_error));
    complete(version, out)
}

pub fn parse_message(bytes: &[u8]) -> Result<RpcMessage, WireError> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| WireError::new(400, -32700, "Invalid JSON"))?;
    let obj = value
        .as_object()
        .ok_or_else(|| WireError::new(400, -32600, "Invalid request"))?;
    if obj
        .keys()
        .any(|k| !matches!(k.as_str(), "jsonrpc" | "id" | "method" | "params"))
        || obj.get("jsonrpc").and_then(Value::as_str) != Some("2.0")
    {
        return Err(WireError::new(400, -32600, "Invalid request"));
    }
    let method = obj
        .get("method")
        .and_then(Value::as_str)
        .ok_or_else(|| WireError::new(400, -32600, "Invalid request"))?;
    if method.is_empty() || method.len() > 128 || method.chars().any(char::is_control) {
        return Err(WireError::new(400, -32600, "Invalid request"));
    }
    let id = if obj.contains_key("id") {
        let id = obj.get("id").unwrap();
        let valid = match id {
            Value::String(s) => s.len() <= 256 && !s.chars().any(char::is_control),
            Value::Number(n) => n
                .as_i64()
                .is_some_and(|v| v.unsigned_abs() <= 9_007_199_254_740_991),
            _ => false,
        };
        if !valid {
            return Err(WireError::new(400, -32600, "Invalid request ID"));
        }
        Some(id.clone())
    } else {
        None
    };
    let params = match obj.get("params") {
        None => Map::new(),
        Some(Value::Object(m)) => m.clone(),
        Some(_) => return Err(WireError::new(400, -32600, "Invalid request")),
    };
    Ok(RpcMessage {
        id,
        method: method.into(),
        params,
    })
}

fn one_header<'a>(headers: &'a HeaderMap, name: &str) -> Result<Option<&'a str>, WireError> {
    if headers.get_all(name).iter().count() > 1 {
        return Err(WireError::new(400, -32020, "Duplicate header"));
    }
    Ok(headers.get(name).and_then(|v| v.to_str().ok()))
}

fn decode_name(value: &str) -> Result<String, WireError> {
    if value.starts_with("=?base64?") && value.ends_with("?=") {
        let payload = &value[9..value.len() - 2];
        let bytes = STANDARD
            .decode(payload)
            .map_err(|_| WireError::new(400, -32020, "Invalid mirrored header"))?;
        if STANDARD.encode(&bytes) != payload {
            return Err(WireError::new(400, -32020, "Invalid mirrored header"));
        }
        return String::from_utf8(bytes)
            .map_err(|_| WireError::new(400, -32020, "Invalid mirrored header"));
    }
    if value.is_empty()
        || value.trim() != value
        || !value.bytes().all(|b| (0x20..=0x7e).contains(&b))
    {
        return Err(WireError::new(400, -32020, "Invalid mirrored header"));
    }
    Ok(value.into())
}

pub fn validate_version(message: &RpcMessage, headers: &HeaderMap) -> Result<String, WireError> {
    let header_version = one_header(headers, "mcp-protocol-version")?;
    let version = header_version
        .or_else(|| {
            (message.method == "initialize")
                .then(|| {
                    message
                        .params
                        .get("protocolVersion")
                        .and_then(Value::as_str)
                })
                .flatten()
        })
        .ok_or_else(|| WireError::new(400, -32020, "Missing protocol header"))?;
    if !VERSIONS.contains(&version) {
        return Err(WireError::unsupported(version));
    }
    let meta = message.params.get("_meta").and_then(Value::as_object);
    if version == MODERN {
        if header_version != Some(MODERN)
            || meta
                .and_then(|m| m.get(VERSION_META))
                .and_then(Value::as_str)
                != Some(MODERN)
            || one_header(headers, "mcp-method")? != Some(message.method.as_str())
        {
            return Err(WireError::new(400, -32020, "Mirrored header mismatch"));
        }
        let meta =
            meta.ok_or_else(|| WireError::new(400, -32602, "Missing client capabilities"))?;
        if !meta.get(CAPABILITIES_META).is_some_and(Value::is_object) {
            return Err(WireError::new(400, -32602, "Missing client capabilities"));
        }
        if let Some(client) = meta.get("io.modelcontextprotocol/clientInfo") {
            let Some(c) = client.as_object() else {
                return Err(WireError::new(400, -32602, "Invalid client information"));
            };
            if !c.get("name").is_some_and(Value::is_string)
                || !c.get("version").is_some_and(Value::is_string)
            {
                return Err(WireError::new(400, -32602, "Invalid client information"));
            }
        }
        if message.method == "tools/call" {
            let name = message
                .params
                .get("name")
                .and_then(Value::as_str)
                .ok_or_else(|| WireError::new(400, -32602, "Missing tool name"))?;
            let mirrored = one_header(headers, "mcp-name")?
                .ok_or_else(|| WireError::new(400, -32020, "Missing mirrored header"))?;
            if decode_name(mirrored)? != name {
                return Err(WireError::new(400, -32020, "Mirrored header mismatch"));
            }
        } else if one_header(headers, "mcp-name")?.is_some() {
            return Err(WireError::new(400, -32020, "Unexpected mirrored header"));
        }
    } else {
        if let Some(meta) = meta {
            if meta.contains_key(VERSION_META) || meta.contains_key(CAPABILITIES_META) {
                return Err(WireError::new(400, -32020, "Mixed protocol eras"));
            }
        }
        if message.method == "initialize"
            && message
                .params
                .get("protocolVersion")
                .and_then(Value::as_str)
                != Some(version)
        {
            return Err(WireError::new(
                400,
                -32020,
                "Initialization version mismatch",
            ));
        }
    }
    Ok(version.into())
}

fn tool(name: &str, description: &str, input: Value, read_only: bool) -> Value {
    json!({
        "name":name,
        "description":description,
        "inputSchema":input,
        "annotations":{"readOnlyHint":read_only,"destructiveHint":false,"openWorldHint":false},
        "securitySchemes":[{"type":"oauth2","scopes":["mcp"]}]
    })
}

pub fn catalog() -> Vec<Value> {
    let empty = json!({"type":"object","properties":{},"additionalProperties":false});
    vec![
        tool("auth_status", "Return only the current conversation's cloud-visible local authorization class; never workspace paths, owner identity, tasks, or grants.", empty.clone(), true),
        tool("request_chat_authorization", "Check for an already-approved local conversation. Cloud service cannot create local approval; unavailable requests must not be retried or converted into OAuth reconnect.", json!({"type":"object","properties":{"scopes":{"type":"array","minItems":1,"maxItems":1,"items":{"type":"string","enum":["files.read"]}}},"additionalProperties":false}), false),
        tool("workspace_probe", "Read-only availability probe for the locally approved workspace. Offline is a normal tool error and never an OAuth failure. This cloud increment never performs local filesystem or command side effects.", empty, true),
    ]
}

pub fn protocol_result(message: &RpcMessage, version: &str) -> Result<Option<Value>, WireError> {
    if message.id.is_none() {
        if version != MODERN && message.method == "notifications/initialized" {
            return Ok(None);
        }
        return Err(WireError::new(400, -32600, "Unsupported notification"));
    }
    let result = match message.method.as_str() {
        "server/discover" if version == MODERN => {
            let mut m = Map::new();
            m.insert("supportedVersions".into(), json!(VERSIONS));
            m.insert("capabilities".into(), json!({"tools":{}}));
            m.insert("instructions".into(), Value::String(instructions().into()));
            complete(version, m)
        }
        "initialize" if version != MODERN => {
            if !message
                .params
                .get("capabilities")
                .is_some_and(Value::is_object)
                || !message.params.get("clientInfo").is_some_and(|v| {
                    v.as_object().is_some_and(|o| {
                        o.get("name").is_some_and(Value::is_string)
                            && o.get("version").is_some_and(Value::is_string)
                    })
                })
            {
                return Err(WireError::new(400, -32602, "Invalid initialization"));
            }
            json!({"protocolVersion":version,"capabilities":{"tools":{"listChanged":false}},"serverInfo":server_info(),"instructions":instructions()})
        }
        "ping" if version != MODERN => json!({}),
        "tools/list" => {
            if message.params.get("cursor").is_some() {
                return Err(WireError::new(400, -32602, "Invalid cursor"));
            }
            let mut m = Map::new();
            m.insert("tools".into(), Value::Array(catalog()));
            complete(version, m)
        }
        "tools/call" => return Ok(None),
        _ => {
            return Err(WireError::new(
                if version == MODERN { 404 } else { 400 },
                -32601,
                "Method not found",
            ))
        }
    };
    Ok(Some(
        json!({"jsonrpc":"2.0","id":message.id.clone().unwrap(),"result":result}),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    fn modern_headers(method: &str, name: Option<&str>) -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert("mcp-protocol-version", HeaderValue::from_static(MODERN));
        h.insert("mcp-method", HeaderValue::from_str(method).unwrap());
        if let Some(name) = name {
            h.insert("mcp-name", HeaderValue::from_str(name).unwrap());
        }
        h
    }
    fn modern(method: &str, params: Value) -> RpcMessage {
        RpcMessage {
            id: Some(json!(1)),
            method: method.into(),
            params: params.as_object().unwrap().clone(),
        }
    }
    #[test]
    fn modern_headers_must_match_body() {
        let m = modern(
            "tools/list",
            json!({"_meta":{VERSION_META:MODERN,CAPABILITIES_META:{}}}),
        );
        assert_eq!(
            validate_version(&m, &modern_headers("tools/list", None)).unwrap(),
            MODERN
        );
        assert!(validate_version(&m, &modern_headers("server/discover", None)).is_err());
    }
    #[test]
    fn modern_name_sentinel_decodes_canonically() {
        let m = modern(
            "tools/call",
            json!({"name":"workspace_probe","_meta":{VERSION_META:MODERN,CAPABILITIES_META:{}}}),
        );
        let encoded = format!("=?base64?{}?=", STANDARD.encode("workspace_probe"));
        assert_eq!(decode_name(&encoded).unwrap(), "workspace_probe");
        let mut h = modern_headers("tools/call", None);
        h.insert("mcp-name", HeaderValue::from_str(&encoded).unwrap());
        assert_eq!(validate_version(&m, &h).unwrap(), MODERN);
    }
    #[test]
    fn legacy_initialize_is_only_headerless_handshake() {
        let init=RpcMessage{id:Some(json!(1)),method:"initialize".into(),params:json!({"protocolVersion":LEGACY[1],"capabilities":{},"clientInfo":{"name":"x","version":"1"}}).as_object().unwrap().clone()};
        assert_eq!(
            validate_version(&init, &HeaderMap::new()).unwrap(),
            LEGACY[1]
        );
        let list = RpcMessage {
            id: Some(json!(2)),
            method: "tools/list".into(),
            params: Map::new(),
        };
        assert!(validate_version(&list, &HeaderMap::new()).is_err());
    }
    #[test]
    fn catalog_is_stable_and_side_effect_free() {
        let names: Vec<_> = catalog()
            .into_iter()
            .map(|v| v["name"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(
            names,
            [
                "auth_status",
                "request_chat_authorization",
                "workspace_probe"
            ]
        );
    }
}
