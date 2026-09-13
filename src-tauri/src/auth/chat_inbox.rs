//! A local inbox must be a single coherent snapshot, including an empty inbox.
use super::*;
use crate::auth::chat_events::{PendingEntry, PendingSnapshot};

impl ChatAuthorizer {
    pub(crate) fn pending_inbox(&self, profiles: &BTreeSet<String>) -> Result<PendingSnapshot, String> {
        // Executor reconciliation can block, so it stays outside the final state
        // mutex. Every row and the revision below are then read at one instant.
        for profile in profiles { self.reconcile(profile); }
        let state = self.state.lock().map_err(|_| "本机授权列表读取失败")?;
        let now = Instant::now();
        let mut entries = Vec::new();
        for record in state.records.values().filter(|r| profiles.contains(&r.profile)
            && r.view.status == "pending"
            && now.duration_since(r.since) < Duration::from_secs(PENDING)) {
            if entries.len() >= 256 {
                return Err("待审批列表达到容量上限，请逐个工作区处理".into());
            }
            entries.push(PendingEntry { profile: record.profile.clone(),
                exclusive: Self::policy(&state, &record.profile).exclusive, grant: record.view.clone() });
        }
        entries.sort_by(|a, b| (a.grant.created_at, &a.grant.id).cmp(&(b.grant.created_at, &b.grant.id)));
        // Do not derive this from per-workspace maxima: deleting the last
        // workspace must not reset the revision to zero and resurrect its UI.
        Ok(PendingSnapshot { revision: state.revision, entries })
    }
}
