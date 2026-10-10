//! SDK exit-document validation only. This data cannot issue a retirement seal.
use serde::Deserialize;

pub(super) const MAX_STATUS_BYTES: usize = 65_536;
pub(super) const OPERATION_TIMEOUT: i32 = 0x8037_0118_u32 as i32;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SystemExitStatus {
    #[serde(rename = "Status")]
    status: i32,
    #[serde(rename = "ExitType")]
    exit_type: String,
    #[serde(rename = "Attribution", default)]
    attribution: Vec<serde_json::Value>,
}

/// Called only on the owned allocation returned by the actual SDK whole-exit
/// wait. Guest DATA and portable test JSON are never a native proof producer.
pub(super) fn validate_terminated_status(raw: &str) -> Result<(), &'static str> {
    if raw.is_empty() || raw.len() > MAX_STATUS_BYTES {
        return Err("WINDOWS_HCS_EXIT_DOCUMENT_REJECTED");
    }
    let status: SystemExitStatus =
        serde_json::from_str(raw).map_err(|_| "WINDOWS_HCS_EXIT_DOCUMENT_REJECTED")?;
    if status.status != 0 || status.exit_type != "ForcedExit" || !status.attribution.is_empty() {
        return Err("WINDOWS_HCS_EXIT_STATUS_UNCONFIRMED");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sdk_zero_forced_exit_is_data_validation_only() {
        assert!(validate_terminated_status(r#"{"Status":0,"ExitType":"ForcedExit"}"#).is_ok());
        assert!(validate_terminated_status(
            r#"{"Status":0,"ExitType":"ForcedExit","Attribution":[]}"#
        )
        .is_ok());
    }

    #[test]
    fn missing_duplicate_unknown_and_wrong_status_types_reject() {
        for raw in [
            r#"{"ExitType":"ForcedExit"}"#,
            r#"{"Status":0}"#,
            r#"{"Status":0,"Status":0,"ExitType":"ForcedExit"}"#,
            r#"{"Status":0,"ExitType":"ForcedExit","ExitType":"ForcedExit"}"#,
            r#"{"Status":0,"ExitType":"ForcedExit","owner":true}"#,
            r#"{"Status":"0","ExitType":"ForcedExit"}"#,
            r#"{"Status":0.0,"ExitType":"ForcedExit"}"#,
            r#"{"Status":4294967296,"ExitType":"ForcedExit"}"#,
            r#"{"Status":null,"ExitType":"ForcedExit"}"#,
            r#"{"Status":0,"ExitType":"ForcedExit","Attribution":null}"#,
        ] {
            assert!(validate_terminated_status(raw).is_err(), "{raw}");
        }
    }

    #[test]
    fn failed_unexpected_or_attributed_exit_rejects() {
        for raw in [
            r#"{"Status":-2143878905,"ExitType":"ForcedExit"}"#,
            r#"{"Status":0,"ExitType":"UnexpectedExit"}"#,
            r#"{"Status":0,"ExitType":"GracefulExit"}"#,
            r#"{"Status":0,"ExitType":"Unknown"}"#,
            r#"{"Status":0,"ExitType":"ForcedExit","Attribution":[{}]}"#,
        ] {
            assert!(validate_terminated_status(raw).is_err());
        }
    }

    #[test]
    fn trailing_truncated_and_oversize_documents_reject() {
        for raw in ["", "{", r#"{"Status":0,"ExitType":"ForcedExit"}{}"#] {
            assert!(validate_terminated_status(raw).is_err());
        }
        assert!(validate_terminated_status(&" ".repeat(MAX_STATUS_BYTES + 1)).is_err());
    }
}
