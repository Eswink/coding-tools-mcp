#[path = "进程树v2.rs"]
pub(crate) mod process_tree;
#[path = "聊天运行域v1.rs"]
pub(crate) mod chat_domain;
pub mod context;
pub mod dispatch;
pub mod exec;
#[path = "异步命令v1.rs"]
pub mod exec_tasks;
pub mod file;
pub mod git;
pub mod history;
mod image_tool;
pub mod patch;
pub mod platform_dispatch;
pub mod policy;
pub mod registry;
pub mod session;
pub mod workspace;

pub use context::{SharedToolContext, ToolContext};
/// 唯一工具执行入口；MCP 与 Actions 必须调用此函数，不得分叉执行实现。
/// 平台层只在执行完成后附加权威 Host 语义；策略和副作用仍全部位于 dispatch。
pub use platform_dispatch::call_tool;
pub use policy::{validate_actions_exposure, PolicySettings};
pub use registry::{
    exposed_tool_names, is_allowed_tool, list_tools, list_tools_for_profile, MUTATING_TOOLS,
};
pub use workspace::{wrap_mcp_tool_result, wrap_tool_result, Workspace};

#[cfg(all(test, windows))]
#[path = "Windows执行回归v8.rs"]
mod windows_regression_v8;
