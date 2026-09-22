use serde::Serialize;
use std::{
    fmt,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::Duration,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IngressRejection {
    HostOrOrigin,
    Headers,
    Media,
    RateLimit,
    Body,
    Timeout,
    Internal,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuthObservation {
    Invalid,
    Unavailable,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum McpObservation {
    Success,
    Permission,
    Availability,
    ProtocolError,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConnectionObservation {
    Accepted,
    RejectedCapacity,
    Timeout,
    Closed,
}

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub struct ObservationSnapshot {
    pub ingress_accepted: u64,
    pub reject_host_or_origin: u64,
    pub reject_headers: u64,
    pub reject_media: u64,
    pub reject_rate_limit: u64,
    pub reject_body: u64,
    pub reject_timeout: u64,
    pub reject_internal: u64,
    pub auth_invalid: u64,
    pub auth_unavailable: u64,
    pub mcp_success: u64,
    pub mcp_permission: u64,
    pub mcp_availability: u64,
    pub mcp_protocol_error: u64,
    pub latency_under_10_ms: u64,
    pub latency_under_100_ms: u64,
    pub latency_under_1_s: u64,
    pub latency_1_s_or_more: u64,
    pub connection_accepted: u64,
    pub connection_rejected_capacity: u64,
    pub connection_timeout: u64,
    pub connection_closed: u64,
}

#[derive(Default)]
struct Counters {
    ingress_accepted: AtomicU64,
    reject_host_or_origin: AtomicU64,
    reject_headers: AtomicU64,
    reject_media: AtomicU64,
    reject_rate_limit: AtomicU64,
    reject_body: AtomicU64,
    reject_timeout: AtomicU64,
    reject_internal: AtomicU64,
    auth_invalid: AtomicU64,
    auth_unavailable: AtomicU64,
    mcp_success: AtomicU64,
    mcp_permission: AtomicU64,
    mcp_availability: AtomicU64,
    mcp_protocol_error: AtomicU64,
    latency_under_10_ms: AtomicU64,
    latency_under_100_ms: AtomicU64,
    latency_under_1_s: AtomicU64,
    latency_1_s_or_more: AtomicU64,
    connection_accepted: AtomicU64,
    connection_rejected_capacity: AtomicU64,
    connection_timeout: AtomicU64,
    connection_closed: AtomicU64,
}

/// Aggregate-only observability.
///
/// Recording methods intentionally accept only closed enums and numeric
/// durations. There is no API for arbitrary metric labels, request headers,
/// tokens, session identifiers, workspace paths, tool arguments, source text,
/// or command output.
#[derive(Clone, Default)]
pub struct GatewayObservability {
    counters: Arc<Counters>,
}

impl GatewayObservability {
    pub fn record_ingress_accepted(&self) {
        inc(&self.counters.ingress_accepted);
    }

    pub fn record_ingress_rejected(&self, reason: IngressRejection) {
        let counter = match reason {
            IngressRejection::HostOrOrigin => &self.counters.reject_host_or_origin,
            IngressRejection::Headers => &self.counters.reject_headers,
            IngressRejection::Media => &self.counters.reject_media,
            IngressRejection::RateLimit => &self.counters.reject_rate_limit,
            IngressRejection::Body => &self.counters.reject_body,
            IngressRejection::Timeout => &self.counters.reject_timeout,
            IngressRejection::Internal => &self.counters.reject_internal,
        };
        inc(counter);
    }

    pub fn record_auth(&self, outcome: AuthObservation) {
        let counter = match outcome {
            AuthObservation::Invalid => &self.counters.auth_invalid,
            AuthObservation::Unavailable => &self.counters.auth_unavailable,
        };
        inc(counter);
    }

    pub fn record_mcp(&self, outcome: McpObservation) {
        let counter = match outcome {
            McpObservation::Success => &self.counters.mcp_success,
            McpObservation::Permission => &self.counters.mcp_permission,
            McpObservation::Availability => &self.counters.mcp_availability,
            McpObservation::ProtocolError => &self.counters.mcp_protocol_error,
        };
        inc(counter);
    }

    pub fn record_latency(&self, elapsed: Duration) {
        let counter = if elapsed < Duration::from_millis(10) {
            &self.counters.latency_under_10_ms
        } else if elapsed < Duration::from_millis(100) {
            &self.counters.latency_under_100_ms
        } else if elapsed < Duration::from_secs(1) {
            &self.counters.latency_under_1_s
        } else {
            &self.counters.latency_1_s_or_more
        };
        inc(counter);
    }

    pub fn record_connection(&self, outcome: ConnectionObservation) {
        let counter = match outcome {
            ConnectionObservation::Accepted => &self.counters.connection_accepted,
            ConnectionObservation::RejectedCapacity => {
                &self.counters.connection_rejected_capacity
            }
            ConnectionObservation::Timeout => &self.counters.connection_timeout,
            ConnectionObservation::Closed => &self.counters.connection_closed,
        };
        inc(counter);
    }

    pub fn snapshot(&self) -> ObservationSnapshot {
        ObservationSnapshot {
            ingress_accepted: load(&self.counters.ingress_accepted),
            reject_host_or_origin: load(&self.counters.reject_host_or_origin),
            reject_headers: load(&self.counters.reject_headers),
            reject_media: load(&self.counters.reject_media),
            reject_rate_limit: load(&self.counters.reject_rate_limit),
            reject_body: load(&self.counters.reject_body),
            reject_timeout: load(&self.counters.reject_timeout),
            reject_internal: load(&self.counters.reject_internal),
            auth_invalid: load(&self.counters.auth_invalid),
            auth_unavailable: load(&self.counters.auth_unavailable),
            mcp_success: load(&self.counters.mcp_success),
            mcp_permission: load(&self.counters.mcp_permission),
            mcp_availability: load(&self.counters.mcp_availability),
            mcp_protocol_error: load(&self.counters.mcp_protocol_error),
            latency_under_10_ms: load(&self.counters.latency_under_10_ms),
            latency_under_100_ms: load(&self.counters.latency_under_100_ms),
            latency_under_1_s: load(&self.counters.latency_under_1_s),
            latency_1_s_or_more: load(&self.counters.latency_1_s_or_more),
            connection_accepted: load(&self.counters.connection_accepted),
            connection_rejected_capacity: load(&self.counters.connection_rejected_capacity),
            connection_timeout: load(&self.counters.connection_timeout),
            connection_closed: load(&self.counters.connection_closed),
        }
    }
}

impl fmt::Debug for GatewayObservability {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("GatewayObservability")
            .field(&self.snapshot())
            .finish()
    }
}

fn inc(counter: &AtomicU64) {
    counter.fetch_add(1, Ordering::Relaxed);
}

fn load(counter: &AtomicU64) -> u64 {
    counter.load(Ordering::Relaxed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snapshot_contains_only_bounded_aggregate_counts() {
        let metrics = GatewayObservability::default();
        metrics.record_ingress_accepted();
        metrics.record_ingress_rejected(IngressRejection::HostOrOrigin);
        metrics.record_auth(AuthObservation::Invalid);
        metrics.record_mcp(McpObservation::Availability);
        metrics.record_latency(Duration::from_millis(125));
        metrics.record_connection(ConnectionObservation::RejectedCapacity);

        let snapshot = metrics.snapshot();
        assert_eq!(snapshot.ingress_accepted, 1);
        assert_eq!(snapshot.reject_host_or_origin, 1);
        assert_eq!(snapshot.auth_invalid, 1);
        assert_eq!(snapshot.mcp_availability, 1);
        assert_eq!(snapshot.latency_under_1_s, 1);
        assert_eq!(snapshot.connection_rejected_capacity, 1);

        let rendered = serde_json::to_string(&snapshot).unwrap();
        for forbidden in [
            "authorization",
            "bearer",
            "session",
            "workspace",
            "arguments",
            "source",
            "command",
            "token",
        ] {
            assert!(!rendered.to_ascii_lowercase().contains(forbidden));
        }
    }

    #[test]
    fn latency_uses_fixed_buckets() {
        let metrics = GatewayObservability::default();
        for duration in [
            Duration::from_millis(1),
            Duration::from_millis(10),
            Duration::from_millis(100),
            Duration::from_secs(1),
        ] {
            metrics.record_latency(duration);
        }
        let snapshot = metrics.snapshot();
        assert_eq!(snapshot.latency_under_10_ms, 1);
        assert_eq!(snapshot.latency_under_100_ms, 1);
        assert_eq!(snapshot.latency_under_1_s, 1);
        assert_eq!(snapshot.latency_1_s_or_more, 1);
    }

    #[test]
    fn debug_is_aggregate_only() {
        let metrics = GatewayObservability::default();
        metrics.record_mcp(McpObservation::Permission);
        let rendered = format!("{metrics:?}");
        assert!(rendered.contains("mcp_permission"));
        assert!(!rendered.contains("openai/session"));
    }
}
