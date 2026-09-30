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
