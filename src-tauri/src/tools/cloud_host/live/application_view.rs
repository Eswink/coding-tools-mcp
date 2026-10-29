//! Read-only native UI view. A status string is never execution authority.
use super::*;
impl NativeLiveHost {
    pub(crate) fn application_phase(&self) -> &'static str {
        match self
            .tools
            .context
            .root_work
            .as_ref()
            .map(|root| root.native_state())
        {
            Ok("available") => {}
            Ok("paused") => return "paused",
            _ => return "recovery",
        }
        let root = self.tools.authorizer.snapshot(&self.tools.profile);
        if root["recovery"]["required"] != false {
            return "recovery";
        }
        if self.work.status().unconfirmed {
            return "recovery";
        }
        if self.work.status().sealed {
            return "draining";
        }
        if self.tools.context.execution_gate.snapshot().availability
            != crate::runtime::ExecutionAvailability::Online
        {
            return "paused";
        }
        if self.tools.link.ensure_connected().is_err() {
            return "starting";
        }
        let Ok(journal) = self.projection.lock() else {
            return "recovery";
        };
        let mut pending = false;
        for conversation in journal.conversations() {
            if let Ok(authority) = self.tools.authority(conversation) {
                if authority.view.phase() == crate::auth::LocalAuthorityPhase::Active
                    && now().is_ok_and(|at| authority.view.deadline() > at)
                {
                    return "approved";
                }
            }
            if let Ok(request) = self.tools.request(conversation) {
                pending |=
                    self.tools.authorizer.status(&request)["authorization"]["status"] == "pending";
            }
        }
        if pending {
            "pending_approval"
        } else {
            "connected"
        }
    }
}

#[cfg(test)]
impl NativeLiveHost {
    pub(crate) fn application_test_context(&self) -> Arc<crate::tools::ToolContext> {
        self.tools.context.clone()
    }
    pub(crate) fn application_test_work(&self) -> coding_tools_cloud_agent::work::WorkDrain {
        self.work.clone()
    }
}
