use super::*;
use crate::canonical::digest_json;
use serde_json::json;
fn valid() -> Value {
    json!({"cmd":"Get-Content input.txt","workspace_io":{"input":"src/input.txt","output_parent":"results","output_leaf":"answer.txt"}})
}
#[test]
fn valid_manifest_is_hash_bound_and_requires_three_scopes() {
    let s = tool("exec_command").unwrap();
    let args = valid();
    assert!(s.validate(&args).is_ok());
    assert_eq!(
        s.scopes_for(&args),
        ["exec.run", "files.read", "files.write"]
    );
    assert_eq!(s.primary_scope(&args), "exec.run");
}
#[test]
fn workspace_defaults_preserve_the_explicit_manifest_bytes() {
    let s = tool("exec_command").unwrap();
    let args = valid();
    let out = s.arguments(&args).unwrap();
    assert_eq!(out["workspace_io"], args["workspace_io"]);
    assert_eq!(out["cmd"], args["cmd"]);
    assert_eq!(out["workdir"], ".");
    assert_eq!(out["tty"], false);
    assert!(s.validate(&out).is_ok());
}
#[test]
fn every_input_or_output_field_changes_the_canonical_arguments_digest() {
    let args = valid();
    let original = digest_json(&args, 4096).unwrap();
    for key in ["input", "output_parent", "output_leaf"] {
        let mut changed = args.clone();
        changed["workspace_io"][key] = json!("different");
        assert!(tool("exec_command").unwrap().validate(&changed).is_ok());
        assert_ne!(digest_json(&changed, 4096).unwrap(), original);
    }
}
#[test]
fn nested_unknown_fields_and_wrong_types_never_become_old_single_scope() {
    let s = tool("exec_command").unwrap();
    for value in [
        json!(null),
        json!(true),
        json!([]),
        json!({}),
        json!({"input":"a","output_parent":"out","output_leaf":"b","authorized":true}),
        json!({"input":"a","output_parent":"out","output_leaf":"b","overwrite":true}),
        json!({"input":7,"output_parent":"out","output_leaf":"b"}),
    ] {
        let mut args = valid();
        args["workspace_io"] = value;
        assert!(s.validate(&args).is_err());
        assert_eq!(
            s.scopes_for(&args),
            ["exec.run", "files.read", "files.write"]
        );
    }
}
#[test]
fn absolute_traversal_device_ads_and_ambiguous_paths_are_denied() {
    let s = tool("exec_command").unwrap();
    for value in [
        "",
        ".",
        "..",
        "/a",
        "C:a",
        "C:/a",
        "\\\\host\\a",
        "a\\b",
        "a//b",
        "a/../b",
        "a:stream",
        "a.",
        "a ",
        "CON",
        "NUL.txt",
        "COM1 .log",
        "COM¹",
        "LPT².txt",
        "a\0",
        "a\n",
        "a?b",
    ] {
        for key in ["input", "output_parent", "output_leaf"] {
            let mut args = valid();
            args["workspace_io"][key] = json!(value);
            assert!(s.validate(&args).is_err(), "{key}:{value:?}");
        }
    }
    let mut args = valid();
    args["workspace_io"]["output_leaf"] = json!("sub/result.txt");
    assert!(s.validate(&args).is_err());
}
#[test]
fn path_byte_depth_and_utf16_leaf_limits_are_enforced() {
    let s = tool("exec_command").unwrap();
    let mut args = valid();
    args["workspace_io"]["input"] = json!(vec!["a"; 64].join("/"));
    assert!(s.validate(&args).is_ok());
    args["workspace_io"]["input"] = json!(vec!["a"; 65].join("/"));
    assert!(s.validate(&args).is_err());
    let mut args = valid();
    args["workspace_io"]["output_leaf"] = json!("a".repeat(255));
    assert!(s.validate(&args).is_ok());
    args["workspace_io"]["output_leaf"] = json!("a".repeat(256));
    assert!(s.validate(&args).is_err());
    args["workspace_io"]["output_leaf"] = json!("😀".repeat(128));
    assert!(s.validate(&args).is_err());
    let mut args = valid();
    args["workspace_io"]["input"] = json!(vec!["a".repeat(255); 5].join("/"));
    assert!(s.validate(&args).is_err());
}
#[test]
fn workspace_command_mode_is_finite_and_cannot_select_other_workdir_or_tty() {
    let s = tool("exec_command").unwrap();
    for (key, value) in [
        ("cmd", json!("a".repeat(2049))),
        ("stdin", json!("x".repeat(1025))),
        ("tty", json!(true)),
        ("workdir", json!("other")),
    ] {
        let mut args = valid();
        args[key] = value;
        assert!(s.validate(&args).is_err(), "{key}");
    }
    let mut args = valid();
    args["cmd"] = json!("a".repeat(2048));
    args["stdin"] = json!("x".repeat(1024));
    assert!(s.validate(&args).is_ok());
}
#[test]
fn absent_workspace_io_preserves_old_defaults_and_single_scope() {
    let s = tool("exec_command").unwrap();
    let old = json!({"cmd":"echo old","workdir":"sub","tty":true});
    assert!(s.validate(&old).is_ok());
    assert_eq!(s.scopes_for(&old), ["exec.run"]);
    let args = s.arguments(&old).unwrap();
    assert!(args.get("workspace_io").is_none());
    assert_eq!(args["tty"], true);
    assert_eq!(args["workdir"], "sub");
}
