use super::*;
use serde_json::json;
use std::collections::BTreeSet;

#[test]
fn complete_catalog_is_closed_unique_and_has_only_native_scopes() {
    let specs = tools();
    assert_eq!(specs.len(), 47);
    assert_eq!(
        specs.iter().map(|s| &s.name).collect::<BTreeSet<_>>().len(),
        specs.len()
    );
    for spec in specs {
        assert!(!spec.scopes.is_empty());
        assert!(spec
            .scopes
            .iter()
            .all(|s| crate::grant::LOCAL_SCOPES.contains(&s.as_str())));
        assert_eq!(spec.schema["type"], "object");
        assert_eq!(spec.schema["additionalProperties"], false);
        for forbidden in [
            "workspace_root",
            "sandbox",
            "env",
            "environment",
            "authorized",
            "_meta",
            "cloud",
        ] {
            assert!(
                spec.schema["properties"].get(forbidden).is_none(),
                "{} {forbidden}",
                spec.name
            );
        }
    }
    for forbidden in [
        "request_permissions",
        "approve",
        "revoke",
        "delete_workspace",
        "unknown",
    ] {
        assert!(tool(forbidden).is_none());
    }
}

#[test]
fn arguments_are_strict_bounded_and_defaults_are_digest_stable() {
    let spec = tool("read_file").unwrap();
    let a = spec.arguments(&json!({"path":"file.rs"})).unwrap();
    assert_eq!(a["max_bytes"], 2048);
    assert_eq!(spec.arguments(&a).unwrap(), a);
    for args in [
        json!(null),
        json!([]),
        json!({}),
        json!({"path":1}),
        json!({"path":""}),
        json!({"path":"x","max_bytes":2049}),
        json!({"path":"x","max_bytes":1.5}),
        json!({"path":"x","start_line":-1}),
        json!({"path":"x","env":{}}),
        json!({"path":"x","_meta":{"authorized":true}}),
        json!({"path":"a".repeat(4096)}),
    ] {
        assert!(spec.arguments(&args).is_err(), "{args}");
    }
}

#[test]
fn workspace_paths_cannot_choose_another_root() {
    for path in [
        "/etc/passwd",
        "../outside",
        "dir/../../outside",
        "C:/Windows",
        r"..\outside",
        "file\u{0}",
    ] {
        assert!(
            tool("read_file")
                .unwrap()
                .arguments(&json!({"path":path}))
                .is_err(),
            "{path}"
        );
        assert!(
            tool("git_diff")
                .unwrap()
                .arguments(&json!({"paths":[path]}))
                .is_err(),
            "{path}"
        );
    }
    assert!(tool("read_file")
        .unwrap()
        .arguments(&json!({"path":"src/main.rs"}))
        .is_ok());
}

#[test]
fn multi_scope_and_mutation_classes_are_conservative() {
    assert_eq!(
        tool("write_stdin").unwrap().scopes,
        ["task.manage", "exec.run"]
    );
    assert_eq!(
        tool("history_session_validate").unwrap().scopes,
        ["history.write"]
    );
    for name in [
        "apply_patch",
        "start_exec_task",
        "set_default_cwd",
        "write_stdin",
        "history_session_validate",
        "start_task",
    ] {
        assert!(tool(name).unwrap().mutating, "{name}");
    }
    for name in [
        "read_file",
        "list_dir",
        "git_status",
        "get_exec_task",
        "history_session_read",
    ] {
        assert!(!tool(name).unwrap().mutating, "{name}");
    }
}

#[test]
fn every_schema_default_validates_and_never_adds_authority() {
    for spec in tools() {
        for field in spec.schema["properties"].as_object().unwrap().values() {
            if let Some(default) = field.get("default") {
                assert!(matches_schema(field, default, 0), "{} {field}", spec.name);
            }
        }
    }
    assert!(tool("exec_command")
        .unwrap()
        .arguments(&json!({"cmd":"echo hi","filesystem_scope":"host"}))
        .is_err());
    assert!(tool("history_session_bootstrap")
        .unwrap()
        .arguments(&json!({"workspace_root":"/"}))
        .is_err());
}

#[test]
fn history_validation_is_least_scope_and_bound_to_repair_argument() {
    let spec = tool("history_session_validate").unwrap();
    for args in [json!({}), json!({"repair":false})] {
        assert_eq!(spec.primary_scope(&args), "history.read");
        assert!(!spec.is_mutating(&args));
    }
    assert_eq!(spec.primary_scope(&json!({"repair":true})), "history.write");
    assert!(spec.is_mutating(&json!({"repair":true})));
}

#[test]
fn worktree_tools_accept_only_opaque_identity_and_existing_local_scopes() {
    for name in ["worktree_create", "worktree_list"] {
        assert!(tool(name).unwrap().arguments(&json!({})).is_ok());
        for args in [
            json!({"path":"."}),
            json!({"root":"/"}),
            json!({"ref":"HEAD"}),
            json!({"argv":[]}),
        ] {
            assert!(tool(name).unwrap().arguments(&args).is_err());
        }
    }
    let remove = tool("worktree_remove").unwrap();
    assert_eq!(remove.scopes, ["files.write"]);
    assert!(remove.mutating);
    assert_eq!(tool("worktree_list").unwrap().scopes, ["workspace.read"]);
    assert!(remove.arguments(&json!({"id":"a".repeat(32)})).is_ok());
    for id in [
        "../outside".to_string(),
        "A".repeat(32),
        "g".repeat(32),
        "a".repeat(31),
        "a".repeat(33),
    ] {
        assert!(remove.arguments(&json!({"id":id})).is_err());
    }
    assert!(remove
        .arguments(&json!({"id":"a".repeat(32),"force":true}))
        .is_err());
}
