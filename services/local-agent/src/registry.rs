use crate::{
    LocalAdmission, ToolCall, ToolError, ToolErrorKind, ToolExecutor, ToolExposure, ToolFuture,
    ToolSpec,
};
use std::{collections::BTreeMap, fmt, sync::Arc};

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

    pub fn has_capability(&self, capability: crate::Capability) -> bool {
        self.admission.capabilities.contains(&capability)
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

#[cfg(test)]
#[path = "registry_tests.rs"]
mod tests;
