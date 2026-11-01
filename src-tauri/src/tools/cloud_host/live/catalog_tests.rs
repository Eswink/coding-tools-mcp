use serde_json::json;

#[test]
fn public_cloud_catalog_matches_native_scope_and_schema_contract() {
    for spec in coding_tools_cloud_agent::catalog::tools() {
        if spec.name == "workspace_probe" {
            continue;
        }
        let native =
            super::super::super::chat_domain::required(&spec.name, &json!({"repair":true}))
                .expect("every cloud tool must have native scope mapping");
        assert_eq!(
            native,
            spec.scopes_for(&json!({"repair":true}))
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            spec.name
        );
        let read = super::super::super::chat_domain::required(&spec.name, &json!({"repair":false}))
            .unwrap();
        assert_eq!(
            read,
            spec.scopes_for(&json!({"repair":false}))
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            spec.name
        );
        let schema = super::super::super::registry::input_schema(&spec.name);
        let properties = schema["properties"].as_object().unwrap();
        for (key, field) in spec.schema["properties"].as_object().unwrap() {
            assert_eq!(
                field["type"], properties[key]["type"],
                "{} {key}",
                spec.name
            );
        }
        assert_eq!(
            spec.schema.get("required"),
            schema.get("required"),
            "{}",
            spec.name
        );
    }
}

/// A1 C2b (SPEC-A1 v4 §3.2): the worker_id variant of both alignment assertions.
/// With `worker_id` both sides add exactly `agents.manage` (never duplicated) on
/// top of the repair-selected base set, and the primary scope is unchanged.
#[test]
fn worker_id_variants_add_agents_manage_on_both_sides_and_keep_the_primary() {
    use super::super::super::chat_domain::scopes;
    let id = "a".repeat(32);
    for spec in coding_tools_cloud_agent::catalog::tools() {
        if spec.name == "workspace_probe" {
            continue;
        }
        for repair in [true, false] {
            let plain = json!({ "repair": repair });
            let with = json!({ "repair": repair, "worker_id": id });
            let cloud = spec.scopes_for(&with);
            let native = scopes(&spec.name, &with).expect("native mapping");
            assert_eq!(
                native,
                cloud.iter().map(String::as_str).collect::<Vec<_>>(),
                "{} repair={repair}",
                spec.name
            );
            assert!(cloud.iter().any(|s| s == "agents.manage"), "{}", spec.name);
            assert_eq!(
                cloud.iter().filter(|s| *s == "agents.manage").count(),
                1,
                "{}",
                spec.name
            );
            assert_eq!(spec.primary_scope(&with), spec.primary_scope(&plain));
            let base = spec.scopes_for(&plain);
            assert!(base.iter().all(|s| cloud.contains(s)), "{}", spec.name);
        }
    }
}

/// The 22 worker tools carry the same opaque worker_id property on both sides;
/// the native schema of every other cloud tool rejects it (additionalProperties).
#[test]
fn worker_id_schema_is_identical_on_both_sides() {
    for spec in coding_tools_cloud_agent::catalog::tools() {
        let native = super::super::super::registry::input_schema(&spec.name);
        assert_eq!(
            spec.schema["properties"].get("worker_id"),
            native["properties"].get("worker_id"),
            "{}",
            spec.name
        );
        assert_eq!(native["additionalProperties"], false, "{}", spec.name);
    }
}
