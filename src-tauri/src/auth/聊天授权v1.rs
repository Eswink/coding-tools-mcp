//! Conversation approval is local-only. OAuth refresh never transfers a lease.
use std::collections::{BTreeSet, HashMap};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use serde::Serialize;
use serde_json::{json, Value};
use ring::hmac;
use super::{principal::VerifiedPrincipal, session_policy::SessionPolicy,
    exclusive_lease::{Owner, Phase}, chat_events::ChatEvent};
use super::local_authority::{AuthorityEpochStore, LocalAdmissionPermit, LocalAdmissionTicket, LocalAuthorityPhase, LocalAuthoritySnapshot, LocalExecutionState};

pub const SCOPES: &[&str] = &[
    "workspace.read", "files.read", "files.write", "exec.run", "task.read",
    "task.manage", "history.read", "history.write", "harness.write",
];
const PENDING: u64 = 90;
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
    pub id: String, pub fingerprint: String, pub status: String,
    pub scopes: BTreeSet<String>, pub created_at: u64, pub expires_at: u64,
    pub idle_expires_at: u64,
}
struct Record {
    profile: String, binding: String, view: GrantView,
    since: Instant, touched: Instant, lease_seconds: u64, idle_seconds: u64,
}
impl Record {
    fn refresh(&mut self, now: Instant) {
        let expired = match self.view.status.as_str() {
            "pending" => now.duration_since(self.since) >= Duration::from_secs(PENDING),
            "active" => now.duration_since(self.since) >= Duration::from_secs(self.lease_seconds)
                || (self.idle_seconds != 0 && now.duration_since(self.touched) >= Duration::from_secs(self.idle_seconds)),
            _ => false,
        };
        if expired { self.view.status = "expired".into(); }
    }
}
#[derive(Default)]
struct State {
    records: HashMap<String, Record>, owners: HashMap<String, Owner>,
    policies: HashMap<String, SessionPolicy>, flights: HashMap<String, usize>,
    epoch: u64, revision: u64,
}
#[derive(Clone)]
struct WorkSource {
    sessions: Arc<crate::tools::session::SessionStore>,
    tasks: Arc<crate::tools::exec_tasks::ExecTaskStore>,
}
pub(crate) struct ChatAuthorizer {
    state: Mutex<State>, work: Mutex<HashMap<String, Vec<WorkSource>>>,
    fences: Mutex<HashMap<String, Arc<super::execution_fence::ExecutionFence>>>,
    authority_epochs: Mutex<HashMap<String, Arc<AuthorityEpochStore>>>,
    events: tokio::sync::broadcast::Sender<ChatEvent>,
}
impl Default for ChatAuthorizer {
    fn default() -> Self {
        Self { state: Mutex::default(), work: Mutex::default(), fences:Mutex::default(), authority_epochs:Mutex::default(), events: tokio::sync::broadcast::channel(128).0 }
    }
}
pub(crate) struct AdmissionGuard { service: Arc<ChatAuthorizer>, profile: String }
impl Drop for AdmissionGuard {
    fn drop(&mut self) {
        if let Ok(mut state) = self.service.state.lock() {
            if let Some(n) = state.flights.get_mut(&self.profile) { *n = n.saturating_sub(1); }
            state.epoch = state.epoch.wrapping_add(1);
        }
    }
}
pub(crate) fn service() -> Arc<ChatAuthorizer> {
    static INSTANCE: OnceLock<Arc<ChatAuthorizer>> = OnceLock::new();
    INSTANCE.get_or_init(|| Arc::new(ChatAuthorizer::default())).clone()
}
pub(crate) fn unix_now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}
fn denied(code: &str) -> Value {
    if ["EXCLUSIVE_CHAT_LOCKED","CHAT_WORK_DRAINING","CHAT_RECOVERY_REQUIRED"].contains(&code) {
        return json!({"ok":false,"error":{"code":code,"category":"permission",
            "message":"This workspace is reserved by another conversation or is draining prior work. Do not request authorization or poll. The desktop owner controls release.",
            "retryable":false},"requires_local_action":false});
    }
    crate::tools::workspace::tool_err_code("CHAT_AUTHORIZATION_REQUIRED", code, "permission")
}
impl ChatAuthorizer {
    pub(crate) fn attach_storage(&self, profile:&str, root:&std::path::Path, harness_root:&std::path::Path)->Result<(),String> {
        let mut fences=self.fences.lock().map_err(|_|"执行恢复锁不可用")?;
        let mut authority_epochs=self.authority_epochs.lock().map_err(|_|"本地授权版本不可用")?;
        let fence_exists=fences.contains_key(profile);
        let epoch_exists=authority_epochs.contains_key(profile);
        if fence_exists || epoch_exists {
            if fence_exists && epoch_exists { return Ok(()); }
            return Err("本地授权存储状态不一致；未允许远程执行".into());
        }
        // Open both authenticated namespaces before publishing either one.
        let fence=Arc::new(super::execution_fence::ExecutionFence::open(root)?);
        let authority_epoch=Arc::new(AuthorityEpochStore::open(root)?);
        for binding in fence.bindings() {
            let tasks=crate::tools::exec_tasks::ExecTaskStore::shared(harness_root.join("chat-v1").join(binding).join("exec-tasks-v1"));
            tasks.bind_profile(profile);
            self.register_work(profile,Arc::new(crate::tools::session::SessionStore::new()),tasks);
        }
        fences.insert(profile.into(),fence);
        authority_epochs.insert(profile.into(),authority_epoch);
        Ok(())
    }
    fn fence(&self,profile:&str)->Option<Arc<super::execution_fence::ExecutionFence>> {
        self.fences.lock().expect("execution fences").get(profile).cloned()
    }
    fn authority_epoch(&self,profile:&str)->Result<u64,&'static str> {
        self.authority_epochs.lock().map_err(|_|"LOCAL_AUTHORITY_UNAVAILABLE")?
            .get(profile).ok_or("LOCAL_AUTHORITY_UNAVAILABLE")?.epoch()
    }
    pub(crate) fn acknowledge_recovery(&self,profile:&str,generation:&str)->Result<(),String> {
        if self.busy(profile){return Err("仍有运行中或终止状态未确认的任务，请先在异步任务面板处理".into());}
        let mut state=self.state.lock().map_err(|_|"授权状态不可用")?;
        if state.flights.get(profile).copied().unwrap_or(0)>0{return Err("仍有在途调用".into());}
        self.fence(profile).ok_or("没有恢复锁")?.acknowledge(generation)?;
        self.event(&mut state,profile,"changed",None);Ok(())
    }

    pub(crate) fn subscribe(&self) -> tokio::sync::broadcast::Receiver<ChatEvent> { self.events.subscribe() }
    fn event(&self, state: &mut State, profile: &str, kind: &'static str, id: Option<String>) {
        state.revision = state.revision.wrapping_add(1);
        // Bounded nonblocking queue only; no UI callback or executor lock under state.
        let _ = self.events.send(ChatEvent { revision: state.revision, profile: profile.into(), kind, request_id: id });
    }
    fn policy(state: &State, profile: &str) -> SessionPolicy { state.policies.get(profile).cloned().unwrap_or_default() }
    pub(crate) fn configure(&self, profile: &str, policy: &SessionPolicy) -> Result<(), String> {
        policy.validate()?;
        self.reconcile(profile);
        let mut state = self.state.lock().map_err(|_| "授权状态不可用")?;
        if Self::policy(&state, profile) != *policy {
            Self::revoke_locked(&mut state, profile, None);
            Self::drain_transition(&mut state,profile);
            state.policies.insert(profile.into(), policy.clone());
            self.event(&mut state, profile, "changed", None);
        }
        Ok(())
    }
    pub(crate) fn register_work(&self, profile: &str, sessions: Arc<crate::tools::session::SessionStore>, tasks: Arc<crate::tools::exec_tasks::ExecTaskStore>) {
        let mut work = self.work.lock().expect("chat work registry");
        let sources = work.entry(profile.into()).or_default();
        if !sources.iter().any(|s| Arc::ptr_eq(&s.sessions, &sessions)) { sources.push(WorkSource { sessions, tasks }); }
    }
    pub(crate) fn cancel_local_sessions(&self,profile:&str) {
        let sources=self.work.lock().expect("chat work registry").get(profile).cloned().unwrap_or_default();
        for source in sources {source.sessions.cancel_local();}
        self.reconcile(profile);
    }
    fn busy(&self, profile: &str) -> bool {
        let sources = self.work.lock().expect("chat work registry").get(profile).cloned().unwrap_or_default();
        sources.iter().any(|s| s.sessions.has_unfinished_work() || s.tasks.has_unfinished_work())
            || crate::tools::exec_tasks::ExecTaskStore::live_for_profile(profile).iter().any(|s| s.has_unfinished_work())
    }
    /// Freeze admission first; only inspect executors after releasing the state lock.
    fn reconcile(&self, profile: &str) {
        let check = {
            let mut state = self.state.lock().expect("chat authorization lock");
            let now = Instant::now();
            let mut changed = false;
            for r in state.records.values_mut().filter(|r| r.profile == profile) {
                let old = r.view.status.clone(); r.refresh(now); changed |= old != r.view.status;
            }
            if let Some(owner) = state.owners.get(profile).cloned() {
                let valid = state.records.get(&owner.binding).is_some_and(|r|
                    r.view.id == owner.request_id && matches!(r.view.status.as_str(), "pending" | "active"));
                if !valid && owner.phase != Phase::Draining {
                    state.owners.get_mut(profile).unwrap().phase = Phase::Draining; changed = true;
                }
            }
            if changed { self.event(&mut state, profile, "changed", None); }
            (state.flights.get(profile).copied().unwrap_or(0)==0).then(||(
                state.owners.get(profile).filter(|o|o.phase==Phase::Draining).map(|o|o.request_id.clone()),state.epoch))
        };
        if let Some((id, epoch)) = check {
            if self.busy(profile) { return; }
            let mut state = self.state.lock().expect("chat authorization lock");
            if state.epoch == epoch && state.flights.get(profile).copied().unwrap_or(0) == 0 {
                // Serialized commit: no new admission can start between checking quiescence and clearing the durable bit.
                if self.fence(profile).is_some_and(|f|f.clear_quiet().is_err()){return;}
                if id.as_ref().is_some_and(|id|state.owners.get(profile).is_some_and(|o|&o.request_id==id&&o.phase==Phase::Draining)) {
                    state.owners.remove(profile); self.event(&mut state, profile, "changed", None);
                }
            }
        }
    }
    fn owner_check(state: &State, profile: &str, key: &str) -> Result<(), &'static str> {
        if let Some(owner) = state.owners.get(profile) {
            if owner.phase == Phase::Draining { return Err("CHAT_WORK_DRAINING"); }
            if owner.binding != key { return Err("EXCLUSIVE_CHAT_LOCKED"); }
        }
        Ok(())
    }
    pub fn status(&self, req: &RemoteRequest) -> Value {
        let key = match req.identity() { Ok(k) => k, Err(e) => return denied(e) };
        self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|f|!f.ready()){return denied("CHAT_RECOVERY_REQUIRED");}
        let state = self.state.lock().expect("chat authorization lock");
        if let Err(e) = Self::owner_check(&state, &req.profile, key) { return denied(e); }
        match state.records.get(key).filter(|r| r.profile == req.profile) {
            Some(r) => json!({"ok":true,"authorization":r.view}),
            None => json!({"ok":true,"authorization":{"status":"unauthorized"}}),
        }
    }
    // Compatibility helper for the crate's authorization state-machine tests.
    // Production remote dispatch always uses request_guarded so it can apply
    // the workspace-allocation guard without changing OAuth semantics.
    #[cfg(test)]
    pub fn request(&self, req: &RemoteRequest, args: &Value) -> Value {
        self.request_guarded(req, args, || Ok::<(), Value>(()))
    }

    pub(crate) fn request_guarded<G, F>(
        &self,
        req: &RemoteRequest,
        args: &Value,
        acquire_new_allocation_guard: F,
    ) -> Value
    where
        F: FnOnce() -> Result<G, Value>,
    {
        let key = match req.identity() { Ok(k) => k, Err(e) => return denied(e) };
        self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|f|!f.ready()){return denied("CHAT_RECOVERY_REQUIRED");}
        let mut state = self.state.lock().expect("chat authorization lock");
        // Preserve the original request-validation contract before returning
        // an existing grant or consulting execution availability.
        if let Err(e) = Self::owner_check(&state, &req.profile, key) { return denied(e); }
        let Some(obj) = args.as_object() else { return denied("INVALID_AUTHORIZATION_REQUEST"); };
        if obj.keys().any(|k| k != "scopes") { return denied("INVALID_AUTHORIZATION_REQUEST"); }
        let requested: BTreeSet<String> = match obj.get("scopes") {
            None => ["workspace.read", "files.read", "task.read", "history.read"].iter().map(|s| (*s).into()).collect(),
            Some(v) => match v.as_array().filter(|v| !v.is_empty() && v.len() <= SCOPES.len()) {
                Some(v) if v.iter().all(|s| s.as_str().is_some_and(|s| SCOPES.contains(&s))) => v.iter().map(|s| s.as_str().unwrap().into()).collect(),
                _ => return denied("INVALID_SCOPES"),
            }
        };
        if let Some(r) = state.records.get(key).filter(|r| r.profile == req.profile) {
            if matches!(r.view.status.as_str(), "pending" | "active") {
                return json!({"ok":true,"authorization":r.view});
            }
        }

        // This guard is acquired while the authorization mutex is held and is
        // retained until the new pending record/event has committed. That makes
        // pause-vs-authorization allocation linearizable without coupling the
        // authorizer to a concrete workspace-availability implementation.
        let _new_allocation_guard = match acquire_new_allocation_guard() {
            Ok(guard) => guard,
            Err(value) => return value,
        };

        let now = Instant::now();
        for r in state.records.values_mut() { r.refresh(now); }
        state.records.retain(|_, r| matches!(r.view.status.as_str(), "active" | "pending"));
        if state.records.values().filter(|r| r.profile == req.profile).count() >= MAX_RECORDS || state.records.len() >= 1024 {
            return denied("AUTHORIZATION_CAPACITY_REACHED");
        }
        let wall = unix_now(); let policy = Self::policy(&state, &req.profile);
        let view = GrantView { id: uuid::Uuid::new_v4().to_string(), fingerprint: key[..16].into(), status: "pending".into(),
            scopes: requested, created_at: wall, expires_at: wall + PENDING, idle_expires_at: wall + PENDING };
        state.records.insert(key.into(), Record { profile: req.profile.clone(), binding: key.into(), view: view.clone(),
            since: now, touched: now, lease_seconds: policy.chat_lease_ttl_seconds, idle_seconds: policy.chat_idle_timeout_seconds });
        if policy.exclusive { state.owners.insert(req.profile.clone(), Owner { binding: key.into(), request_id: view.id.clone(), phase: Phase::Reserved }); }
        self.event(&mut state, &req.profile, "pending", Some(view.id.clone()));
        json!({"ok":true,"authorization":view,"next":"Approve this fingerprint in the local desktop. Do not send any password or token in chat."})
    }
    pub fn decide(&self, profile: &str, id: &str, approve: bool, scopes: &[String]) -> Result<(), String> {
        self.reconcile(profile);
        let mut state = self.state.lock().map_err(|_| "授权状态不可用")?;
        self.decide_locked(&mut state, profile, id, approve, scopes, Instant::now())
    }
    /// The decision mutex is the authorization linearization point. Reconciliation
    /// may have waited on executor/storage locks; its earlier TTL check is stale.
    fn decide_locked(&self, state: &mut State, profile: &str, id: &str, approve: bool,
        scopes: &[String], now: Instant) -> Result<(), String> {
        let key = state.records.iter().find(|(_,r)| r.profile == profile && r.view.id == id)
            .map(|(k,_)| k.clone()).ok_or("请求不存在或已过期")?;
        Self::owner_check(state, profile, &key).map_err(str::to_string)?;
        let r = state.records.get_mut(&key).unwrap();
        let old_status = r.view.status.clone();
        r.refresh(now);
        if old_status != r.view.status {
            if let Some(owner) = state.owners.get_mut(profile)
                .filter(|o| o.binding == key && o.request_id == id) {
                owner.phase = Phase::Draining;
            }
            self.event(state, profile, "changed", Some(id.into()));
        }
        let r = state.records.get(&key).unwrap();
        if r.view.status != "pending" { return Err("只能审批待授权请求".into()); }
        let selected: BTreeSet<String> = scopes.iter().cloned().collect();
        if approve && (selected.is_empty() || !selected.is_subset(&r.view.scopes)) { return Err("批准权限必须是所申请权限的非空子集".into()); }
        let r = state.records.get_mut(&key).unwrap();
        r.view.status = if approve { "active" } else { "denied" }.into();
        if approve {
            r.view.scopes = selected; r.since = now; r.touched = now;
            r.view.expires_at = unix_now() + r.lease_seconds;
            r.view.idle_expires_at = if r.idle_seconds == 0 { r.view.expires_at } else { r.view.expires_at.min(unix_now() + r.idle_seconds) };
        }
        if let Some(owner) = state.owners.get_mut(profile) { owner.phase = if approve { Phase::Active } else { Phase::Draining }; }
        self.event(state, profile, "changed", Some(id.into()));
        Ok(())
    }
    fn drain_transition(state:&mut State,profile:&str) {
        state.owners.entry(profile.into()).or_insert_with(||Owner {
            binding:String::new(),request_id:uuid::Uuid::new_v4().to_string(),phase:Phase::Draining });
    }
    fn revoke_locked(state: &mut State, profile: &str, id: Option<&str>) {
        for r in state.records.values_mut().filter(|r| r.profile == profile && id.is_none_or(|id| r.view.id == id)) { r.view.status = "revoked".into(); }
        if let Some(owner) = state.owners.get_mut(profile).filter(|o| id.is_none_or(|id| o.request_id == id)) { owner.phase = Phase::Draining; }
    }
    pub fn revoke(&self, profile: &str, id: Option<&str>) {
        let mut state = self.state.lock().expect("chat authorization lock");
        Self::revoke_locked(&mut state, profile, id); self.event(&mut state, profile, "changed", id.map(str::to_string));
    }
    #[cfg(test)]
    pub fn set_exclusive(&self, profile: &str, enabled: bool) {
        self.reconcile(profile);
        let mut state = self.state.lock().expect("chat authorization lock");
        // Explicit local mode changes revoke rather than silently promote a winner.
        Self::revoke_locked(&mut state, profile, None);
        Self::drain_transition(&mut state,profile);
        let mut policy = Self::policy(&state, profile); policy.exclusive = enabled;
        state.policies.insert(profile.into(), policy); self.event(&mut state, profile, "changed", None);
    }
    pub fn snapshot(&self, profile: &str) -> Value {
        self.reconcile(profile);
        let state = self.state.lock().expect("chat authorization lock");
        let mut views: Vec<_> = state.records.values().filter(|r| r.profile == profile).map(|r| r.view.clone()).collect();
        views.sort_by(|a,b| a.id.cmp(&b.id));
        json!({"records":views,"exclusive":Self::policy(&state,profile).exclusive,"available_scopes":SCOPES,
            "lease_state":state.owners.get(profile).map(|o|serde_json::to_value(o.phase).unwrap()).unwrap_or(json!("free")),
            "revision":state.revision,"policy":Self::policy(&state,profile),
            "recovery":self.fence(profile).map(|f|f.snapshot()).unwrap_or(json!({"required":false}))})
    }
    /// Export only this already-approved conversation's local authority.
    /// This function cannot create or widen a grant and does not touch idle TTL.
    #[cfg_attr(not(test), allow(dead_code))]
    pub(crate) fn local_authority_snapshot(
        &self,
        req: &RemoteRequest,
        gate: &crate::runtime::WorkspaceExecutionGate,
    ) -> Result<LocalAuthoritySnapshot, &'static str> {
        let key = req.identity()?;
        self.reconcile(&req.profile);
        let authority_epoch = self.authority_epoch(&req.profile)?;
        let recovery_required = self.fence(&req.profile).is_some_and(|fence| !fence.ready());
        let mut state = self
            .state
            .lock()
            .map_err(|_| "LOCAL_AUTHORITY_UNAVAILABLE")?;
        let owner = state.owners.get(&req.profile).cloned();
        if owner.as_ref().is_some_and(|owner| owner.binding != key) {
            return Err("EXCLUSIVE_CHAT_LOCKED");
        }
        let revision = state.revision;
        let record = state.records.get_mut(key).ok_or("CHAT_NOT_APPROVED")?;
        record.refresh(Instant::now());
        if record.profile != req.profile || record.binding != key {
            return Err("CHAT_NOT_APPROVED");
        }
        let owner_matches = owner
            .as_ref()
            .is_some_and(|owner| owner.binding == key && owner.request_id == record.view.id);
        let phase = if recovery_required {
            if !owner_matches {
                return Err("CHAT_RECOVERY_REQUIRED");
            }
            LocalAuthorityPhase::RecoveryRequired
        } else if owner
            .as_ref()
            .is_some_and(|owner| owner.phase == Phase::Draining)
        {
            if !owner_matches {
                return Err("CHAT_WORK_DRAINING");
            }
            LocalAuthorityPhase::Draining
        } else {
            if record.view.status != "active"
                || owner
                    .as_ref()
                    .is_some_and(|owner| owner.phase != Phase::Active)
            {
                return Err("CHAT_NOT_APPROVED");
            }
            LocalAuthorityPhase::Active
        };
        let view = record.view.clone();
        let gate_snapshot = gate.snapshot();
        let execution_state = if phase == LocalAuthorityPhase::Active {
            gate_snapshot.availability.into()
        } else {
            LocalExecutionState::Offline
        };
        Ok(LocalAuthoritySnapshot::new(
            phase,
            key.to_string(),
            view.id,
            view.scopes,
            view.created_at,
            view.expires_at,
            view.idle_expires_at,
            authority_epoch,
            revision,
            gate_snapshot.generation,
            execution_state,
        ))
    }

    /// Mint a process-local hand-off ticket from current local authority only.
    /// The ticket is intentionally not serializable or cloneable.
    #[cfg_attr(not(test), allow(dead_code))]
    pub(crate) fn issue_local_admission_ticket(
        &self,
        req: &RemoteRequest,
        scopes: &[&str],
        gate: &crate::runtime::WorkspaceExecutionGate,
    ) -> Result<LocalAdmissionTicket, &'static str> {
        let key = req.identity()?;
        self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|fence| !fence.ready()) {
            return Err("CHAT_RECOVERY_REQUIRED");
        }
        if scopes.is_empty() {
            return Err("INSUFFICIENT_CHAT_SCOPE");
        }
        let authority_epoch = self.authority_epoch(&req.profile)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "LOCAL_AUTHORITY_UNAVAILABLE")?;
        Self::owner_check(&state, &req.profile, key)?;
        let record = state.records.get_mut(key).ok_or("CHAT_NOT_APPROVED")?;
        record.refresh(Instant::now());
        if record.profile != req.profile || record.binding != key || record.view.status != "active"
        {
            return Err("CHAT_NOT_APPROVED");
        }
        if scopes
            .iter()
            .any(|scope| !record.view.scopes.contains(*scope))
        {
            return Err("INSUFFICIENT_CHAT_SCOPE");
        }
        let grant_id = record.view.id.clone();
        let required_scopes = scopes.iter().map(|scope| (*scope).to_string()).collect();
        let authority_revision = state.revision;
        // Lock order stays authorization -> execution gate, matching the
        // existing guarded authorization allocation path.
        let gate_snapshot = gate.snapshot();
        if gate_snapshot.availability == crate::runtime::ExecutionAvailability::Offline {
            return Err("WORKSPACE_OFFLINE");
        }
        Ok(LocalAdmissionTicket::new(
            req.profile.clone(),
            key.to_string(),
            grant_id,
            required_scopes,
            authority_epoch,
            authority_revision,
            gate_snapshot.generation,
        ))
    }

    /// Final local linearization point immediately before future tool dispatch.
    /// Any authority/gate transition after ticket issuance rejects the ticket.
    #[cfg_attr(not(test), allow(dead_code))]
    pub(crate) fn commit_local_admission(
        self: &Arc<Self>,
        req: &RemoteRequest,
        gate: &Arc<crate::runtime::WorkspaceExecutionGate>,
        ticket: LocalAdmissionTicket,
    ) -> Result<LocalAdmissionPermit, &'static str> {
        if ticket.expired() {
            return Err("LOCAL_ADMISSION_EXPIRED");
        }
        let key = req.identity()?;
        if ticket.profile != req.profile || ticket.binding != key {
            return Err("LOCAL_ADMISSION_MISMATCH");
        }
        self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|fence| !fence.ready()) {
            return Err("CHAT_RECOVERY_REQUIRED");
        }
        if self.authority_epoch(&req.profile)? != ticket.authority_epoch {
            return Err("LOCAL_AUTHORITY_CHANGED");
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| "LOCAL_AUTHORITY_UNAVAILABLE")?;
        if state.revision != ticket.authority_revision {
            return Err("LOCAL_AUTHORITY_CHANGED");
        }
        Self::owner_check(&state, &req.profile, key)?;
        let record = state.records.get_mut(key).ok_or("CHAT_NOT_APPROVED")?;
        record.refresh(Instant::now());
        if record.profile != req.profile
            || record.binding != key
            || record.view.status != "active"
            || record.view.id != ticket.grant_id
        {
            return Err("CHAT_NOT_APPROVED");
        }
        if ticket
            .required_scopes
            .iter()
            .any(|scope| !record.view.scopes.contains(scope))
        {
            return Err("INSUFFICIENT_CHAT_SCOPE");
        }
        // Auth mutex is still held here: a pause/revoke that wins before this
        // point invalidates generation/revision; a commit that wins here is an
        // established in-flight operation and retains the existing semantics.
        let execution = gate.try_admit_generation(ticket.execution_generation)?;
        let scope_refs: Vec<&str> = ticket.required_scopes.iter().map(String::as_str).collect();
        Self::permit_locked(&mut state, req, key, &scope_refs)?;
        *state.flights.entry(req.profile.clone()).or_default() += 1;
        state.epoch = state.epoch.wrapping_add(1);
        let chat = AdmissionGuard {
            service: self.clone(),
            profile: req.profile.clone(),
        };
        drop(state);
        if ticket.required_scopes.contains("exec.run") {
            if let Some(fence) = self.fence(&req.profile) {
                fence.mark(key)?;
            }
        }
        Ok(LocalAdmissionPermit::new(chat, execution))
    }

    fn permit_locked(state: &mut State, req: &RemoteRequest, key: &str, scopes: &[&str]) -> Result<(), &'static str> {
        Self::owner_check(state,&req.profile,key)?;
        let r = state.records.get_mut(key).ok_or("CHAT_NOT_APPROVED")?;
        r.refresh(Instant::now());
        if r.profile != req.profile || r.binding != key || r.view.status != "active" { return Err("CHAT_NOT_APPROVED"); }
        if scopes.iter().any(|s| !r.view.scopes.contains(*s)) { return Err("INSUFFICIENT_CHAT_SCOPE"); }
        r.touched = Instant::now();
        r.view.idle_expires_at = if r.idle_seconds == 0 { r.view.expires_at } else { r.view.expires_at.min(unix_now() + r.idle_seconds) };
        Ok(())
    }
    pub fn permit(&self, req: &RemoteRequest, scopes: &[&str]) -> Result<(), &'static str> {
        let key = req.identity()?; self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|f|!f.ready()){return Err("CHAT_RECOVERY_REQUIRED");}
        let mut state = self.state.lock().map_err(|_| "AUTHORIZATION_UNAVAILABLE")?;
        Self::permit_locked(&mut state,req,key,scopes)
    }
    pub(crate) fn admit(self: &Arc<Self>, req: &RemoteRequest, scopes: &[&str]) -> Result<AdmissionGuard, &'static str> {
        let key = req.identity()?; self.reconcile(&req.profile);
        if self.fence(&req.profile).is_some_and(|f|!f.ready()){return Err("CHAT_RECOVERY_REQUIRED");}
        let mut state = self.state.lock().map_err(|_| "AUTHORIZATION_UNAVAILABLE")?;
        Self::permit_locked(&mut state,req,key,scopes)?;
        *state.flights.entry(req.profile.clone()).or_default() += 1; state.epoch = state.epoch.wrapping_add(1);
        let guard=AdmissionGuard { service:self.clone(), profile:req.profile.clone() };
        drop(state);
        if scopes.contains(&"exec.run") {
            if let Some(fence)=self.fence(&req.profile){fence.mark(key)?;}
        }
        Ok(guard)
    }
}
#[cfg(test)]
#[path = "聊天授权回归v1.rs"]
mod tests;
#[cfg(test)]
#[path = "exclusive_lease_tests.rs"]
mod exclusive_tests;

#[cfg(test)]
#[path = "chat_decision_tests.rs"]
mod decision_tests;

#[path = "chat_inbox.rs"]
mod inbox;
#[cfg(test)]
#[path = "chat_inbox_tests.rs"]
mod inbox_tests;
