use super::*;
use crate::{
    auth::{cloud_context::CloudTransport, PublicOrigin},
    workspace::{AuthConfig, RuntimeConfig},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde_json::json;
use zeroize::Zeroizing;

struct Fixture {
    root: tempfile::TempDir,
    id: String,
    lease: ListenerContextLease,
    listener: Option<(
        crate::mcp::ShutdownSender,
        tauri::async_runtime::JoinHandle<()>,
    )>,
    config: Vec<u8>,
    key: Zeroizing<Vec<u8>>,
}
impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        let id = Uuid::new_v4().to_string();
        // OS-selected socket remains owned by the actual native HTTP listener.
        let (shutdown, listener, _gate, lease) =
            crate::mcp::spawn_listener_with_origin_and_context_lease(
                0,
                workspace,
                id.clone(),
                AuthConfig {
                    auth_type: "noauth".into(),
                    ..Default::default()
                },
                PublicOrigin::managed("").unwrap(),
                None,
                None,
                None,
                RuntimeConfig::default(),
            )
            .unwrap();
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&ring::rand::SystemRandom::new()).unwrap();
        let pair = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
        let config = serde_json::to_vec(&json!({"origin":"https://127.0.0.1:9", "prefix":"/bridge",
            "connector":Uuid::new_v4(), "device":Uuid::new_v4(), "device_epoch":1,"authority_epoch":1,
            "public_key":URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),
            "revision_file":root.path().join("runtime/revision.bin"),"ca_der_file":null,"run_seconds":60})).unwrap();
        let key = Zeroizing::new(
            serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs8.as_ref())})).unwrap(),
        );
        Self {
            root,
            id,
            lease,
            listener: Some((shutdown, listener)),
            config,
            key,
        }
    }
    fn material(&self) -> RuntimeMaterial {
        let cfg = coding_tools_cloud_agent::AgentConfig::from_bytes(&self.config).unwrap();
        let context = self.lease.with_live(Arc::clone).unwrap();
        RuntimeMaterial {
            config: self.config.clone(),
            key: Zeroizing::new(self.key.to_vec()),
            link: CloudTransport::new(
                &self.id,
                context.workspace.root(),
                &cfg.origin,
                &cfg.prefix,
                cfg.connector,
                cfg.device,
                1,
                "native-application-test-separate-binding-secret",
            )
            .unwrap(),
            root: self.root.path().join("runtime"),
            authority_epoch: 1,
        }
    }
    async fn close_listener(&mut self) {
        if let Some((shutdown, task)) = self.listener.take() {
            let _ = shutdown.send(());
            tokio::time::timeout(Duration::from_secs(5), task)
                .await
                .unwrap()
                .unwrap();
            self.lease.wait_closed().await;
        }
    }
}
async fn host(app: &ApplicationAgents, id: &str) -> Arc<NativeLiveHost> {
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let result = app
                .views
                .lock()
                .unwrap()
                .get(id)
                .and_then(|v| v.host.lock().unwrap().clone());
            if let Some(host) = result {
                return host;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("application factory did not open native journals")
}

#[tokio::test]
async fn close_before_first_poll_initializes_nothing_and_closed_manager_cannot_reopen() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    app.request_shutdown();
    app.shutdown().await.unwrap();
    assert!(!fixture.root.path().join("runtime").exists());
    assert!(app
        .start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .is_err());
    fixture.close_listener().await;
}

#[tokio::test]
async fn duplicate_registration_is_rejected_before_journal_initialization() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    assert!(app
        .start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .is_err());
    assert!(!fixture.root.path().join("runtime").exists());
    app.shutdown().await.unwrap();
    fixture.close_listener().await;
}

#[tokio::test]
async fn actual_listener_context_and_pause_are_shared_and_listener_close_stops_agent() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    let context = fixture.lease.with_live(Arc::clone).unwrap();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    let host = host(&app, &fixture.id).await;
    assert!(Arc::ptr_eq(&context, &host.application_test_context()));
    context.execution_gate.pause().unwrap();
    assert_eq!(app.status(&fixture.id, true).unwrap().phase, "paused");
    let handle = app
        .views
        .lock()
        .unwrap()
        .get(&fixture.id)
        .unwrap()
        .handle
        .clone();
    fixture.close_listener().await;
    assert_eq!(
        handle.wait(Duration::from_secs(5)).await.unwrap(),
        RunOutcome::Drained
    );
    assert!(!app.status(&fixture.id, true).unwrap().connected);
    assert!(host.application_test_work().status().sealed);
    assert!(fixture.lease.with_live(|_| ()).is_err());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn application_stop_retains_slot_and_journal_until_real_native_callback_finishes() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    let host = host(&app, &fixture.id).await;
    // Both assertions must exercise the same valid journal path, so a Windows
    // path-normalization refusal cannot masquerade as the live exclusive lock.
    let journal_parent = fixture.root.path().join("runtime").canonicalize().unwrap();
    let journal = journal_parent.join("executions.bin");
    let (ready, started) = tokio::sync::oneshot::channel();
    let (release, held) = std::sync::mpsc::channel();
    let work = crate::tools::native_drain::blocking(&host.application_test_work(), move |_| {
        let _ = ready.send(());
        held.recv_timeout(Duration::from_secs(10))
            .map_err(|_| coding_tools_cloud_agent::AgentError::ExecutionUnknown)?;
        Ok(())
    });
    let waiter = tokio::spawn(work);
    started.await.unwrap();
    waiter.abort();
    let _ = waiter.await;
    let handle = app
        .views
        .lock()
        .unwrap()
        .get(&fixture.id)
        .unwrap()
        .handle
        .clone();
    app.manager.request_stop(&handle).unwrap();
    assert!(handle.wait(Duration::from_millis(40)).await.is_err());
    assert!(app
        .start(
            &fixture.id,
            fixture.lease.clone(),
            fixture.material(),
            false
        )
        .is_err());
    assert!(HostAgent::open(&fixture.config, &fixture.key, &journal, false, host.clone()).is_err());
    release.send(()).unwrap();
    assert_eq!(
        handle.wait(Duration::from_secs(5)).await.unwrap(),
        RunOutcome::Drained
    );
    assert!(HostAgent::open(&fixture.config, &fixture.key, &journal, false, host).is_ok());
    fixture.close_listener().await;
}

#[tokio::test]
async fn partial_setup_never_self_heals_or_overwrites_existing_namespace() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    std::fs::create_dir(fixture.root.path().join("runtime")).unwrap();
    std::fs::write(fixture.root.path().join("runtime/retained"), "immutable").unwrap();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    let handle = app
        .views
        .lock()
        .unwrap()
        .get(&fixture.id)
        .unwrap()
        .handle
        .clone();
    assert_eq!(
        handle.wait(Duration::from_secs(5)).await.unwrap(),
        RunOutcome::FailedDrained
    );
    assert_eq!(app.status(&fixture.id, true).unwrap().phase, "recovery");
    assert_eq!(
        std::fs::read(fixture.root.path().join("runtime/retained")).unwrap(),
        b"immutable"
    );
    assert_eq!(
        std::fs::read_dir(fixture.root.path().join("runtime"))
            .unwrap()
            .count(),
        1
    );
    app.start(
        &fixture.id,
        fixture.lease.clone(),
        fixture.material(),
        false,
    )
    .unwrap();
    let handle = app
        .views
        .lock()
        .unwrap()
        .get(&fixture.id)
        .unwrap()
        .handle
        .clone();
    assert_eq!(
        handle.wait(Duration::from_secs(5)).await.unwrap(),
        RunOutcome::FailedDrained
    );
    assert_eq!(
        std::fs::read_dir(fixture.root.path().join("runtime"))
            .unwrap()
            .count(),
        1
    );
    fixture.close_listener().await;
}

#[tokio::test]
async fn native_workspace_removal_preserves_uncertain_occupancy() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    let material = fixture.material();
    let handle = app
        .manager
        .launch(workspace_identity(&fixture.id), |_| async {
            panic!("synthetic native owner failure");
            #[allow(unreachable_code)]
            TaskExit::Drained
        })
        .unwrap();
    app.views.lock().unwrap().insert(
        fixture.id.clone(),
        View {
            handle: handle.clone(),
            link: material.link,
            host: Arc::new(Mutex::new(None)),
        },
    );
    assert!(handle.wait(Duration::from_secs(2)).await.is_err());
    assert_eq!(app.status(&fixture.id, true).unwrap().phase, "recovery");
    assert!(app.remove_drained_workspace(&fixture.id).is_err());
    assert!(app
        .start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .is_err());
    assert!(!fixture.root.path().join("runtime").exists());
    fixture.close_listener().await;
}

#[tokio::test]
async fn native_workspace_removal_releases_only_drained_view_and_preserves_disk() {
    let mut fixture = Fixture::new();
    let app = ApplicationAgents::default();
    app.start(&fixture.id, fixture.lease.clone(), fixture.material(), true)
        .unwrap();
    let opened = host(&app, &fixture.id).await;
    drop(opened);
    assert!(app.remove_drained_workspace(&fixture.id).is_err());
    app.stop(&fixture.id).await.unwrap();
    app.remove_drained_workspace(&fixture.id).unwrap();
    assert!(!app.views.lock().unwrap().contains_key(&fixture.id));
    assert!(fixture.root.path().join("runtime/executions.bin").is_file());
    fixture.close_listener().await;
}
