//! Separate, locally installed cloud-channel identity; never a grant or OAuth token.
//! Activation is called only by the owned Agent supervisor after authenticated IPC.
//! There is intentionally no Deserialize implementation for transport or credentials.
use super::chat::{ChatAuthorizer, RemoteRequest};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::hmac;
use std::{
    collections::HashSet,
    path::Path,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use uuid::Uuid;

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct CloudPeer {
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: u64,
    pub gateway_boot: Uuid,
    pub session: Uuid,
    pub generation: u64,
}
impl std::fmt::Debug for CloudPeer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("CloudPeer([REDACTED])")
    }
}
struct Lease {
    peer: CloudPeer,
    until: Instant,
}
struct State {
    lease: Option<Lease>,
    last_peer: Option<CloudPeer>,
    seen_boots: HashSet<Uuid>,
    closed: bool,
}
struct Inner {
    profile: String,
    workspace: String,
    issuer: String,
    resource: String,
    connector: Uuid,
    device: Uuid,
    epoch: u64,
    key: hmac::Key,
    state: Mutex<State>,
}
#[derive(Clone)]
pub(crate) struct CloudTransport(Arc<Inner>);
pub(super) struct CloudCredential {
    link: CloudTransport,
    peer: CloudPeer,
    binding: String,
}
impl Clone for CloudCredential {
    fn clone(&self) -> Self {
        Self {
            link: self.link.clone(),
            peer: self.peer.clone(),
            binding: self.binding.clone(),
        }
    }
}
impl CloudTransport {
    /// All configuration is native-owned, not copied out of a cloud tool request.
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        profile: &str,
        workspace: &Path,
        origin: &str,
        prefix: &str,
        connector: Uuid,
        device: Uuid,
        epoch: u64,
        binding_secret: &str,
    ) -> Result<Self, &'static str> {
        let origin_url = reqwest::Url::parse(origin).map_err(|_| "CLOUD_CONFIGURATION_REJECTED")?;
        if profile.is_empty()
            || profile.len() > 128
            || profile.chars().any(char::is_control)
            || origin_url.scheme() != "https"
            || origin_url.host_str().is_none()
            || origin_url.origin().ascii_serialization() != origin
            || origin_url.path() != "/"
            || !origin_url.username().is_empty()
            || origin_url.password().is_some()
            || origin_url.query().is_some()
            || origin_url.fragment().is_some()
            || prefix.len() < 2
            || prefix.len() > 64
            || !prefix.starts_with('/')
            || prefix.ends_with('/')
            || !prefix[1..]
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            || connector.is_nil()
            || device.is_nil()
            || epoch == 0
            || binding_secret.len() < 32
        {
            return Err("CLOUD_CONFIGURATION_REJECTED");
        }
        let workspace = workspace
            .canonicalize()
            .map_err(|_| "CLOUD_CONFIGURATION_REJECTED")?;
        if !workspace.is_dir() {
            return Err("CLOUD_CONFIGURATION_REJECTED");
        }
        Ok(Self(Arc::new(Inner {
            profile: profile.into(),
            workspace: workspace.to_string_lossy().into_owned(),
            issuer: format!("{origin}{prefix}/oauth"),
            resource: format!("{origin}{prefix}/mcp/{connector}"),
            connector,
            device,
            epoch,
            key: hmac::Key::new(hmac::HMAC_SHA256, binding_secret.as_bytes()),
            state: Mutex::new(State {
                lease: None,
                last_peer: None,
                seen_boots: HashSet::new(),
                closed: false,
            }),
        })))
    }
    pub(crate) fn for_workspace(&self, profile: &str, workspace: &Path) -> bool {
        self.0.profile == profile
            && workspace
                .canonicalize()
                .is_ok_and(|p| p.to_string_lossy() == self.0.workspace)
    }
    /// The trusted supervisor calls this only after the pinned sidecar confirms
    /// its real authenticated connection. Calling it does not allocate approval.
    pub(crate) fn activate(&self, peer: CloudPeer, ttl: Duration) -> Result<(), &'static str> {
        if peer.connector != self.0.connector
            || peer.device != self.0.device
            || peer.device_epoch != self.0.epoch
            || peer.gateway_boot.is_nil()
            || peer.session.is_nil()
            || peer.generation == 0
            || ttl.is_zero()
            || ttl > Duration::from_secs(30)
        {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| "CLOUD_CONNECTION_REJECTED")?;
        if state.closed {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        if let Some(old) = &state.last_peer {
            if old.gateway_boot == peer.gateway_boot {
                if peer.generation <= old.generation || peer.session == old.session {
                    return Err("CLOUD_CONNECTION_REJECTED");
                }
            } else if state.seen_boots.contains(&peer.gateway_boot) {
                return Err("CLOUD_CONNECTION_REJECTED");
            }
        }
        if !state.seen_boots.contains(&peer.gateway_boot) && state.seen_boots.len() >= 64 {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        state.seen_boots.insert(peer.gateway_boot);
        state.last_peer = Some(peer.clone());
        state.lease = Some(Lease {
            peer,
            until: Instant::now() + ttl,
        });
        Ok(())
    }
    pub(crate) fn renew(&self, peer: &CloudPeer, ttl: Duration) -> Result<(), &'static str> {
        if ttl.is_zero() || ttl > Duration::from_secs(30) {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| "CLOUD_CONNECTION_REJECTED")?;
        if state.closed {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        let lease = state.lease.as_mut().ok_or("CLOUD_CONNECTION_REJECTED")?;
        if &lease.peer != peer || lease.until <= Instant::now() {
            return Err("CLOUD_CONNECTION_REJECTED");
        }
        lease.until = Instant::now() + ttl;
        Ok(())
    }
    pub(crate) fn disconnect(&self, peer: &CloudPeer) {
        if let Ok(mut state) = self.0.state.lock() {
            if state.lease.as_ref().is_some_and(|l| &l.peer == peer) {
                state.lease = None;
            }
        }
    }
    pub(crate) fn ensure_connected(&self) -> Result<(), &'static str> {
        let state = self
            .0
            .state
            .lock()
            .map_err(|_| "CLOUD_CONNECTION_REQUIRED")?;
        if state.closed
            || state
                .lease
                .as_ref()
                .is_none_or(|l| l.until <= Instant::now())
        {
            return Err("CLOUD_CONNECTION_REQUIRED");
        }
        Ok(())
    }
    pub(crate) fn storage_binding(&self) -> String {
        let bytes = serde_json::to_vec(&(
            "ctm-native-cloud-state-v1",
            &self.0.profile,
            &self.0.workspace,
            &self.0.issuer,
            &self.0.resource,
            self.0.connector,
            self.0.device,
            self.0.epoch,
        ))
        .expect("native fixed state identity");
        hmac::sign(&self.0.key, &bytes)
            .as_ref()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }
    pub(crate) fn close(&self) {
        if let Ok(mut state) = self.0.state.lock() {
            state.closed = true;
            state.lease = None;
        }
    }
    pub(crate) fn matches(&self, peer: &CloudPeer) -> bool {
        self.0.state.lock().is_ok_and(|state| {
            !state.closed
                && state
                    .lease
                    .as_ref()
                    .is_some_and(|l| &l.peer == peer && l.until > Instant::now())
        })
    }
    pub(crate) fn request(
        &self,
        conversation: &str,
        service: Arc<ChatAuthorizer>,
    ) -> Result<RemoteRequest, &'static str> {
        let digest = URL_SAFE_NO_PAD
            .decode(conversation)
            .map_err(|_| "CLOUD_CONTEXT_REJECTED")?;
        if digest.len() != 32 || URL_SAFE_NO_PAD.encode(digest) != conversation {
            return Err("CLOUD_CONTEXT_REJECTED");
        }
        let peer = {
            let state = self
                .0
                .state
                .lock()
                .map_err(|_| "CLOUD_CONNECTION_REQUIRED")?;
            if state.closed {
                return Err("CLOUD_CONNECTION_REQUIRED");
            }
            state
                .lease
                .as_ref()
                .filter(|x| x.until > Instant::now())
                .ok_or("CLOUD_CONNECTION_REQUIRED")?
                .peer
                .clone()
        };
        let input = serde_json::to_vec(&(
            "ctm-cloud-native-binding-v1",
            &self.0.profile,
            &self.0.workspace,
            &self.0.issuer,
            &self.0.resource,
            self.0.connector,
            self.0.device,
            self.0.epoch,
            conversation,
        ))
        .map_err(|_| "CLOUD_CONTEXT_REJECTED")?;
        let binding = hmac::sign(&self.0.key, &input)
            .as_ref()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        let credential = CloudCredential {
            link: self.clone(),
            peer,
            binding,
        };
        Ok(RemoteRequest::from_cloud(
            &self.0.profile,
            credential,
            service,
        ))
    }
}
impl CloudCredential {
    pub(super) fn binding(&self) -> &str {
        &self.binding
    }
    pub(super) fn is_current(&self, profile: &str, binding: Option<&str>) -> bool {
        profile == self.link.0.profile
            && binding == Some(self.binding.as_str())
            && self.link.matches(&self.peer)
    }
}
#[cfg(test)]
mod tests;
