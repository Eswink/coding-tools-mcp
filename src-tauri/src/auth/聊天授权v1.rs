//! Conversation approval is a server-side capability, never a model-supplied flag.
//! OpenAI metadata is only a discriminator within the authenticated host boundary.
use std::collections::{BTreeSet, HashMap, HashSet};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use serde::Serialize;
use serde_json::{json, Value};
use ring::hmac;
use super::principal::VerifiedPrincipal;

pub const SCOPES: &[&str] = &[
    "workspace.read", "files.read", "files.write", "exec.run", "task.read",
    "task.manage", "history.read", "history.write", "harness.write",
];
const PENDING: u64 = 90;
const IDLE: u64 = 30 * 60;
const ABSOLUTE: u64 = 8 * 60 * 60;
const MAX_RECORDS: usize = 64;

#[derive(Clone)]
pub(crate) struct RemoteRequest {
    pub profile: String,
    pub principal: Option<VerifiedPrincipal>,
    pub binding: Option<String>,
    pub service: Arc<ChatAuthorizer>,
}
impl RemoteRequest {
    pub fn unresolved(profile: &str) -> Self {
        Self { profile: profile.into(), principal: None, binding: None, service: service() }
    }
    pub fn verified(profile: &str, workspace: &str, principal: VerifiedPrincipal, meta: &Value, secret: &str) -> Self {
        let binding = meta.get("openai/session").and_then(Value::as_str)
            .filter(|s| !s.is_empty() && s.len() <= 256 && !s.chars().any(char::is_control))
            .map(|session| {
                let bytes = serde_json::to_vec(&(profile, workspace, &principal.issuer,
                    &principal.subject, &principal.client_id, session)).expect("binding serialization");
                hmac::sign(&hmac::Key::new(hmac::HMAC_SHA256, secret.as_bytes()), &bytes)
                    .as_ref().iter().map(|b| format!("{b:02x}")).collect()
            });
        Self { profile: profile.into(), principal: Some(principal), binding, service: service() }
    }
    pub fn identity(&self) -> Result<&str, &'static str> {
        if !self.principal.as_ref().is_some_and(VerifiedPrincipal::is_current) {
            return Err("OAUTH_REQUIRED");
        }
        self.binding.as_deref().ok_or("CHAT_CONTEXT_REQUIRED")
    }
}

#[derive(Clone, Serialize)]
pub(crate) struct GrantView {
    pub id: String,
    pub fingerprint: String,
    pub status: String,
    pub scopes: BTreeSet<String>,
    pub created_at: u64,
    pub expires_at: u64,
    pub idle_expires_at: u64,
}
struct Record {
    profile: String,
    binding: String,
    view: GrantView,
    since: Instant,
    touched: Instant,
}
impl Record {
    fn refresh(&mut self, now: Instant) {
        let expired = match self.view.status.as_str() {
            "pending" => now.duration_since(self.since) >= Duration::from_secs(PENDING),
            "active" => now.duration_since(self.since) >= Duration::from_secs(ABSOLUTE)
                || now.duration_since(self.touched) >= Duration::from_secs(IDLE),
            _ => false,
        };
        if expired { self.view.status = "expired".into(); }
    }
}
#[derive(Default)]
struct State { records: HashMap<String, Record>, exclusive: HashSet<String> }
#[derive(Default)]
pub(crate) struct ChatAuthorizer { state: Mutex<State> }
pub(crate) fn service() -> Arc<ChatAuthorizer> {
    static INSTANCE: OnceLock<Arc<ChatAuthorizer>> = OnceLock::new();
    INSTANCE.get_or_init(|| Arc::new(ChatAuthorizer::default())).clone()
}
pub(crate) fn unix_now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}
fn denied(code: &str) -> Value {
    crate::tools::workspace::tool_err_code("CHAT_AUTHORIZATION_REQUIRED", code, "permission")
}
impl ChatAuthorizer {
    pub fn status(&self, req: &RemoteRequest) -> Value {
        let key = match req.identity() { Ok(k) => k, Err(e) => return denied(e) };
        let mut state = self.state.lock().expect("chat authorization lock");
        let record = state.records.get_mut(key).filter(|r| r.profile == req.profile);
        match record {
            Some(r) => { r.refresh(Instant::now()); json!({"ok":true,"authorization":r.view}) }
            None => json!({"ok":true,"authorization":{"status":"unauthorized"}}),
        }
    }
    pub fn request(&self, req: &RemoteRequest, args: &Value) -> Value {
        let key = match req.identity() { Ok(k) => k, Err(e) => return denied(e) };
        let Some(obj) = args.as_object() else { return denied("INVALID_AUTHORIZATION_REQUEST"); };
        if obj.keys().any(|k| k != "scopes") { return denied("INVALID_AUTHORIZATION_REQUEST"); }
        let requested: BTreeSet<String> = match obj.get("scopes") {
            None => ["workspace.read", "files.read", "task.read", "history.read"].iter().map(|s| (*s).into()).collect(),
            Some(v) => match v.as_array().filter(|v| !v.is_empty() && v.len() <= SCOPES.len()) {
                Some(v) if v.iter().all(|s| s.as_str().is_some_and(|s| SCOPES.contains(&s))) =>
                    v.iter().map(|s| s.as_str().unwrap().into()).collect(),
                _ => return denied("INVALID_SCOPES"),
            }
        };
        let mut state = self.state.lock().expect("chat authorization lock");
        let now = Instant::now();
        for r in state.records.values_mut() { r.refresh(now); }
        if let Some(r) = state.records.get(key).filter(|r| r.profile == req.profile) {
            // Idempotency: retries neither extend a deadline nor broaden permissions.
            if r.view.status == "pending" || r.view.status == "active" {
                return json!({"ok":true,"authorization":r.view});
            }
        }
        state.records.retain(|_, r| r.view.status == "active" || r.view.status == "pending");
        if state.records.values().filter(|r| r.profile == req.profile).count() >= MAX_RECORDS
            || state.records.len() >= 1024 { return denied("AUTHORIZATION_CAPACITY_REACHED"); }
        let wall = unix_now();
        let view = GrantView { id: uuid::Uuid::new_v4().to_string(), fingerprint: key[..16].into(),
            status: "pending".into(), scopes: requested, created_at: wall,
            expires_at: wall + PENDING, idle_expires_at: wall + PENDING };
        state.records.insert(key.into(), Record { profile: req.profile.clone(), binding: key.into(), view: view.clone(), since: now, touched: now });
        json!({"ok":true,"authorization":view,"next":"Approve this fingerprint in the local desktop. Do not send any password or token in chat."})
    }
    /// Called ONLY by trusted local IPC. The model cannot invoke approval or revoke-all.
    pub fn decide(&self, profile: &str, id: &str, approve: bool, scopes: &[String]) -> Result<(), String> {
        let mut state = self.state.lock().map_err(|_| "授权状态不可用")?;
        let now = Instant::now();
        for r in state.records.values_mut() { r.refresh(now); }
        let key = state.records.iter().find(|(_,r)| r.profile == profile && r.view.id == id)
            .map(|(k,_)| k.clone()).ok_or("请求不存在或已过期")?;
        let r = state.records.get(&key).unwrap();
        if r.view.status != "pending" { return Err("只能审批待授权请求".into()); }
        let selected: BTreeSet<String> = scopes.iter().cloned().collect();
        if approve && (selected.is_empty() || !selected.is_subset(&r.view.scopes)) {
            return Err("批准权限必须是所申请权限的非空子集".into());
        }
        if approve && state.exclusive.contains(profile) {
            for r in state.records.values_mut().filter(|r| r.profile == profile && r.view.status == "active") {
                r.view.status = "revoked".into();
            }
        }
        let r = state.records.get_mut(&key).unwrap();
        r.view.status = if approve { "active" } else { "denied" }.into();
        if approve {
            r.view.scopes = selected; r.since = now; r.touched = now;
            r.view.expires_at = unix_now() + ABSOLUTE; r.view.idle_expires_at = unix_now() + IDLE;
        }
        Ok(())
    }
    pub fn revoke(&self, profile: &str, id: Option<&str>) {
        let mut state = self.state.lock().expect("chat authorization lock");
        for r in state.records.values_mut().filter(|r| r.profile == profile && id.is_none_or(|id| r.view.id == id)) {
            r.view.status = "revoked".into();
        }
    }
    pub fn set_exclusive(&self, profile: &str, enabled: bool) {
        let mut state = self.state.lock().expect("chat authorization lock");
        if enabled {
            state.exclusive.insert(profile.into());
            // No ambiguous existing winner: changing to exclusive closes every grant.
            for r in state.records.values_mut().filter(|r| r.profile == profile) { r.view.status = "revoked".into(); }
        } else { state.exclusive.remove(profile); }
    }
    pub fn snapshot(&self, profile: &str) -> Value {
        let mut state = self.state.lock().expect("chat authorization lock");
        let mut views: Vec<_> = state.records.values_mut().filter(|r| r.profile == profile).map(|r| {
            r.refresh(Instant::now()); r.view.clone()
        }).collect();
        views.sort_by(|a,b| a.id.cmp(&b.id));
        json!({"records":views,"exclusive":state.exclusive.contains(profile),"available_scopes":SCOPES})
    }
    pub fn permit(&self, req: &RemoteRequest, scopes: &[&str]) -> Result<(), &'static str> {
        let key = req.identity()?;
        let mut state = self.state.lock().map_err(|_| "AUTHORIZATION_UNAVAILABLE")?;
        let r = state.records.get_mut(key).ok_or("CHAT_NOT_APPROVED")?;
        r.refresh(Instant::now());
        if r.profile != req.profile || r.binding != key || r.view.status != "active" { return Err("CHAT_NOT_APPROVED"); }
        if scopes.iter().any(|s| !r.view.scopes.contains(*s)) { return Err("INSUFFICIENT_CHAT_SCOPE"); }
        r.touched = Instant::now(); r.view.idle_expires_at = unix_now() + IDLE;
        Ok(())
    }
}
#[cfg(test)]
#[path = "聊天授权回归v1.rs"]
mod tests;
