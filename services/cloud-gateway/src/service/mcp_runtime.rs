use super::{input::GatewayConfig, lifecycle, Result, ServiceError};
use crate::{
    observability::{ConnectionObservation, GatewayObservability, IngressRejection},
    IdentityStore,
};
use axum::{
    extract::State,
    http::{header, Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use hyper::server::conn::http1;
use hyper_util::{
    rt::{TokioIo, TokioTimer},
    service::TowerToHyperService,
};
use serde_json::json;
use std::{
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio::{
    net::TcpListener,
    sync::{watch, Semaphore},
    task::JoinSet,
};

const MAX_CONNECTIONS: usize = 64;
const REQUESTS_PER_SECOND: u32 = 64;
#[derive(Clone)]
struct RuntimeState {
    store: IdentityStore,
    cfg: GatewayConfig,
    budget: Arc<Mutex<(Instant, u32)>>,
    observability: GatewayObservability,
}
fn safe(status: StatusCode, value: serde_json::Value) -> Response {
    let mut r = (status, Json(value)).into_response();
    r.headers_mut()
        .insert(header::CACHE_CONTROL, "no-store".parse().unwrap());
    r.headers_mut()
        .insert(header::REFERRER_POLICY, "no-referrer".parse().unwrap());
    r.headers_mut()
        .insert(header::X_CONTENT_TYPE_OPTIONS, "nosniff".parse().unwrap());
    r
}
async fn controls(
    State(s): State<RuntimeState>,
    request: Request<axum::body::Body>,
    next: Next,
) -> Response {
    let started = Instant::now();
    if request.headers().get_all(header::HOST).iter().count() != 1
        || request
            .headers()
            .get(header::HOST)
            .and_then(|h| h.to_str().ok())
            != Some(s.store.identity().authority())
        || request.headers().get_all(header::ORIGIN).iter().count() > 1
        || request
            .headers()
            .get(header::ORIGIN)
            .is_some_and(|h| !h.to_str().is_ok_and(|v| s.store.identity().allow_origin(v)))
    {
        s.observability
            .record_ingress_rejected(IngressRejection::HostOrOrigin);
        s.observability.record_latency(started.elapsed());
        return safe(StatusCode::FORBIDDEN, json!({"error":"request_rejected"}));
    }
    let admitted = if let Ok(mut b) = s.budget.lock() {
        if b.0.elapsed() >= Duration::from_secs(1) {
            *b = (Instant::now(), 0)
        };
        if b.1 < REQUESTS_PER_SECOND {
            b.1 += 1;
            true
        } else {
            false
        }
    } else {
        false
    };
    if !admitted {
        s.observability
            .record_ingress_rejected(IngressRejection::RateLimit);
        s.observability.record_latency(started.elapsed());
        let mut r = safe(StatusCode::TOO_MANY_REQUESTS, json!({"error":"try_later"}));
        r.headers_mut()
            .insert(header::RETRY_AFTER, "1".parse().unwrap());
        return r;
    }
    s.observability.record_ingress_accepted();
    let response = next.run(request).await;
    match response.status() {
        StatusCode::PAYLOAD_TOO_LARGE => s
            .observability
            .record_ingress_rejected(IngressRejection::Body),
        StatusCode::REQUEST_TIMEOUT => s
            .observability
            .record_ingress_rejected(IngressRejection::Timeout),
        status if status.is_server_error() => s
            .observability
            .record_ingress_rejected(IngressRejection::Internal),
        _ => {}
    }
    s.observability.record_latency(started.elapsed());
    response
}
async fn live() -> Response {
    safe(StatusCode::OK, json!({"live":true}))
}
async fn ready(State(s): State<RuntimeState>) -> Response {
    if tokio::time::timeout(Duration::from_secs(2), lifecycle::ready(&s.store, &s.cfg))
        .await
        .is_ok_and(|r| r.is_ok())
    {
        safe(StatusCode::OK, json!({"ready":true}))
    } else {
        safe(StatusCode::SERVICE_UNAVAILABLE, json!({"ready":false}))
    }
}

pub(crate) async fn serve(store: IdentityStore, cfg: GatewayConfig) -> Result<()> {
    lifecycle::ready(&store, &cfg).await?;
    #[cfg(unix)]
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(|_| ServiceError::Shutdown)?;
    let shutdown = async move {
        #[cfg(unix)]
        tokio::select! {_=tokio::signal::ctrl_c()=>{},_=terminate.recv()=>{}}
        #[cfg(not(unix))]
        {
            let _ = tokio::signal::ctrl_c().await;
        }
    };
    tokio::pin!(shutdown);
    let listener = TcpListener::bind(cfg.bind)
        .await
        .map_err(|_| ServiceError::Bind)?;
    let address = listener.local_addr().map_err(|_| ServiceError::Bind)?;
    let observability = GatewayObservability::default();
    let state = RuntimeState {
        store: store.clone(),
        cfg: cfg.clone(),
        budget: Arc::new(Mutex::new((Instant::now(), 0))),
        observability: observability.clone(),
    };
    let health = Router::new()
        .route(&format!("{}/health/live", cfg.prefix), get(live))
        .route(&format!("{}/health/ready", cfg.prefix), get(ready))
        .with_state(state.clone());
    let control = crate::channel::ChannelController::activate(store.clone())
        .await
        .map_err(|_| ServiceError::Store)?;
    let (agent_routes, agent_shutdown) =
        crate::channel::managed_agent_channel_routes(control.clone());
    let routes = crate::http::identity_routes(store.clone())
        .merge(agent_routes)
        .merge(crate::mcp::routes_with_observability(
            store.clone(),
            control,
            observability.clone(),
        ))
        .merge(health)
        .layer(middleware::from_fn_with_state(state, controls));
    let semaphore = Arc::new(Semaphore::new(MAX_CONNECTIONS));
    let (stop, _) = watch::channel(false);
    let mut tasks = JoinSet::new();
    println!(
        "{}",
        json!({"status":"ready","listen":address.to_string(),"mode":"identity_agent_mcp_control_plane"})
    );
    loop {
        tokio::select! {biased; _=&mut shutdown=>break,Some(_)=tasks.join_next(),if !tasks.is_empty()=>{},accepted=listener.accept()=>{
            let (stream,_) = accepted.map_err(|_|ServiceError::Bind)?;
            let Ok(permit) = semaphore.clone().try_acquire_owned() else {
                observability.record_connection(ConnectionObservation::RejectedCapacity);
                drop(stream);
                continue;
            };
            observability.record_connection(ConnectionObservation::Accepted);
            let app = routes.clone();
            let mut closing = stop.subscribe();
            let connection_observability = observability.clone();
            tasks.spawn(async move {
                let _permit = permit;
                let mut builder = http1::Builder::new();
                builder
                    .timer(TokioTimer::new())
                    .header_read_timeout(Duration::from_secs(5))
                    .max_headers(32)
                    .max_buf_size(65_536)
                    .keep_alive(true);
                let connection = builder
                    .serve_connection(TokioIo::new(stream), TowerToHyperService::new(app))
                    .with_upgrades();
                tokio::pin!(connection);
                tokio::select! {
                    _ = &mut connection => {
                        connection_observability.record_connection(ConnectionObservation::Closed);
                    },
                    _ = tokio::time::sleep(Duration::from_secs(10)) => {
                        connection_observability.record_connection(ConnectionObservation::Timeout);
                    },
                    _ = closing.changed() => {
                        connection.as_mut().graceful_shutdown();
                        let _ = tokio::time::timeout(Duration::from_secs(4), &mut connection).await;
                        connection_observability.record_connection(ConnectionObservation::Closed);
                    }
                }
            });
        }}
    }
    drop(listener);
    let _ = stop.send(true);
    agent_shutdown.signal();
    let drained = tokio::time::timeout(Duration::from_secs(5), async {
        while tasks.join_next().await.is_some() {}
    })
    .await
    .is_ok();
    if !drained {
        tasks.abort_all();
    }
    let agents_drained = agent_shutdown.drain().await.is_ok();
    if tokio::time::timeout(Duration::from_secs(5), store.pool.close())
        .await
        .is_err()
        || !drained
        || !agents_drained
    {
        return Err(ServiceError::Shutdown);
    }
    println!("{}", json!({"status":"stopped"}));
    Ok(())
}
