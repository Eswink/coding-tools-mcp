use serde_json::{json, Value};

use crate::tools::context::ToolContext;

/// Platform-aware envelope around the single production dispatcher.
///
/// Execution, policy and side effects remain in `dispatch::call_tool`; this
/// layer only attaches authoritative host semantics to the two discovery
/// tools so clients do not infer Windows commands on Linux (or vice versa).
pub fn call_tool(ctx: &ToolContext, name: &str, args: &Value) -> Value {
    let mut result = crate::tools::dispatch::call_tool(ctx, name, args);
    if matches!(name, "server_info" | "check_exec_environment") {
        attach_host_context(&mut result);
    }
    result
}

fn attach_host_context(result: &mut Value) {
    let Some(object) = result.as_object_mut() else { return; };
    let host = crate::platform::context();
    object.insert(
        "host".into(),
        serde_json::to_value(host).unwrap_or_else(|_| json!({
            "os": crate::platform::platform().os_name(),
            "commandExecution": "direct-argv"
        })),
    );
    object.insert(
        "command_input_semantics".into(),
        Value::String("direct argv by default; invoke an explicit host shell for pipes, redirects, variables, globs, chaining, or other shell syntax".into()),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovery_envelope_exposes_authoritative_host_semantics() {
        let mut value = json!({"ok": true, "server": "fixture"});
        attach_host_context(&mut value);
        assert_eq!(value["host"]["arch"], std::env::consts::ARCH);
        assert_eq!(value["host"]["commandExecution"], "direct-argv");
        #[cfg(target_os = "windows")]
        {
            assert_eq!(value["host"]["os"], "windows");
            assert_eq!(value["host"]["pathStyle"], "windows");
            assert!(value["host"]["shellModes"].as_array().unwrap().iter().any(|v| v == "powershell"));
        }
        #[cfg(target_os = "linux")]
        {
            assert_eq!(value["host"]["os"], "linux");
            assert_eq!(value["host"]["pathStyle"], "posix");
            assert!(value["host"]["shellModes"].as_array().unwrap().iter().any(|v| v == "sh"));
            assert!(value["host"]["commandGuidance"].as_str().unwrap().contains("Do not emit cmd.exe"));
        }
    }
}
