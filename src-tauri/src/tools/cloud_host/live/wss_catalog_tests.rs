use super::*;

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn full_catalog_routes_real_read_and_mutation_without_replay_or_foreign_output() {
    let h = Harness::start().await;
    let pending = h
        .rpc(
            8100,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":["files.read","files.write"]}),
        )
        .await;
    assert_eq!(pending["authorization"]["status"], "pending", "{pending}");
    h.host
        .tools
        .authorizer
        .decide(
            "native-wss",
            pending["authorization"]["id"].as_str().unwrap(),
            true,
            &["files.read".into(), "files.write".into()],
        )
        .unwrap();
    h.wait("eligible_a", true).await;
    let read = h
        .rpc(
            8101,
            "native-A",
            "read_file",
            json!({"path":"native-canary.txt"}),
        )
        .await;
    assert_eq!(read["ok"], true, "{read}");
    assert!(read.to_string().contains("native-cloud-real-file-canary"));
    let patch = json!({"patch":"*** Begin Patch\n*** Add File: cloud-created.txt\n+catalog-native-write\n*** End Patch\n"});
    let written = h.rpc(8102, "native-A", "apply_patch", patch.clone()).await;
    assert_eq!(written["ok"], true, "{written}");
    assert_eq!(
        std::fs::read_to_string(h._root.path().join("workspace/cloud-created.txt")).unwrap(),
        "catalog-native-write\n"
    );
    let duplicate = h.rpc(8102, "native-A", "apply_patch", patch).await;
    assert_ne!(duplicate["ok"], true);
    let conflict = h
        .rpc(
            8102,
            "native-A",
            "apply_patch",
            json!({"patch":"different"}),
        )
        .await;
    assert_eq!(conflict["error"]["code"], "REQUEST_ID_CONFLICT");
    let foreign = h
        .rpc(
            8103,
            "native-B",
            "read_file",
            json!({"path":"native-canary.txt"}),
        )
        .await;
    assert_eq!(foreign["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    assert!(!foreign
        .to_string()
        .contains("native-cloud-real-file-canary"));
    h.host.tools.authorizer.revoke("native-wss", None);
    h.wait("eligible_a", false).await;
    let revoked = h
        .rpc(
            8104,
            "native-A",
            "read_file",
            json!({"path":"native-canary.txt"}),
        )
        .await;
    assert_ne!(revoked["ok"], true);
    assert!(!revoked
        .to_string()
        .contains("native-cloud-real-file-canary"));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn cloud_worktree_catalog_executes_real_owned_create_list_remove_without_root_override() {
    let h = Harness::start().await;
    let workspace = h._root.path().join("workspace");
    let repository = git2::Repository::init(&workspace).unwrap();
    let mut index = repository.index().unwrap();
    index
        .add_path(std::path::Path::new("native-canary.txt"))
        .unwrap();
    index.write().unwrap();
    let tree_id = index.write_tree().unwrap();
    let tree = repository.find_tree(tree_id).unwrap();
    let signature = git2::Signature::now("Fixture", "fixture@example.invalid").unwrap();
    repository
        .commit(Some("HEAD"), &signature, &signature, "fixture", &tree, &[])
        .unwrap();
    let pending = h
        .rpc(
            8200,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":["files.read","files.write","workspace.read"]}),
        )
        .await;
    assert_eq!(pending["authorization"]["status"], "pending", "{pending}");
    h.host
        .tools
        .authorizer
        .decide(
            "native-wss",
            pending["authorization"]["id"].as_str().unwrap(),
            true,
            &[
                "files.read".into(),
                "files.write".into(),
                "workspace.read".into(),
            ],
        )
        .unwrap();
    h.wait("eligible_a", true).await;
    let invalid = h
        .rpc(
            8201,
            "native-A",
            "worktree_create",
            json!({"path":"/tmp/model-selected-root"}),
        )
        .await;
    assert_eq!(invalid["error"]["code"], "INVALID_ARGUMENTS");
    let created = h.rpc(8202, "native-A", "worktree_create", json!({})).await;
    assert_eq!(created["ok"], true, "{created}");
    let id = created["worktree"]["id"].as_str().unwrap();
    let listed = h.rpc(8203, "native-A", "worktree_list", json!({})).await;
    assert_eq!(listed["ok"], true, "{listed}");
    assert_eq!(listed["worktrees"].as_array().unwrap().len(), 1);
    let foreign = h.rpc(8204, "native-B", "worktree_list", json!({})).await;
    assert_eq!(foreign["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    assert!(!foreign.to_string().contains(id));
    let removed = h
        .rpc(8205, "native-A", "worktree_remove", json!({"id":id}))
        .await;
    assert_eq!(removed["ok"], true, "{removed}");
    assert_eq!(
        std::fs::read_to_string(workspace.join("native-canary.txt")).unwrap(),
        "native-cloud-real-file-canary"
    );
    assert_eq!(
        h.rpc(8206, "native-A", "worktree_list", json!({})).await["worktrees"],
        json!([])
    );
}
