//! Explicit engineering fixture, never a production image or execution grant.
use serde::Deserialize;
use sha2::{Digest, Sha256};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Version {
    #[serde(rename = "Major")]
    major: u32,
    #[serde(rename = "Minor")]
    minor: u32,
}
// Deliberately finite data only. No device, boot, disk, GuestState, host path or
// image field is admitted without a later actual owned asset producer.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct EmptyTopology {}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct VirtualMachineData {
    #[serde(rename = "ComputeTopology")]
    _topology: EmptyTopology,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Configuration {
    #[serde(rename = "Owner")]
    owner: String,
    #[serde(rename = "SchemaVersion")]
    version: Version,
    #[serde(rename = "VirtualMachine")]
    _vm: VirtualMachineData,
    #[serde(rename = "ShouldTerminateOnLastHandleClosed")]
    terminate_on_close: bool,
}

/// Non-Clone, non-Deserialize owned configuration. This object does not contain
/// permission and is useless without the real native claim and committed grant.
pub(crate) struct CreationFixture {
    pub(super) source: String,
    pub(super) configuration: Vec<u16>,
    pub(super) archive_parent: Option<String>,
}

fn validate_configuration(raw: &str, expected_hash: &str) -> Result<(), &'static str> {
    if raw.is_empty()
        || raw.len() > 65_536
        || raw.contains('\0')
        || expected_hash.len() != 64
        || !expected_hash
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || format!("{:x}", Sha256::digest(raw.as_bytes())) != expected_hash
    {
        return Err("WINDOWS_HCS_FIXTURE_CONFIGURATION_REJECTED");
    }
    let parsed: Configuration =
        serde_json::from_str(raw).map_err(|_| "WINDOWS_HCS_FIXTURE_CONFIGURATION_REJECTED")?;
    if parsed.owner != "ctm-created-owner-ci"
        || parsed.version.major != 2
        || parsed.version.minor != 1
        || !parsed.terminate_on_close
    {
        return Err("WINDOWS_HCS_FIXTURE_CONFIGURATION_REJECTED");
    }
    Ok(())
}

impl CreationFixture {
    /// Selects read-only archive data for the actual claimed owner. It cannot
    /// construct a permission, boot resource or HCS creation capability.
    pub(crate) fn for_current_disposable_runner_with_archives(
        configuration: String,
        expected_hash: &str,
        archive_parent: String,
    ) -> Result<Self, &'static str> {
        let source = crate::tools::windows_vm::input::native_source()?;
        if std::env::var("GITHUB_ACTIONS").as_deref() != Ok("true")
            || std::env::var("RUNNER_OS").as_deref() != Ok("Windows")
            || std::env::var("GITHUB_SHA").as_deref() != Ok(source)
            || std::env::var("CTM_CREATION_OWNER_NATIVE").as_deref()
                != Ok("APPROVED_DISPOSABLE_RUNNER_ONLY")
        {
            return Err("WINDOWS_HCS_NATIVE_FIXTURE_HELD");
        }
        validate_configuration(&configuration, expected_hash)?;
        super::super::super::path::components(&archive_parent)?;
        Ok(Self {
            source: source.into(),
            configuration: configuration.encode_utf16().chain(Some(0)).collect(),
            archive_parent: Some(archive_parent),
        })
    }
    /// Only explicit future disposable native CI callers can attach this plan.
    /// The caller must separately pin its approved image/assets and runner.
    /// This gate and hash are provenance constraints, never image authority.
    pub(crate) fn for_current_disposable_runner(
        configuration: String,
        expected_hash: &str,
    ) -> Result<Self, &'static str> {
        let source = crate::tools::windows_vm::input::native_source()?;
        if std::env::var("GITHUB_ACTIONS").as_deref() != Ok("true")
            || std::env::var("RUNNER_OS").as_deref() != Ok("Windows")
            || std::env::var("GITHUB_SHA").as_deref() != Ok(source)
            || std::env::var("CTM_CREATION_OWNER_NATIVE").as_deref()
                != Ok("APPROVED_DISPOSABLE_RUNNER_ONLY")
        {
            return Err("WINDOWS_HCS_NATIVE_FIXTURE_HELD");
        }
        validate_configuration(&configuration, expected_hash)?;
        // Source/env/hash constrain provenance only. No actual opened/pinned
        // image/asset owner exists yet, so none can authorize a native launch.
        Err("WINDOWS_HCS_FIXTURE_ASSET_OWNER_UNPROVEN")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> String {
        r#"{"Owner":"ctm-created-owner-ci","SchemaVersion":{"Major":2,"Minor":1},"VirtualMachine":{"ComputeTopology":{}},"ShouldTerminateOnLastHandleClosed":true}"#.into()
    }
    fn hash(raw: &str) -> String {
        format!("{:x}", Sha256::digest(raw.as_bytes()))
    }

    #[test]
    fn finite_hash_bound_configuration_is_data_only() {
        let raw = config();
        assert!(validate_configuration(&raw, &hash(&raw)).is_ok());
        assert!(validate_configuration(&raw, &"0".repeat(64)).is_err());
        assert!(validate_configuration(&raw, &hash(&raw).to_uppercase()).is_err());
    }
    #[test]
    fn configuration_cannot_attach_existing_system_or_external_interfaces() {
        for value in [
            "MappedDirectories",
            "MappedPipes",
            "NetworkAdapters",
            "Networking",
            "HostingSystemId",
            "HostedSystem",
            "Container",
            "GuestConnection",
            "HvSocket",
        ] {
            let raw = config().replace("\"ComputeTopology\":{}", &format!("\"{value}\":{{}}"));
            assert!(
                validate_configuration(&raw, &hash(&raw)).is_err(),
                "{value}"
            );
        }
        let raw = config().replace("\"Owner\":", "\"Unexpected\":");
        assert!(validate_configuration(&raw, &hash(&raw)).is_err());
    }
    #[test]
    fn duplicate_missing_nul_and_oversize_configuration_rejects() {
        for raw in [
            config().replace("\"Major\":2", "\"Major\":2,\"Major\":2"),
            config().replace(",\"ShouldTerminateOnLastHandleClosed\":true", ""),
            config().replace("\"Minor\":1", "\"Minor\":99"),
            config().replace("true", "false"),
            config() + "\0",
            " ".repeat(65_537),
        ] {
            assert!(validate_configuration(&raw, &hash(&raw)).is_err());
        }
    }
}

#[cfg(test)]
mod review_regressions {
    use super::*;
    fn hashed(raw: &str) -> String {
        format!("{:x}", Sha256::digest(raw.as_bytes()))
    }
    #[test]
    fn repeated_devices_cannot_hide_network_adapter_before_raw_submit() {
        let raw = r#"{"Owner":"ctm-created-owner-ci","SchemaVersion":{"Major":2,"Minor":1},"VirtualMachine":{"Devices":{"NetworkAdapters":[]},"Devices":{}},"ShouldTerminateOnLastHandleClosed":true}"#;
        assert!(
            validate_configuration(raw, &hashed(raw)).is_err(),
            "actual source currently folds first forbidden Devices before submitting raw"
        );
    }
    #[test]
    fn repeated_vm_compute_topology_rejects_even_when_values_equal() {
        let raw = r#"{"Owner":"ctm-created-owner-ci","SchemaVersion":{"Major":2,"Minor":1},"VirtualMachine":{"ComputeTopology":{},"ComputeTopology":{}},"ShouldTerminateOnLastHandleClosed":true}"#;
        assert!(validate_configuration(raw, &hashed(raw)).is_err());
    }
}
