//! One-shot explicit native-CI plans; no ToolContext or host constructor fields.
use super::CreationFixture;
use std::{
    collections::HashMap,
    sync::{Mutex, OnceLock},
};

struct RegisteredFixture {
    arguments: serde_json::Value,
    fixture: CreationFixture,
}
static PLANS: OnceLock<Mutex<HashMap<uuid::Uuid, RegisteredFixture>>> = OnceLock::new();

pub(crate) fn register_creation_fixture(
    host: uuid::Uuid,
    arguments: serde_json::Value,
    fixture: CreationFixture,
) -> Result<(), &'static str> {
    coding_tools_cloud_agent::catalog::tool("exec_command")
        .ok_or("WINDOWS_HCS_FIXTURE_ARGUMENTS_REJECTED")?
        .validate(&arguments)
        .map_err(|_| "WINDOWS_HCS_FIXTURE_ARGUMENTS_REJECTED")?;
    if host.is_nil()
        || coding_tools_cloud_agent::catalog::WorkspaceIo::from_arguments(&arguments)
            .map_err(|_| "WINDOWS_HCS_FIXTURE_ARGUMENTS_REJECTED")?
            .is_none()
    {
        return Err("WINDOWS_HCS_FIXTURE_ARGUMENTS_REJECTED");
    }
    let mut plans = PLANS
        .get_or_init(Default::default)
        .lock()
        .map_err(|_| "WINDOWS_HCS_FIXTURE_REGISTRY_UNAVAILABLE")?;
    if plans.len() >= 16 || plans.contains_key(&host) {
        return Err("WINDOWS_HCS_FIXTURE_REGISTRY_UNAVAILABLE");
    }
    plans.insert(host, RegisteredFixture { arguments, fixture });
    Ok(())
}

pub(crate) fn take_creation_fixture(
    host: uuid::Uuid,
    arguments: &serde_json::Value,
) -> Result<Option<CreationFixture>, &'static str> {
    let Some(plans) = PLANS.get() else {
        return Ok(None);
    };
    let mut plans = plans
        .lock()
        .map_err(|_| "WINDOWS_HCS_FIXTURE_REGISTRY_UNAVAILABLE")?;
    let Some(plan) = plans.get(&host) else {
        return Ok(None);
    };
    if &plan.arguments != arguments {
        return Err("WINDOWS_HCS_FIXTURE_ARGUMENTS_REJECTED");
    }
    Ok(plans.remove(&host).map(|plan| plan.fixture))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn arguments() -> serde_json::Value {
        serde_json::json!({"cmd":"Get-Content input.txt", "workspace_io":{
            "input":"input.txt", "output_parent":"results", "output_leaf":"new.txt"}})
    }
    fn data_only_plan() -> CreationFixture {
        // Synthetic metadata only: no native constructor, claim, permit,
        // WorkspaceRunGrant, ComputeCore object or executable owner is made.
        CreationFixture {
            source: "component-no-native-source".into(),
            configuration: vec![0],
            archive_parent: None,
        }
    }
    #[test]
    fn exact_host_and_arguments_selection_is_single_use_data_only() {
        let host = uuid::Uuid::new_v4();
        let args = arguments();
        register_creation_fixture(host, args.clone(), data_only_plan()).unwrap();
        assert!(
            take_creation_fixture(uuid::Uuid::new_v4(), &args)
                .unwrap()
                .is_none()
        );
        let mut mismatch = args.clone();
        mismatch["cmd"] = serde_json::json!("Get-Content another.txt");
        assert!(take_creation_fixture(host, &mismatch).is_err());
        assert!(take_creation_fixture(host, &args).unwrap().is_some());
        assert!(take_creation_fixture(host, &args).unwrap().is_none());
    }
    #[test]
    fn duplicate_host_does_not_replace_the_first_owned_plan() {
        let host = uuid::Uuid::new_v4();
        let args = arguments();
        register_creation_fixture(host, args.clone(), data_only_plan()).unwrap();
        assert!(register_creation_fixture(host, args.clone(), data_only_plan()).is_err());
        assert_eq!(
            take_creation_fixture(host, &args).unwrap().unwrap().source,
            "component-no-native-source"
        );
    }
    #[test]
    fn missing_workspace_intent_and_invalid_arguments_never_select_a_plan() {
        for args in [
            serde_json::json!({"cmd":"echo harmless"}),
            serde_json::json!({"cmd":"echo harmless","workspace_io":{"input":"../escape"}}),
        ] {
            assert!(
                register_creation_fixture(uuid::Uuid::new_v4(), args, data_only_plan()).is_err()
            );
        }
        assert!(
            register_creation_fixture(uuid::Uuid::nil(), arguments(), data_only_plan()).is_err()
        );
    }
}
