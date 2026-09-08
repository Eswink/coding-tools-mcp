use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use crate::harness::Harness;
use crate::tools::policy::PolicySettings;
use crate::tools::session::SessionStore;
use crate::tools::workspace::{relative_display, Workspace};
use crate::workspace::AuthConfig;

pub struct ToolContext {
    pub workspace: Workspace,
    pub auth: AuthConfig,
    pub policy: PolicySettings,
    pub tool_profile: String,
    pub permission_mode: String,
    pub harness: Harness,
    default_cwd: Mutex<PathBuf>,
    pub sessions: Arc<SessionStore>,
    pub(crate) managed_task: bool,
    pub(crate) local_task_control: bool,
    pub exec_tasks: Arc<crate::tools::exec_tasks::ExecTaskStore>,
}

pub type SharedToolContext = Arc<ToolContext>;

impl ToolContext {
    pub fn new(workspace_path: PathBuf) -> Result<Self, String> {
        let workspace = Workspace::new(workspace_path).map_err(|e| e.message())?;
        let auth = AuthConfig {
            auth_type: "noauth".into(),
            ..AuthConfig::default()
        };
        Ok(Self::from_workspace(
            workspace,
            auth,
            PolicySettings::default(),
            "full".into(),
            "trusted".into(),
        ))
    }

    pub fn from_workspace(
        workspace: Workspace,
        auth: AuthConfig,
        policy: PolicySettings,
        tool_profile: String,
        permission_mode: String,
    ) -> Self {
        let harness_root = Harness::default_root().expect("无法初始化 Harness 数据目录");
        Self::from_workspace_with_harness_root(
            workspace,
            auth,
            policy,
            crate::tools::registry::normalize_tool_profile(&tool_profile).into(),
            permission_mode,
            harness_root,
        )
    }

    pub fn from_workspace_with_harness_root(
        workspace: Workspace,
        auth: AuthConfig,
        policy: PolicySettings,
        tool_profile: String,
        permission_mode: String,
        harness_root: PathBuf,
    ) -> Self {
        let root = workspace.root().to_path_buf();
        Self {
            workspace,
            auth,
            policy,
            tool_profile: crate::tools::registry::normalize_tool_profile(&tool_profile).into(),
            permission_mode,
            harness: Harness::new(root.clone(), harness_root).expect("无法初始化 Harness"),
            default_cwd: Mutex::new(root),
            sessions: Arc::new(SessionStore::new()),
            managed_task: false,
            local_task_control: false,
            exec_tasks: Arc::new(crate::tools::exec_tasks::ExecTaskStore::default()),
        }
    }

    pub fn for_test(workspace_path: PathBuf, harness_root: PathBuf) -> Result<Self, String> {
        let workspace = Workspace::new(workspace_path).map_err(|e| e.message())?;
        Ok(Self::from_workspace_with_harness_root(
            workspace,
            AuthConfig {
                auth_type: "noauth".into(),
                ..AuthConfig::default()
            },
            PolicySettings::default(),
            "full".into(),
            "trusted".into(),
            harness_root,
        ))
    }

    /// Snapshot policy/cwd at acceptance; share the existing service-owned task/session stores.
    pub(crate) fn background_snapshot(&self) -> Self {
        Self {
            workspace: self.workspace.clone(), auth: self.auth.clone(), policy: self.policy.clone(),
            tool_profile: self.tool_profile.clone(), permission_mode: self.permission_mode.clone(),
            harness: self.harness.clone(), default_cwd: Mutex::new(self.default_cwd_path()),
            sessions: self.sessions.clone(), exec_tasks: self.exec_tasks.clone(),
            managed_task: self.managed_task,
            local_task_control: self.local_task_control,
        }
    }

    /// Lazy encrypted storage. Merely starting the listener never creates secrets.
    pub(crate) fn enable_durable_tasks(&mut self, profile_id: &str, channel: &str) {
        use sha2::{Digest, Sha256};
        let identity = serde_json::to_vec(&(self.harness.workspace_id(), profile_id, channel)).expect("task namespace");
        let namespace = format!("{:x}", Sha256::digest(identity));
        let root = self.harness.store_root().join("exec-tasks-v2").join(namespace);
        self.exec_tasks = crate::tools::exec_tasks::ExecTaskStore::shared(root);
        self.exec_tasks.bind_profile(profile_id);
    }

    pub fn workspace_path(&self) -> String {
        self.workspace.root_display()
    }

    pub fn default_cwd_display(&self) -> String {
        let cwd = self.default_cwd.lock().expect("cwd lock");
        relative_display(self.workspace.root(), &cwd)
    }

    pub fn set_default_cwd(&self, path: PathBuf) {
        *self.default_cwd.lock().expect("cwd lock") = path;
    }

    pub fn default_cwd_path(&self) -> PathBuf {
        self.default_cwd.lock().expect("cwd lock").clone()
    }
}
