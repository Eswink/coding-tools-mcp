use serde::de::DeserializeOwned;
use serde_json::Value;
use std::{
    collections::BTreeSet,
    error::Error,
    fmt,
};

pub const MAX_SCHEMA_BYTES: usize = 16 * 1024;
pub const MAX_CALL_ID_BYTES: usize = 128;
pub const MAX_CONTEXT_ID_BYTES: usize = 256;
pub const MAX_INPUT_BYTES: usize = 64 * 1024;
pub const MAX_OUTPUT_BYTES: usize = 1024 * 1024;

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct ToolName(String);

impl ToolName {
    pub fn parse(value: impl Into<String>) -> Result<Self, ToolError> {
        let value = value.into();
        let valid = !value.is_empty()
            && value.len() <= 64
            && value.as_bytes()[0].is_ascii_lowercase()
            && value
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_');
        if !valid {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "invalid tool name",
            ));
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for ToolName {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Capability {
    WorkspaceRead,
    WorkspaceWrite,
    ProcessExec,
    GitWrite,
    Network,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ToolExposure {
    Direct,
    Deferred,
    Hidden,
}

#[derive(Clone, Debug)]
pub struct ToolSpec {
    pub name: ToolName,
    pub description: String,
    pub input_schema: Value,
    pub exposure: ToolExposure,
    pub required_capabilities: BTreeSet<Capability>,
    pub max_input_bytes: usize,
    pub max_output_bytes: usize,
}

impl ToolSpec {
    pub fn new(
        name: ToolName,
        description: impl Into<String>,
        input_schema: Value,
    ) -> Result<Self, ToolError> {
        let description = description.into();
        if description.is_empty()
            || description.len() > 512
            || description.chars().any(char::is_control)
            || !input_schema.is_object()
        {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "invalid tool specification",
            ));
        }
        let schema_bytes = serde_json::to_vec(&input_schema)
            .map_err(|_| ToolError::new(ToolErrorKind::InvalidInput, "invalid schema"))?;
        if schema_bytes.len() > MAX_SCHEMA_BYTES {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "schema too large",
            ));
        }
        Ok(Self {
            name,
            description,
            input_schema,
            exposure: ToolExposure::Direct,
            required_capabilities: BTreeSet::new(),
            max_input_bytes: MAX_INPUT_BYTES,
            max_output_bytes: MAX_OUTPUT_BYTES,
        })
    }

    pub fn exposure(mut self, exposure: ToolExposure) -> Self {
        self.exposure = exposure;
        self
    }

    pub fn require(mut self, capability: Capability) -> Self {
        self.required_capabilities.insert(capability);
        self
    }

    pub fn limits(
        mut self,
        max_input_bytes: usize,
        max_output_bytes: usize,
    ) -> Result<Self, ToolError> {
        if max_input_bytes == 0
            || max_input_bytes > MAX_INPUT_BYTES
            || max_output_bytes == 0
            || max_output_bytes > MAX_OUTPUT_BYTES
        {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "invalid tool limits",
            ));
        }
        self.max_input_bytes = max_input_bytes;
        self.max_output_bytes = max_output_bytes;
        Ok(self)
    }
}

#[derive(Clone)]
pub struct ToolCall {
    pub request_id: String,
    pub conversation_id: String,
    pub workspace_id: String,
    pub tool_name: ToolName,
    pub arguments: Value,
}

impl ToolCall {
    pub fn new(
        request_id: impl Into<String>,
        conversation_id: impl Into<String>,
        workspace_id: impl Into<String>,
        tool_name: ToolName,
        arguments: Value,
    ) -> Result<Self, ToolError> {
        let request_id = bounded_id(request_id.into(), MAX_CALL_ID_BYTES)?;
        let conversation_id = bounded_id(conversation_id.into(), MAX_CONTEXT_ID_BYTES)?;
        let workspace_id = bounded_id(workspace_id.into(), MAX_CONTEXT_ID_BYTES)?;
        if !arguments.is_object() {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "tool arguments must be an object",
            ));
        }
        Ok(Self {
            request_id,
            conversation_id,
            workspace_id,
            tool_name,
            arguments,
        })
    }
}

impl fmt::Debug for ToolCall {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ToolCall")
            .field("request_id", &self.request_id)
            .field("conversation_id", &"<opaque>")
            .field("workspace_id", &"<opaque>")
            .field("tool_name", &self.tool_name)
            .field("arguments", &"<redacted>")
            .finish()
    }
}

fn bounded_id(value: String, max: usize) -> Result<String, ToolError> {
    if value.is_empty() || value.len() > max || value.chars().any(char::is_control) {
        return Err(ToolError::new(
            ToolErrorKind::InvalidInput,
            "invalid invocation identity",
        ));
    }
    Ok(value)
}

/// Opaque local execution authority.
///
/// It is intentionally not serializable or deserializable. The first shared
/// runtime increment exposes no public constructor; the local authority bridge
/// will own construction in a later integration issue.
pub struct LocalAdmission {
    pub(crate) conversation_id: String,
    pub(crate) workspace_id: String,
    pub(crate) capabilities: BTreeSet<Capability>,
    pub(crate) generation: u64,
    pub(crate) expires_at_unix_ms: u64,
}

impl fmt::Debug for LocalAdmission {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("LocalAdmission")
            .field("identity", &"<local-authority>")
            .field("generation", &self.generation)
            .field("expires_at_unix_ms", &self.expires_at_unix_ms)
            .finish()
    }
}

#[cfg(test)]
impl LocalAdmission {
    pub(crate) fn fixture(
        conversation_id: &str,
        workspace_id: &str,
        capabilities: impl IntoIterator<Item = Capability>,
        generation: u64,
        expires_at_unix_ms: u64,
    ) -> Self {
        Self {
            conversation_id: conversation_id.into(),
            workspace_id: workspace_id.into(),
            capabilities: capabilities.into_iter().collect(),
            generation,
            expires_at_unix_ms,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ToolErrorKind {
    InvalidInput,
    Unauthorized,
    CapabilityDenied,
    NotFound,
    ExecutorMismatch,
    OutputTooLarge,
    Execution,
}

#[derive(Clone)]
pub struct ToolError {
    pub kind: ToolErrorKind,
    message: &'static str,
}

impl ToolError {
    pub const fn new(kind: ToolErrorKind, message: &'static str) -> Self {
        Self { kind, message }
    }

    pub fn public_message(&self) -> &'static str {
        self.message
    }
}

impl fmt::Debug for ToolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ToolError")
            .field("kind", &self.kind)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for ToolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message)
    }
}

impl Error for ToolError {}

#[derive(Clone)]
pub enum ToolOutput {
    Text {
        text: String,
        truncated: bool,
        original_bytes: usize,
    },
    Json(Value),
}

impl ToolOutput {
    pub fn text(mut text: String, max_bytes: usize) -> Result<Self, ToolError> {
        if max_bytes == 0 || max_bytes > MAX_OUTPUT_BYTES {
            return Err(ToolError::new(
                ToolErrorKind::InvalidInput,
                "invalid output limit",
            ));
        }
        let original_bytes = text.len();
        let truncated = original_bytes > max_bytes;
        if truncated {
            let mut end = max_bytes.min(text.len());
            while !text.is_char_boundary(end) {
                end -= 1;
            }
            text.truncate(end);
        }
        Ok(Self::Text {
            text,
            truncated,
            original_bytes,
        })
    }

    pub fn json(value: Value) -> Self {
        Self::Json(value)
    }

    pub fn encoded_len(&self) -> Result<usize, ToolError> {
        match self {
            Self::Text { text, .. } => Ok(text.len()),
            Self::Json(value) => serde_json::to_vec(value)
                .map(|v| v.len())
                .map_err(|_| ToolError::new(ToolErrorKind::Execution, "output encoding failed")),
        }
    }
}

impl fmt::Debug for ToolOutput {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Text {
                text,
                truncated,
                original_bytes,
            } => f
                .debug_struct("ToolOutput::Text")
                .field("bytes", &text.len())
                .field("truncated", truncated)
                .field("original_bytes", original_bytes)
                .finish(),
            Self::Json(value) => f
                .debug_struct("ToolOutput::Json")
                .field(
                    "bytes",
                    &serde_json::to_vec(value).map(|v| v.len()).unwrap_or(usize::MAX),
                )
                .finish(),
        }
    }
}

pub fn parse_arguments<T: DeserializeOwned>(value: &Value, max_bytes: usize) -> Result<T, ToolError> {
    if max_bytes == 0 || max_bytes > MAX_INPUT_BYTES {
        return Err(ToolError::new(
            ToolErrorKind::InvalidInput,
            "invalid input limit",
        ));
    }
    let bytes = serde_json::to_vec(value)
        .map_err(|_| ToolError::new(ToolErrorKind::InvalidInput, "invalid arguments"))?;
    if bytes.len() > max_bytes {
        return Err(ToolError::new(
            ToolErrorKind::InvalidInput,
            "tool input too large",
        ));
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| ToolError::new(ToolErrorKind::InvalidInput, "invalid arguments"))
}
