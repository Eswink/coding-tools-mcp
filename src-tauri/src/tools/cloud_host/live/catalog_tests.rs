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
