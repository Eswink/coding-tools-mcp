pub(crate) mod chat_notifications;
pub use chat_notifications::{chat_authorization_inbox,refresh_session_control};
#[path = "异步任务v2.rs"]
mod exec_tasks;
pub use exec_tasks::control_exec_tasks;
#[path = "聊天授权v1.rs"]
mod chat_authorization;
pub use chat_authorization::chat_authorization_control;
mod app_info;
mod configuration;
mod frp_profiles;
mod health;
mod logs;
pub(crate) mod runtime;
mod secrets;
mod software;
mod tunnel;
pub(crate) mod ui_memory;
pub(crate) mod window_chrome;
mod workspace;

pub use app_info::{
    check_app_update, get_environment_diagnostics, get_startup_status, open_url, retry_startup,
};
pub(crate) use app_info::environment_diagnostics_snapshot;
pub use ui_memory::{get_webview_memory_sample, recreate_ui_webview};
pub use window_chrome::{hide_to_tray, quit_app, show_main_window};
pub use frp_profiles::{
    delete_frp_profile, get_app_settings, get_last_workspace_id, get_proxy, list_frp_profiles,
    save_frp_profile, set_last_workspace, set_proxy,
};
pub use health::run_health_checks;
pub use logs::read_workspace_logs;
pub use runtime::{
    get_actions_runtime_status, get_runtime_status, restart_actions_runtime, restart_runtime,
    start_actions_runtime, start_runtime, stop_actions_runtime, stop_runtime,
};
pub use secrets::{
    get_shared_secret, get_workspace_secret, regenerate_shared_secret,
    regenerate_workspace_secret, set_shared_secret, set_workspace_secret,
};
pub use software::{
    get_download_config, install_software, list_software, set_download_config,
    uninstall_software,
};
pub use tunnel::{get_frp_snippet, restart_tunnel, start_tunnel, stop_tunnel, test_tunnel};
pub use workspace::{
    create_workspace, delete_workspace, list_workspaces, open_workspace_directory, update_workspace,
};
