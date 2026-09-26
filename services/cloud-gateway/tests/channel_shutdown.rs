//! Shutdown is a distinct lifecycle fence; stale shutdown must not damage a new boot.
#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;
use channel_support::*;
use coding_tools_cloud_gateway::{channel::*, projection::ProjectionDecision as D};
use futures_util::StreamExt;
use std::time::Duration;
use tokio_tungstenite::tungstenite::{client::IntoClientRequest, Message};

#[tokio::test]
async fn stale_controller_shutdown_cannot_fence_new_generation() {
    let (h, old) = setup().await;
    let first = attach(&h, &old).await;
    project(&h, &old, &first, 1, 1).await;
    let new = ChannelController::activate(h.f.store.clone())
        .await
        .unwrap();
    let session = attach(&h, &new).await;
    project(&h, &new, &session, 1, 2).await;
    assert!(old.deactivate().await.is_err());
    new.validate(&session).await.unwrap();
    assert_eq!(new.assess(&h.a, "files.read").await.unwrap(), D::Eligible);
}
#[tokio::test]
async fn current_shutdown_keeps_exclusive_owner_and_revocation_state() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    let before: String = sqlx::query_scalar("SELECT state_text FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    c.deactivate().await.unwrap();
    assert!(c.validate(&s).await.is_err());
    let after: String = sqlx::query_scalar("SELECT state_text FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(before, after);
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::RecoveryRequired
    );
    assert_eq!(
        c.assess(&h.b, "files.read").await.unwrap(),
        D::AuthorizationUnavailable
    );
    c.deactivate().await.unwrap();
}
#[tokio::test]
async fn managed_shutdown_drains_a_real_unauthenticated_websocket() {
    let (_h, c) = setup().await;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (routes, stop) = managed_agent_channel_routes(c);
    let task = tokio::spawn(async move { axum::serve(listener, routes).await.unwrap() });
    let mut request = format!("ws://{address}/coding-tools/agent")
        .into_client_request()
        .unwrap();
    request
        .headers_mut()
        .insert("host", common::identity().authority().parse().unwrap());
    request
        .headers_mut()
        .insert("sec-websocket-protocol", SUBPROTOCOL.parse().unwrap());
    let (mut ws, _) = tokio_tungstenite::connect_async(request.clone())
        .await
        .unwrap();
    assert!(matches!(
        ws.next().await.unwrap().unwrap(),
        Message::Text(_)
    ));
    stop.signal();
    tokio::time::timeout(Duration::from_secs(4), stop.drain())
        .await
        .unwrap()
        .unwrap();
    let frame = tokio::time::timeout(Duration::from_secs(2), ws.next())
        .await
        .unwrap();
    assert!(matches!(frame, Some(Ok(Message::Close(_))) | None));
    assert!(tokio_tungstenite::connect_async(request).await.is_err());
    task.abort();
}
