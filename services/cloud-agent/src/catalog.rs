//! Static cloud tool contract. Catalog membership is not execution authority.
//! Both ends reject unknown tools/fields before dispatch; native authorization,
//! containment, sandboxing and durable no-replay admission remain mandatory.
use crate::{ProtocolError, Result};
use serde::Deserialize;
use serde_json::Value;
use std::sync::OnceLock;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ToolSpec {
    pub name: String,
    pub scopes: Vec<String>,
    pub mutating: bool,
    #[serde(default)]
    pub read_scopes: Option<Vec<String>>,
    pub schema: Value,
}

const AGENTS_MANAGE: &str = "agents.manage";
/// Scopes the catalog may declare that no grant can carry yet (A1 C2b): every
/// remote call needing one fails closed until C6 makes it grantable (O13).
pub const PENDING_SCOPES: &[&str] = &[AGENTS_MANAGE];

pub fn tools() -> &'static [ToolSpec] {
    static TOOLS: OnceLock<Vec<ToolSpec>> = OnceLock::new();
    TOOLS.get_or_init(|| {
        [
            include_str!("catalog/workspace_read.json"),
            include_str!("catalog/files_read.json"),
            include_str!("catalog/files_write.json"),
            include_str!("catalog/exec_run.json"),
            include_str!("catalog/task_read.json"),
            include_str!("catalog/task_manage.json"),
            include_str!("catalog/history_read.json"),
            include_str!("catalog/history_write.json"),
            include_str!("catalog/harness_write.json"),
            include_str!("catalog/agents_manage.json"),
        ]
        .into_iter()
        .flat_map(|raw| {
            serde_json::from_str::<Vec<ToolSpec>>(raw).expect("checked static cloud catalog")
        })
        .collect()
    })
}

pub fn tool(name: &str) -> Option<&'static ToolSpec> {
    tools().iter().find(|spec| spec.name == name)
}

impl ToolSpec {
    /// The repair-aware base set: `read_scopes` unless `repair: true`.
    fn base_scopes(&self, args: &Value) -> &[String] {
        if args.get("repair").and_then(Value::as_bool) != Some(true) {
            if let Some(scopes) = &self.read_scopes {
                return scopes;
            }
        }
        &self.scopes
    }
    /// The wire binds the primary scope; every scope is also checked by both
    /// gateway projection assessment and final native admission. No first-scope
    /// shortcut is sufficient (notably write_stdin requires exec.run too).
    /// A1 C2b (SPEC-A1 v4 §3.2): a call carrying `worker_id` also requires
    /// `agents.manage`, appended once; the primary scope never changes.
    pub fn scopes_for(&self, args: &Value) -> Vec<String> {
        let mut scopes = self.base_scopes(args).to_vec();
        if args.get("worker_id").is_some() && !scopes.iter().any(|s| s == AGENTS_MANAGE) {
            scopes.push(AGENTS_MANAGE.to_owned());
        }
        scopes
    }
    pub fn primary_scope(&self, args: &Value) -> &str {
        &self.base_scopes(args)[0]
    }
    pub fn is_mutating(&self, args: &Value) -> bool {
        self.mutating
            && !(self.read_scopes.is_some()
                && args.get("repair").and_then(Value::as_bool) != Some(true))
    }

    pub fn validate(&self, args: &Value) -> Result<()> {
        crate::canonical::digest_json(args, crate::execution::MAX_EXECUTION_ARGUMENTS)?;
        if !matches_schema(&self.schema, args, 0) {
            return Err(ProtocolError::InvalidRequest);
        }
        let object = args.as_object().ok_or(ProtocolError::InvalidRequest)?;
        for key in ["path", "workdir", "history_dir"] {
            if object
                .get(key)
                .is_some_and(|v| !v.as_str().is_some_and(relative_path))
            {
                return Err(ProtocolError::InvalidRequest);
            }
        }
        if object.get("paths").is_some_and(|v| {
            !v.as_array()
                .is_some_and(|a| a.iter().all(|v| v.as_str().is_some_and(relative_path)))
        }) {
            return Err(ProtocolError::InvalidRequest);
        }
        Ok(())
    }

    /// Materialize advertised defaults BEFORE computing the immutable request
    /// digest. Never rewrite arguments after admission or at the native host.
    pub fn arguments(&self, args: &Value) -> Result<Value> {
        self.validate(args)?;
        let mut result = args.clone();
        let object = result
            .as_object_mut()
            .ok_or(ProtocolError::InvalidRequest)?;
        if let Some(properties) = self.schema["properties"].as_object() {
            for (key, property) in properties {
                if !object.contains_key(key) {
                    if let Some(default) = property.get("default") {
                        object.insert(key.clone(), default.clone());
                    }
                }
            }
        }
        self.validate(&result)?;
        Ok(result)
    }
}

fn relative_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains('\\')
        && !path.contains(':')
        && !path.chars().any(char::is_control)
        && !path.split('/').any(|part| part == "..")
}

/// Deliberately small validator for the closed, flat native schema vocabulary.
/// No remote schema, references, regex evaluation or unbounded recursion.
fn matches_schema(schema: &Value, value: &Value, depth: usize) -> bool {
    if depth > 8 {
        return false;
    }
    if let Some(values) = schema.get("enum").and_then(Value::as_array) {
        if !values.contains(value) {
            return false;
        }
    }
    match schema["type"].as_str() {
        Some("object") => {
            let (Some(object), Some(properties)) =
                (value.as_object(), schema["properties"].as_object())
            else {
                return false;
            };
            if schema["additionalProperties"] != false {
                return false;
            }
            if schema
                .get("required")
                .and_then(Value::as_array)
                .is_some_and(|required| {
                    required
                        .iter()
                        .any(|key| key.as_str().is_none_or(|key| !object.contains_key(key)))
                })
            {
                return false;
            }
            object.iter().all(|(key, value)| {
                properties
                    .get(key)
                    .is_some_and(|field| matches_schema(field, value, depth + 1))
            })
        }
        Some("string") => value.as_str().is_some_and(|text| {
            // Only the reviewed fixed opaque-ID (32) and digest (64) patterns are
            // supported. Never evaluate attacker-supplied regexes or ignore one.
            if let Some(pattern) = schema.get("pattern") {
                let width = match pattern.as_str() {
                    Some("^[0-9a-f]{32}$") => 32,
                    Some("^[0-9a-f]{64}$") => 64,
                    _ => return false,
                };
                if text.len() != width
                    || !text
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                {
                    return false;
                }
            }
            let len = text.chars().count() as u64;
            schema
                .get("minLength")
                .and_then(Value::as_u64)
                .is_none_or(|n| len >= n)
                && schema
                    .get("maxLength")
                    .and_then(Value::as_u64)
                    .is_none_or(|n| len <= n)
        }),
        Some("integer") => {
            if !value.is_i64() && !value.is_u64() {
                return false;
            }
            // Catalog integer ranges fit exactly within f64's integer range;
            // values outside their range are rejected, not coerced or rounded.
            value.as_f64().is_some_and(|number| {
                schema
                    .get("minimum")
                    .and_then(Value::as_f64)
                    .is_none_or(|n| number >= n)
                    && schema
                        .get("maximum")
                        .and_then(Value::as_f64)
                        .is_none_or(|n| number <= n)
            })
        }
        Some("boolean") => value.is_boolean(),
        Some("array") => value.as_array().is_some_and(|values| {
            schema
                .get("minItems")
                .and_then(Value::as_u64)
                .is_none_or(|n| values.len() as u64 >= n)
                && schema
                    .get("maxItems")
                    .and_then(Value::as_u64)
                    .is_none_or(|n| values.len() as u64 <= n)
                && values
                    .iter()
                    .all(|v| matches_schema(&schema["items"], v, depth + 1))
        }),
        _ => false,
    }
}

#[cfg(test)]
mod tests;
