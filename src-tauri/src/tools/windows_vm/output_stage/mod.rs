//! Publication stays denied: no actual closed-VM/all-IO/output issuer exists.
mod gate;
mod nt;
mod owner;
#[cfg(test)] mod tests;
#[cfg(test)] mod native_tests;
pub(crate) fn request_publication(raw_data: &str) -> Result<(), &'static str> {
    // Parsing is bounded data validation. Even valid data cannot make a proof.
    let plan = gate::OutputDataPlan::from_untrusted_data(raw_data)?;
    let _ = gate::approve(plan)?;
    Err("WINDOWS_OUTPUT_ACTUAL_CLOSED_OWNER_REQUIRED")
}
