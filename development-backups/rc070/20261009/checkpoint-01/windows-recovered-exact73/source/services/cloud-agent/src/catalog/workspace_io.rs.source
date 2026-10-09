//! Hash-bound data intent only. This cannot mint permission, a root or VM seal.
use crate::{ProtocolError, Result};
use serde_json::Value;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkspaceIo {
    input: String,
    output_parent: String,
    output_leaf: String,
}
impl WorkspaceIo {
    pub fn input(&self) -> &str {
        &self.input
    }
    pub fn output_parent(&self) -> &str {
        &self.output_parent
    }
    pub fn output_leaf(&self) -> &str {
        &self.output_leaf
    }
    /// Parse the immutable arguments, without normalizing names or rewriting
    /// defaults. A native issuer must still require exec_command + all scopes.
    pub fn from_arguments(args: &Value) -> Result<Option<Self>> {
        let args = args.as_object().ok_or(ProtocolError::InvalidRequest)?;
        let Some(raw) = args.get("workspace_io") else {
            return Ok(None);
        };
        let object = raw.as_object().ok_or(ProtocolError::InvalidRequest)?;
        if object.len() != 3
            || object
                .keys()
                .any(|key| !matches!(key.as_str(), "input" | "output_parent" | "output_leaf"))
        {
            return Err(ProtocolError::InvalidRequest);
        }
        let text = |key: &str| {
            object
                .get(key)
                .and_then(Value::as_str)
                .ok_or(ProtocolError::InvalidRequest)
        };
        let input = text("input")?;
        let parent = text("output_parent")?;
        let leaf = text("output_leaf")?;
        if !path(input)
            || !path(parent)
            || !component(leaf)
            || args.get("workdir").is_some_and(|v| v != ".")
            || args.get("tty").is_some_and(|v| v != false)
            || args
                .get("cmd")
                .is_none_or(|v| v.as_str().is_none_or(|s| s.is_empty() || s.len() > 2048))
            || args
                .get("stdin")
                .is_some_and(|v| v.as_str().is_none_or(|s| s.len() > 1024))
        {
            return Err(ProtocolError::InvalidRequest);
        }
        Ok(Some(Self {
            input: input.into(),
            output_parent: parent.into(),
            output_leaf: leaf.into(),
        }))
    }
}
fn path(text: &str) -> bool {
    if text.is_empty() || text.len() > 1024 || text.contains('\\') {
        return false;
    }
    let parts: Vec<_> = text.split('/').collect();
    parts.len() <= 64 && parts.iter().all(|part| component(part))
}
fn component(text: &str) -> bool {
    if text.is_empty()
        || matches!(text, "." | "..")
        || text.encode_utf16().count() > 255
        || text.ends_with(['.', ' '])
        || text.chars().any(|c| {
            c.is_control() || matches!(c, ':' | '/' | '\\' | '<' | '>' | '"' | '|' | '?' | '*')
        })
    {
        return false;
    }
    let base = text
        .split('.')
        .next()
        .unwrap_or("")
        .trim_end_matches(' ')
        .to_ascii_uppercase();
    !matches!(
        base.as_str(),
        "CON" | "PRN" | "AUX" | "NUL" | "CLOCK$" | "CONIN$" | "CONOUT$"
    ) && !["COM", "LPT"].iter().any(|prefix| {
        base.strip_prefix(prefix).is_some_and(|n| {
            matches!(
                n,
                "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
            )
        })
    })
}
