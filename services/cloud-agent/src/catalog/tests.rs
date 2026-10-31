use super::*;
use serde_json::json;
use std::collections::BTreeSet;

#[test]
fn complete_catalog_is_closed_unique_and_has_only_native_scopes() {
    let specs = tools();
    // A1 C2b (SPEC-A1 v4 §2.1): 47 + 7 subagent_* tools.
    assert_eq!(specs.len(), 54);
    assert_eq!(
        specs.iter().map(|s| &s.name).collect::<BTreeSet<_>>().len(),
        specs.len()
    );
    for spec in specs {
        assert!(!spec.scopes.is_empty());
        // A1 C6: every declared scope (agents.manage included) is grantable.
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

const WORKER_ID_TOOLS: [&str; 22] = [
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_blame",
    "check_exec_environment",
    "get_default_cwd",
    "set_default_cwd",
    "change_summary",
    "read_file",
    "list_dir",
    "list_files",
    "search_text",
    "grep_text",
    "grep",
    "view_image",
    "patch_check",
    "apply_patch",
    "exec_command",
    "exec_health_check",
    "start_exec_task",
    "list_exec_tasks",
];

#[test]
fn agents_manage_is_grantable_since_c6() {
    let scopes = crate::grant::LOCAL_SCOPES;
    assert_eq!(scopes.len(), 10);
    assert_eq!(scopes.last(), Some(&"agents.manage"));
    assert!(tools()
        .iter()
        .any(|t| t.scopes.iter().any(|s| s == "agents.manage")));
}

#[test]
fn subagent_tools_match_the_spec_table() {
    for (name, scopes, mutating) in [
        (
            "subagent_spawn",
            &["agents.manage", "files.write"][..],
            true,
        ),
        ("subagent_status", &["agents.manage"][..], false),
        (
            "subagent_collect",
            &["agents.manage", "files.read"][..],
            false,
        ),
        (
            "subagent_cancel",
            &["agents.manage", "task.manage"][..],
            true,
        ),
        (
            "subagent_integrate",
            &["agents.manage", "files.write"][..],
            true,
        ),
        (
            "subagent_rollback",
            &["agents.manage", "files.write"][..],
            true,
        ),
        (
            "subagent_discard",
            &["agents.manage", "files.write"][..],
            true,
        ),
    ] {
        let spec = tool(name).unwrap_or_else(|| panic!("{name}"));
        assert_eq!(spec.scopes, scopes, "{name}");
        assert_eq!(spec.mutating, mutating, "{name}");
        assert!(spec.read_scopes.is_none(), "{name}");
        assert_eq!(spec.primary_scope(&json!({})), "agents.manage", "{name}");
    }
    let id = "a".repeat(32);
    let sha = "0".repeat(64);
    let spawn = tool("subagent_spawn").unwrap();
    assert!(spawn.arguments(&json!({"request_id":"r"})).is_ok());
    assert!(spawn
        .arguments(&json!({"request_id":"r","label":"x","base":"HEAD"}))
        .is_ok());
    for bad in [
        json!({}),
        json!({"request_id":""}),
        json!({"request_id":"r".repeat(129)}),
        json!({"request_id":"r","label":"l".repeat(81)}),
        json!({"request_id":"r","base":"main"}),
        json!({"request_id":"r","worker_id":id}),
        json!({"request_id":"r","path":"."}),
    ] {
        assert!(spawn.arguments(&bad).is_err(), "{bad}");
    }
    let status = tool("subagent_status").unwrap();
    assert!(status.arguments(&json!({})).is_ok());
    assert!(status.arguments(&json!({"worker_id":id})).is_ok());
    assert!(status
        .arguments(&json!({"worker_id":"A".repeat(32)}))
        .is_err());
    let collect = tool("subagent_collect").unwrap();
    let defaulted = collect.arguments(&json!({"worker_id":id})).unwrap();
    assert_eq!(defaulted["max_bytes"], 4096);
    for bad in [
        json!({}),
        json!({"worker_id":id,"max_bytes":255}),
        json!({"worker_id":id,"max_bytes":4097}),
        json!({"worker_id":id,"cursor":""}),
        json!({"worker_id":id,"cursor":7}),
        json!({"worker_id":id,"cursor":"c".repeat(257)}),
    ] {
        assert!(collect.arguments(&bad).is_err(), "{bad}");
    }
    assert!(collect
        .arguments(&json!({"worker_id":id,"cursor":"djE6"}))
        .is_ok());
    let integrate = tool("subagent_integrate").unwrap();
    assert!(integrate
        .arguments(&json!({"worker_id":id,"diff_sha256":sha,"request_id":"r"}))
        .is_ok());
    for bad in [
        json!({"worker_id":id,"request_id":"r"}),
        json!({"worker_id":id,"diff_sha256":"0".repeat(63),"request_id":"r"}),
        json!({"worker_id":id,"diff_sha256":"G".repeat(64),"request_id":"r"}),
        json!({"worker_id":id,"diff_sha256":sha}),
    ] {
        assert!(integrate.arguments(&bad).is_err(), "{bad}");
    }
    let rollback = tool("subagent_rollback").unwrap();
    assert!(rollback
        .arguments(&json!({"integration_id":id,"request_id":"r"}))
        .is_ok());
    assert!(rollback.arguments(&json!({"integration_id":id})).is_err());
    for name in ["subagent_cancel", "subagent_discard"] {
        assert!(tool(name)
            .unwrap()
            .arguments(&json!({"worker_id":id}))
            .is_ok());
        assert!(tool(name).unwrap().arguments(&json!({})).is_err());
    }
}

#[test]
fn worker_id_is_accepted_exactly_on_the_22_spec_tools() {
    let mut seen = BTreeSet::new();
    for spec in tools() {
        let field = spec.schema["properties"].get("worker_id");
        if spec.name.starts_with("subagent_") {
            continue;
        }
        if let Some(field) = field {
            assert_eq!(
                field,
                &json!({"type":"string","pattern":"^[0-9a-f]{32}$"}),
                "{}",
                spec.name
            );
            seen.insert(spec.name.as_str());
        }
    }
    assert_eq!(seen, WORKER_ID_TOOLS.into_iter().collect());
    let id = "a".repeat(32);
    assert!(tool("read_file")
        .unwrap()
        .arguments(&json!({"path":"x","worker_id":id}))
        .is_ok());
    for bad in ["A".repeat(32), "a".repeat(31), "../x".into()] {
        assert!(tool("read_file")
            .unwrap()
            .arguments(&json!({"path":"x","worker_id":bad}))
            .is_err());
    }
    for name in [
        "server_info",
        "workspace_probe",
        "worktree_list",
        "get_exec_task",
    ] {
        assert!(
            tool(name)
                .unwrap()
                .arguments(&json!({"worker_id":id}))
                .is_err(),
            "{name}"
        );
    }
}

#[test]
fn scopes_for_keeps_the_repair_choice_and_appends_agents_manage_for_workers() {
    let id = "a".repeat(32);
    let validate = tool("history_session_validate").unwrap();
    for (args, base) in [
        (json!({}), "history.read"),
        (json!({"repair":false}), "history.read"),
        (json!({"repair":true}), "history.write"),
    ] {
        assert_eq!(validate.scopes_for(&args), vec![base.to_string()], "{args}");
        let mut with = args.clone();
        with["worker_id"] = json!(id);
        assert_eq!(
            validate.scopes_for(&with),
            vec![base.to_string(), "agents.manage".to_string()],
            "{with}"
        );
        assert_eq!(validate.primary_scope(&with), base);
    }
    let read = tool("read_file").unwrap();
    assert_eq!(read.scopes_for(&json!({"path":"x"})), ["files.read"]);
    assert_eq!(
        read.scopes_for(&json!({"path":"x","worker_id":id})),
        ["files.read", "agents.manage"]
    );
    assert_eq!(read.primary_scope(&json!({"worker_id":id})), "files.read");
    let stdin = tool("write_stdin").unwrap();
    assert_eq!(
        stdin.scopes_for(&json!({"worker_id":id})),
        ["task.manage", "exec.run", "agents.manage"]
    );
    // Never duplicated when the base set already requires agents.manage.
    assert_eq!(
        tool("subagent_status")
            .unwrap()
            .scopes_for(&json!({"worker_id":id})),
        ["agents.manage"]
    );
    assert_eq!(
        tool("subagent_cancel")
            .unwrap()
            .scopes_for(&json!({"worker_id":id})),
        ["agents.manage", "task.manage"]
    );
}

#[test]
fn only_the_two_reviewed_opaque_patterns_are_evaluated() {
    let id32 = json!({"type":"string","pattern":"^[0-9a-f]{32}$"});
    let sha64 = json!({"type":"string","pattern":"^[0-9a-f]{64}$"});
    assert!(matches_schema(&id32, &json!("a".repeat(32)), 0));
    assert!(!matches_schema(&id32, &json!("a".repeat(64)), 0));
    assert!(matches_schema(&sha64, &json!("f".repeat(64)), 0));
    assert!(!matches_schema(&sha64, &json!("f".repeat(32)), 0));
    assert!(!matches_schema(&sha64, &json!("F".repeat(64)), 0));
    assert!(!matches_schema(
        &json!({"type":"string","pattern":"^.*$"}),
        &json!("x"),
        0
    ));
}
