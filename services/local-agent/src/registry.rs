use crate::{
    Capability, LocalAdmission, ToolCall, ToolError, ToolErrorKind, ToolExecutor, ToolExposure,
    ToolFuture, ToolSpec,
};
use serde_json::json;
use std::{collections::BTreeMap, fmt, sync::Arc};

pub const MAX_DEFERRED_DISCOVERY_TOOLS: usize = 64;
pub const MAX_DEFERRED_DISCOVERY_BYTES: usize = 256 * 1024;

pub struct DeferredToolCatalog {
    specs: Vec<ToolSpec>,
    metadata_bytes: usize,
    omitted: bool,
}

impl DeferredToolCatalog {
    pub fn specs(&self) -> &[ToolSpec] {
        &self.specs
    }

    pub fn metadata_bytes(&self) -> usize {
        self.metadata_bytes
    }

    pub fn omitted(&self) -> bool {
        self.omitted
    }
}

impl fmt::Debug for DeferredToolCatalog {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("DeferredToolCatalog")
            .field("count", &self.specs.len())
            .field("metadata_bytes", &self.metadata_bytes)
            .field("omitted", &self.omitted)
            .finish()
    }
}

/// Proof that a ToolCall passed the local registry admission checks.
///
/// The field is private and the type has no public constructor or Clone/Copy
/// implementation, so safe external callers cannot manufacture or reuse it to
/// invoke ToolExecutor directly.
pub struct VerifiedInvocation<'a> {
    admission: &'a LocalAdmission,
}

impl VerifiedInvocation<'_> {
    pub fn generation(&self) -> u64 {
        self.admission.generation
    }

    pub fn expires_at_unix_ms(&self) -> u64 {
        self.admission.expires_at_unix_ms
    }
}

#[cfg(test)]
impl<'a> VerifiedInvocation<'a> {
    pub(crate) fn fixture(admission: &'a LocalAdmission) -> Self {
        Self { admission }
    }
}

impl fmt::Debug for VerifiedInvocation<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("VerifiedInvocation")
            .field("authority", &"<local-admission>")
            .field("generation", &self.admission.generation)
            .finish()
    }
}

#[derive(Default)]
pub struct ToolRegistry {
    tools: BTreeMap<String, RegisteredTool>,
}

struct RegisteredTool {
    spec: ToolSpec,
    executor: Arc<dyn ToolExecutor>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, executor: Arc<dyn ToolExecutor>) -> Result<(), ToolError> {
        let runtime_name = executor.tool_name();
        let spec = executor.spec();
        if runtime_name != spec.name {
            return Err(ToolError::new(
                ToolErrorKind::ExecutorMismatch,
                "tool executor/spec mismatch",
            ));
        }
        let key = spec.name.as_str().to_owned();
        if self.tools.contains_key(&key) {
            return Err(ToolError::new(
                ToolErrorKind::ExecutorMismatch,
                "duplicate tool name",
            ));
        }
        self.tools.insert(key, RegisteredTool { spec, executor });
        Ok(())
    }

    pub fn direct_specs(&self) -> Vec<ToolSpec> {
        self.tools
            .values()
            .filter(|entry| entry.spec.exposure == ToolExposure::Direct)
            .map(|entry| entry.spec.clone())
            .collect()
    }

    pub fn deferred_specs(&self) -> Vec<ToolSpec> {
        self.tools
            .values()
            .filter(|entry| entry.spec.exposure == ToolExposure::Deferred)
            .map(|entry| entry.spec.clone())
            .collect()
    }

    pub fn discover_deferred(&self) -> DeferredToolCatalog {
        let mut specs = Vec::new();
        let mut metadata_bytes = 2usize;
        let mut omitted = false;

        for entry in self
            .tools
            .values()
            .filter(|entry| entry.spec.exposure == ToolExposure::Deferred)
        {
            let encoded = discovery_metadata_bytes(&entry.spec);
            let separator = usize::from(!specs.is_empty());
            if specs.len() >= MAX_DEFERRED_DISCOVERY_TOOLS
                || metadata_bytes
                    .saturating_add(separator)
                    .saturating_add(encoded)
                    > MAX_DEFERRED_DISCOVERY_BYTES
            {
                omitted = true;
                break;
            }
            metadata_bytes += separator + encoded;
            specs.push(entry.spec.clone());
        }

        DeferredToolCatalog {
            specs,
            metadata_bytes,
            omitted,
        }
    }

    pub fn all_specs(&self) -> Vec<ToolSpec> {
        self.tools
            .values()
            .map(|entry| entry.spec.clone())
            .collect()
    }

    pub fn supports_parallel_calls(&self, name: &str) -> Option<bool> {
        self.tools
            .get(name)
            .map(|entry| entry.executor.supports_parallel_calls())
    }

    pub fn invoke<'a>(
        &'a self,
        call: &'a ToolCall,
        admission: &'a LocalAdmission,
        now_unix_ms: u64,
    ) -> ToolFuture<'a> {
        Box::pin(async move {
            let Some(entry) = self.tools.get(call.tool_name.as_str()) else {
                return Err(ToolError::new(ToolErrorKind::NotFound, "unknown tool"));
            };
            if call.conversation_id != admission.conversation_id
                || call.workspace_id != admission.workspace_id
                || now_unix_ms > admission.expires_at_unix_ms
            {
                return Err(ToolError::new(
                    ToolErrorKind::Unauthorized,
                    "local admission rejected",
                ));
            }
            if !entry
                .spec
                .required_capabilities
                .is_subset(&admission.capabilities)
            {
                return Err(ToolError::new(
                    ToolErrorKind::CapabilityDenied,
                    "local capability denied",
                ));
            }
            let input_len = serde_json::to_vec(&call.arguments)
                .map_err(|_| ToolError::new(ToolErrorKind::InvalidInput, "invalid arguments"))?
                .len();
            if input_len > entry.spec.max_input_bytes {
                return Err(ToolError::new(
                    ToolErrorKind::InvalidInput,
                    "tool input too large",
                ));
            }

            let verified = VerifiedInvocation { admission };
            let output = entry.executor.execute(call, verified).await?;
            if output.encoded_len()? > entry.spec.max_output_bytes {
                return Err(ToolError::new(
                    ToolErrorKind::OutputTooLarge,
                    "tool output too large",
                ));
            }
            Ok(output)
        })
    }
}

fn discovery_metadata_bytes(spec: &ToolSpec) -> usize {
    let capabilities = spec
        .required_capabilities
        .iter()
        .map(|capability| match capability {
            Capability::WorkspaceRead => "workspace_read",
            Capability::WorkspaceWrite => "workspace_write",
            Capability::ProcessExec => "process_exec",
            Capability::GitWrite => "git_write",
            Capability::Network => "network",
        })
        .collect::<Vec<_>>();
    serde_json::to_vec(&json!({
        "name": spec.name.as_str(),
        "description": &spec.description,
        "input_schema": &spec.input_schema,
        "required_capabilities": capabilities,
        "max_input_bytes": spec.max_input_bytes,
        "max_output_bytes": spec.max_output_bytes,
    }))
    .expect("validated ToolSpec metadata is JSON-encodable")
    .len()
}

#[cfg(test)]
#[path = "registry_tests.rs"]
mod tests;
