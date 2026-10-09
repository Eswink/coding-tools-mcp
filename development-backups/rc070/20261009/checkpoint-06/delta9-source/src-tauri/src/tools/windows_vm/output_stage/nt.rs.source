//! Data prerequisites only. No unsafe open/create/write/rename/delete API yet.
//! Native writer requires a separately implemented actual closed owner issuer.
pub(super) fn validate_output_data(plan: &super::gate::OutputDataPlan) -> Result<(), &'static str> {
    if !plan.binding.valid() || plan.bytes > 1_048_576 || plan.sha256.len() != 64
        || !plan.sha256.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
        return Err("WINDOWS_OUTPUT_DATA_REJECTED");
    }
    Ok(())
}
