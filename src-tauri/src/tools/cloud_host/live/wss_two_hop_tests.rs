//! Native authenticated two-hop cases; support never fabricates authority.
use super::*;
use coding_tools_cloud_agent::{
    lifecycle::{AgentLifecycle, LifecycleError, RunOutcome},
    managed::AgentStart,
};
use uuid::Uuid;
#[path = "wss_two_hop_support.rs"]
mod support;
use support::*;

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_native_pending_grant_read_foreign() {
    let h = TwoHop::start("tls_two_hop_native_pending_grant_read_foreign").await;
    h.grant().await;
    let read = h.read(9010, "native-A").await;
    assert_eq!(read["ok"], true);
    assert!(read.to_string().contains(CANARY));
    let foreign = h.read(9011, "native-B").await;
    assert_eq!(foreign["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    denied(&foreign);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_reconnect_generation_restart_no_replay() {
    let mut h = TwoHop::start("tls_two_hop_reconnect_generation_restart_no_replay").await;
    h.grant().await;
    assert!(h.read(9020, "native-A").await.to_string().contains(CANARY));
    let first = h.ready().await;
    h.control(Op::GatewayStop).await;
    h.control(Op::GatewayStart).await;
    let second = h.ready().await;
    assert_ne!(first["gateway_boot"], second["gateway_boot"]);
    assert_ne!(first["session"], second["session"]);
    assert!(second["generation"].as_i64().unwrap() > first["generation"].as_i64().unwrap());
    h.stop().await;
    h.launch(false);
    let third = h.ready().await;
    assert_eq!(second["gateway_boot"], third["gateway_boot"]);
    assert_ne!(second["session"], third["session"]);
    assert!(third["generation"].as_i64().unwrap() > second["generation"].as_i64().unwrap());
    // Gateway Existing may enforce this: no local-tombstone causality claim or SQL reset.
    h.no_replay(9020).await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_native_grant_revoke_survives_restart() {
    let mut h = TwoHop::start("tls_two_hop_native_grant_revoke_survives_restart").await;
    h.grant().await;
    assert!(h.read(9030, "native-A").await.to_string().contains(CANARY));
    h.host().tools.authorizer.revoke("native-wss", None);
    h.wait(|s| s["reconciled"] == true && s["phase"] == "free")
        .await;
    denied(&h.read(9031, "native-A").await);
    h.stop().await;
    let old = Arc::downgrade(h.host());
    let old_tools = Arc::downgrade(&h.host().tools);
    let old_authorizer = Arc::downgrade(&h.host().tools.authorizer);
    drop(h.host.take());
    assert!(
        old.upgrade().is_none()
            && old_tools.upgrade().is_none()
            && old_authorizer.upgrade().is_none()
    );
    // All authority/projection objects reopen; MemoryKeys limits this to this process.
    h.host = Some(native_host(h.root.path(), &h.cfg, false));
    h.launch(false);
    h.ready().await;
    denied(&h.read(9032, "native-A").await);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_device_revoke_survives_gateway_database_restart() {
    let mut h = TwoHop::start("tls_two_hop_device_revoke_survives_gateway_database_restart").await;
    h.grant().await;
    assert!(h.read(9040, "native-A").await.to_string().contains(CANARY));
    let before = h.ready().await;
    h.stop().await;
    h.control(Op::RevokeDevice).await;
    h.launch(false);
    let public = h
        .http
        .get(format!(
            "{}/.well-known/oauth-authorization-server/coding-tools/oauth",
            h.cfg.origin
        ))
        .send()
        .await
        .unwrap();
    assert_eq!(public.status(), reqwest::StatusCode::OK);
    // Exhaust the real bounded retry budget: an absent poll result is not proof.
    let refused = tokio::time::timeout(Duration::from_secs(180), h.agent.take().unwrap())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(refused, Err(AgentError::Exhausted));
    assert_eq!(
        h.http
            .get(format!(
                "{}/.well-known/oauth-authorization-server/coding-tools/oauth",
                h.cfg.origin
            ))
            .send()
            .await
            .unwrap()
            .status(),
        reqwest::StatusCode::OK
    );
    let state = h.control(Op::Inspect).await;
    assert_eq!(state["device_revoked"], true);
    assert_eq!(state["connected"], false);
    assert_eq!(state["generation"], before["generation"]);
    assert!(h.host().tools.link.ensure_connected().is_err());
    denied(&h.read(9041, "native-A").await);
    h.control(Op::GatewayStop).await;
    h.control(Op::RestartDatabase).await;
    assert_eq!(h.control(Op::Inspect).await["device_revoked"], true);
    let receipt = h.control(Op::GatewayStart).await;
    assert_eq!(receipt["started"], false);
    assert_eq!(receipt["error"], "provisioning_not_ready");
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_gateway_shutdown_drains_authenticated_socket() {
    let h = TwoHop::start("tls_two_hop_gateway_shutdown_drains_authenticated_socket").await;
    h.grant().await;
    assert!(h.read(9050, "native-A").await.to_string().contains(CANARY));
    let initial = h.ready().await;
    let sampled_before = Instant::now();
    let fresh = h
        .wait(|s| s["lease_until"].as_i64().unwrap() > initial["lease_until"].as_i64().unwrap())
        .await;
    let db_remaining =
        fresh["lease_until"].as_i64().unwrap() - fresh["database_now"].as_i64().unwrap() - 1;
    assert!(db_remaining > 10);
    let database_end = sampled_before + Duration::from_secs(db_remaining as u64);
    let native_end = h.started + Duration::from_secs(30);
    let began = Instant::now();
    assert!(
        database_end > began + Duration::from_secs(10)
            && native_end > began + Duration::from_secs(10)
    );
    let original = sockets();
    assert_eq!(
        original.len(),
        1,
        "HTTPS pooling must not hide the outbound WSS443 tuple"
    );
    let observed = async {
        loop {
            let state = h.control(Op::Inspect).await;
            if state["connected"] == false
                && h.host().tools.link.ensure_connected().is_err()
                && original.is_disjoint(&sockets())
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    };
    let (receipt, ()) = tokio::time::timeout(Duration::from_secs(8), async {
        tokio::join!(h.control(Op::GatewayStop), observed)
    })
    .await
    .expect("actual authenticated socket did not drain within eight seconds");
    assert_eq!(receipt["stopped"], true);
    assert_eq!(receipt["exit_code"], 0);
    assert!(
        Instant::now() < native_end
            && Instant::now() < database_end
            && began.elapsed() < Duration::from_secs(8)
    );
    println!(
        "CTM_NATIVE_DRAIN {}",
        json!({"database_now":fresh["database_now"], "lease_until":fresh["lease_until"],
        "native_remaining_ms":native_end.duration_since(began).as_millis(), "elapsed_ms":began.elapsed().as_millis()})
    );
    assert!(!*h.stop.borrow() && !h.agent.as_ref().unwrap().is_finished());
    h.control(Op::GatewayStart).await;
    let next = h.ready().await;
    assert_ne!(fresh["gateway_boot"], next["gateway_boot"]);
    assert!(next["generation"].as_i64().unwrap() > fresh["generation"].as_i64().unwrap());
    h.no_replay(9050).await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_managed_callback_retains_journal_until_drain() {
    let mut h = TwoHop::start("tls_two_hop_managed_callback_retains_journal_until_drain").await;
    h.stop().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let run = AgentStart::new(h.config.clone(), h.key.clone(), h.journal(), false)
        .unwrap()
        .launch(&manager, Uuid::new_v4(), h.host().clone())
        .unwrap();
    h.ready().await;
    h.grant().await;
    assert!(h.read(9060, "native-A").await.to_string().contains(CANARY));
    let (started, observed) = tokio::sync::oneshot::channel();
    let (release, held) = std::sync::mpsc::channel();
    let callback = crate::tools::native_drain::blocking(&h.host().work, move |_| {
        let _ = started.send(());
        held.recv_timeout(Duration::from_secs(12))
            .map_err(|_| AgentError::ExecutionUnknown)?;
        Ok(())
    });
    let waiter = tokio::spawn(callback);
    tokio::time::timeout(Duration::from_secs(3), observed)
        .await
        .unwrap()
        .unwrap();
    waiter.abort();
    assert!(waiter.await.unwrap_err().is_cancelled());
    manager.request_stop(&run).unwrap();
    tokio::time::timeout(Duration::from_secs(5), async {
        while !h.host().work.status().sealed {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("managed native drain did not seal");
    assert_eq!(
        manager.stop(&run, Duration::from_millis(40)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert!(h.host().work.status().sealed && h.host().work.status().outstanding > 0);
    assert!(HostAgent::open(&h.config, &h.key, &h.journal(), false, h.host().clone()).is_err());
    release.send(()).unwrap();
    assert_eq!(
        run.wait(Duration::from_secs(6)).await,
        Ok(RunOutcome::Drained)
    );
    assert_eq!(h.host().work.status().outstanding, 0);
    assert!(HostAgent::open(&h.config, &h.key, &h.journal(), false, h.host().clone()).is_ok());
}
async fn certificate_refused(mode: &str, cause: &str) {
    let name = format!("tls_two_hop_{mode}_refused");
    let fixture_mode = if mode == "expired_certificate" {
        "expired"
    } else {
        mode
    };
    let mut h = TwoHop::load(&name, fixture_mode).await;
    let error = h
        .http
        .get(h.endpoint("/oauth/authorize"))
        .send()
        .await
        .unwrap_err();
    let mut chain = String::new();
    let mut source: Option<&(dyn std::error::Error + 'static)> = Some(&error);
    while let Some(error) = source {
        chain.push_str(&format!("{error:?}"));
        source = error.source();
    }
    assert!(
        chain.contains(cause),
        "HTTPS did not reject the intended certificate defect"
    );
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(5), h.agent.take().unwrap())
            .await
            .unwrap()
            .unwrap(),
        Err(AgentError::Tls)
    );
    let state = h.control(Op::Inspect).await;
    assert_eq!(state["connected"], false);
    assert_eq!(state["generation"], 0);
    assert!(h.host().tools.link.ensure_connected().is_err());
    assert!(h.host().tools.authorizer.snapshot("native-wss")["records"]
        .as_array()
        .unwrap()
        .is_empty());
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_untrusted_ca_refused() {
    certificate_refused("untrusted_ca", "UnknownIssuer").await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_wrong_hostname_refused() {
    certificate_refused("wrong_hostname", "NotValidForName").await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn tls_two_hop_expired_certificate_refused() {
    certificate_refused("expired_certificate", "Expired").await;
}
