use super::{input::GatewayConfig, lifecycle, Result, ServiceError};
use crate::IdentityStore;
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
}
fn safe_response(status: StatusCode, value: serde_json::Value) -> Response {
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
        return safe_response(StatusCode::FORBIDDEN, json!({"error":"request_rejected"}));
    }
    let admitted = if let Ok(mut b) = s.budget.lock() {
        if b.0.elapsed() >= Duration::from_secs(1) {
            *b = (Instant::now(), 0);
        }
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
        let mut response =
            safe_response(StatusCode::TOO_MANY_REQUESTS, json!({"error":"try_later"}));
        response
            .headers_mut()
            .insert(header::RETRY_AFTER, "1".parse().unwrap());
        return response;
    }
    next.run(request).await
}
async fn live() -> Response {
    safe_response(StatusCode::OK, json!({"live":true}))
}
async fn ready(State(s): State<RuntimeState>) -> Response {
    if tokio::time::timeout(Duration::from_secs(2), lifecycle::ready(&s.store, &s.cfg))
        .await
        .is_ok_and(|r| r.is_ok())
    {
        safe_response(StatusCode::OK, json!({"ready":true}))
    } else {
        safe_response(StatusCode::SERVICE_UNAVAILABLE, json!({"ready":false}))
    }
}

/// Only loopback accepts trusted TLS reverse-proxy traffic. No cloud execution endpoint.
pub(crate) async fn serve(store: IdentityStore, cfg: GatewayConfig) -> Result<()> {
    lifecycle::ready(&store, &cfg).await?;
    #[cfg(unix)]
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(|_| ServiceError::Shutdown)?;
    let shutdown = async move {
        #[cfg(unix)]
        tokio::select! { _ = tokio::signal::ctrl_c() => {}, _ = terminate.recv() => {} }
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
    let state = RuntimeState {
        store: store.clone(),
        cfg: cfg.clone(),
        budget: Arc::new(Mutex::new((Instant::now(), 0))),
    };
    let health = Router::new()
        .route(&format!("{}/health/live", cfg.prefix), get(live))
        .route(&format!("{}/health/ready", cfg.prefix), get(ready))
        .with_state(state.clone());
    let routes = crate::http::identity_routes(store.clone())
        .merge(health)
        .layer(middleware::from_fn_with_state(state, controls));
    let semaphore = Arc::new(Semaphore::new(MAX_CONNECTIONS));
    let (stop, _) = watch::channel(false);
    let mut tasks = JoinSet::new();
    println!(
        "{}",
        json!({"status":"ready","listen":address.to_string(),"mode":"identity_only"})
    );
    loop {
        tokio::select! {
            biased;
            _ = &mut shutdown => break,
            Some(_) = tasks.join_next(), if !tasks.is_empty() => {},
            accepted = listener.accept() => {
                let (stream, _) = accepted.map_err(|_|ServiceError::Bind)?;
                let Ok(permit) = semaphore.clone().try_acquire_owned() else { drop(stream); continue; };
                let app = routes.clone();
                let mut closing = stop.subscribe();
                tasks.spawn(async move {
                    let _permit = permit;
                    let mut builder = http1::Builder::new();
                    builder.timer(TokioTimer::new()).header_read_timeout(Duration::from_secs(5))
                        .max_headers(32).max_buf_size(16_384).keep_alive(false);
                    let connection = builder.serve_connection(TokioIo::new(stream),TowerToHyperService::new(app));
                    tokio::pin!(connection);
                    tokio::select! {
                        _ = &mut connection => {},
                        _ = tokio::time::sleep(Duration::from_secs(10)) => {},
                        _ = closing.changed() => {
                            connection.as_mut().graceful_shutdown();
                            let _ = tokio::time::timeout(Duration::from_secs(4), &mut connection).await;
                        }
                    }
                });
            }
        }
    }
    drop(listener);
    let _ = stop.send(true);
    let drained = tokio::time::timeout(Duration::from_secs(5), async {
        while tasks.join_next().await.is_some() {}
    })
    .await
    .is_ok();
    if !drained {
        tasks.abort_all();
    }
    if tokio::time::timeout(Duration::from_secs(5), store.pool.close())
        .await
        .is_err()
        || !drained
    {
        return Err(ServiceError::Shutdown);
    }
    println!("{}", json!({"status":"stopped"}));
    Ok(())
}
