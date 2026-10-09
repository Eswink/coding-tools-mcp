//! Data and permission are distinct; there is deliberately no proof issuer.
use serde::Deserialize;
use crate::tools::windows_vm::input::owned_run::RunBinding;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DataFields {
    host: String, profile: String, caller: String, source: String,
    session: String, operation: String, input_relative: String,
    output_parent: String, output_leaf: String, bytes: u64, sha256: String,
}
pub(super) struct OutputDataPlan {
    pub(super) binding: RunBinding,
    pub(super) bytes: u64,
    pub(super) sha256: String,
}
impl OutputDataPlan {
    pub fn from_untrusted_data(raw: &str) -> Result<Self, &'static str> {
        if raw.len() > 4096 { return Err("WINDOWS_OUTPUT_DATA_REJECTED"); }
        let data: DataFields = serde_json::from_str(raw).map_err(|_| "WINDOWS_OUTPUT_DATA_REJECTED")?;
        let plan = Self { binding: RunBinding { host: data.host, profile: data.profile,
            caller: data.caller, source: data.source, session: data.session, operation: data.operation,
            input_relative: data.input_relative, output_parent: data.output_parent, output_leaf: data.output_leaf },
            bytes: data.bytes, sha256: data.sha256 };
        super::nt::validate_output_data(&plan)?;
        Ok(plan)
    }
}
pub(super) fn approve(_plan: OutputDataPlan)
    -> Result<super::owner::OwnedOutputPublication, &'static str> {
    Err("WINDOWS_OUTPUT_ACTUAL_CLOSED_OWNER_REQUIRED")
}
