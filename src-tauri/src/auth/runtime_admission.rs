//! Process-local lifetime observation for already-committed desktop authority.
//! No external constructor, serialization, grant creation, or lease extension.
use super::{ChatAuthorizer, LocalAdmissionPermit, LocalAdmissionTicket, Phase, Record, RemoteRequest};
use std::collections::BTreeSet;
use std::fmt;
use std::sync::{Arc, TryLockError};
use std::time::{Duration, Instant};

pub(crate) struct RuntimeAdmission {
    _permit: LocalAdmissionPermit,
    service: Arc<ChatAuthorizer>,
    profile: String,
    binding: String,
    grant_id: String,
    required_scopes: BTreeSet<String>,
    deadline: Instant,
}

impl ChatAuthorizer {
    pub(crate) fn commit_runtime_admission(
        self: &Arc<Self>,
        request: &RemoteRequest,
        gate: &Arc<crate::runtime::WorkspaceExecutionGate>,
        ticket: LocalAdmissionTicket,
    ) -> Result<RuntimeAdmission, &'static str> {
        let profile = ticket.profile.clone();
        let binding = ticket.binding.clone();
        let grant_id = ticket.grant_id.clone();
        let required_scopes = ticket.required_scopes.clone();
        let handoff_expires = ticket.expires;
        let permit = self.commit_local_admission(request, gate, ticket)?;
        // Keep this lock in a nested scope. Permit destruction reacquires the
        // authorizer mutex, so it must never occur while this scope owns it.
        let deadline = {
            let state = self.state.lock().map_err(|_| "LOCAL_AUTHORITY_UNAVAILABLE")?;
            let now = Instant::now();
            if now >= handoff_expires {
                return Err("LOCAL_ADMISSION_EXPIRED");
            }
            let record = state.records.get(&binding).ok_or("CHAT_NOT_APPROVED")?;
            if record.profile != profile
                || record.binding != binding
                || record.view.id != grant_id
                || record.view.status != "active"
                || !required_scopes.is_subset(&record.view.scopes)
                || state.owners.get(&profile).is_some_and(|owner| {
                    owner.binding != binding
                        || owner.request_id != grant_id
                        || owner.phase != Phase::Active
                })
            {
                return Err("LOCAL_AUTHORITY_CHANGED");
            }
            let deadline = record_deadline(record).ok_or("LOCAL_ADMISSION_EXPIRED")?;
            if now >= deadline {
                return Err("LOCAL_ADMISSION_EXPIRED");
            }
            deadline
        };
        Ok(RuntimeAdmission {
            _permit: permit,
            service: self.clone(),
            profile,
            binding,
            grant_id,
            required_scopes,
            deadline,
        })
    }
}

impl RuntimeAdmission {
    pub(crate) fn authorization_ended(&self) -> bool {
        let now = Instant::now();
        if now >= self.deadline {
            return true;
        }
        let state = match self.service.state.try_lock() {
            Ok(state) => state,
            // Never block the process supervisor behind unrelated local I/O.
            // It will observe the next short authorization transition on its
            // next tick; the immutable monotonic ceiling always remains live.
            Err(TryLockError::WouldBlock) => return false,
            Err(TryLockError::Poisoned(_)) => return true,
        };
        let Some(record) = state.records.get(&self.binding) else {
            return true;
        };
        record.profile != self.profile
            || record.binding != self.binding
            || record.view.id != self.grant_id
            || record.view.status != "active"
            || !self.required_scopes.is_subset(&record.view.scopes)
            || record_deadline(record).is_none_or(|deadline| now >= deadline)
            || state.owners.get(&self.profile).is_some_and(|owner| {
                owner.binding != self.binding
                    || owner.request_id != self.grant_id
                    || owner.phase != Phase::Active
            })
    }
}

fn record_deadline(record: &Record) -> Option<Instant> {
    let absolute = record.since.checked_add(Duration::from_secs(record.lease_seconds))?;
    if record.idle_seconds == 0 {
        Some(absolute)
    } else {
        let idle = record.touched.checked_add(Duration::from_secs(record.idle_seconds))?;
        Some(absolute.min(idle))
    }
}

impl fmt::Debug for RuntimeAdmission {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("RuntimeAdmission(<committed-local-authority>)")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn admitted() -> (tempfile::TempDir, RemoteRequest, Arc<crate::runtime::WorkspaceExecutionGate>, RuntimeAdmission) {
        let root = tempfile::tempdir().unwrap();
        let service = Arc::new(ChatAuthorizer::default());
        let profile = uuid::Uuid::new_v4().to_string();
        service.attach_storage(&profile, root.path(), &root.path().join("harness")).unwrap();
        let token = crate::auth::principal::issue(
            "https://mcp.example", "https://mcp.example", "runtime-fixture-key", "client", 3600,
        ).unwrap();
        let principal = crate::auth::principal::verify(
            &token, "https://mcp.example", "https://mcp.example", "runtime-fixture-key", "client",
        ).unwrap();
        let mut request = RemoteRequest::verified(
            &profile, "workspace", principal, &json!({"openai/session":"runtime-test"}), "runtime-fixture-key",
        );
        request.service = service.clone();
        let response = service.request(&request, &json!({"scopes":["exec.run", "files.read", "files.write"]}));
        assert_eq!(response["ok"], true, "{response}");
        service.decide(&profile, response["authorization"]["id"].as_str().unwrap(), true,
                       &["exec.run".into(), "files.read".into(), "files.write".into()]).unwrap();
        let gate = crate::runtime::WorkspaceExecutionGate::shared();
        let ticket = service.issue_local_admission_ticket(&request, &["exec.run", "files.read", "files.write"], &gate).unwrap();
        let admission = service.commit_runtime_admission(&request, &gate, ticket).unwrap();
        (root, request, gate, admission)
    }

    #[test]
    fn runtime_revoke_is_observed_without_extending_the_lease() {
        let (_root, request, gate, admission) = admitted();
        let before = request.service.state.lock().unwrap().records[request.identity().unwrap()].touched;
        assert!(!admission.authorization_ended());
        assert_eq!(request.service.state.lock().unwrap().records[request.identity().unwrap()].touched, before);
        request.service.revoke(&request.profile, None);
        assert!(admission.authorization_ended());
        assert_eq!(gate.snapshot().in_flight, 1, "revocation is not proof of process cleanup");
        drop(admission);
        assert_eq!(gate.snapshot().in_flight, 0);
    }

    #[test]
    fn pause_and_unrelated_revision_do_not_revoke_committed_work() {
        let (_root, request, gate, admission) = admitted();
        gate.pause().unwrap();
        request.service.revoke("unrelated-profile", None);
        assert!(!admission.authorization_ended());
        drop(admission);
        assert_eq!(gate.snapshot().in_flight, 0);
    }

    #[test]
    fn monotonic_expiry_is_observed_without_reconciliation() {
        let (_root, request, _gate, admission) = admitted();
        {
            let mut state = request.service.state.lock().unwrap();
            let record = state.records.get_mut(request.identity().unwrap()).unwrap();
            record.since = Instant::now() - Duration::from_secs(record.lease_seconds + 1);
            assert_eq!(record.view.status, "active");
        }
        assert!(admission.authorization_ended());
    }

    #[test]
    fn observer_does_not_wait_for_authorization_mutex_or_disclose_identity() {
        let (_root, request, _gate, admission) = admitted();
        let state = request.service.state.lock().unwrap();
        assert!(!admission.authorization_ended());
        assert!(!format!("{admission:?}").contains(&request.profile));
        assert!(!format!("{admission:?}").contains(request.identity().unwrap()));
        drop(state);
        drop(admission);
    }
}
