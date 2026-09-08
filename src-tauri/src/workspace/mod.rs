#[path = "固定入口.rs"]
pub mod endpoint;
pub mod legacy_import;
mod model;
pub mod resources;

pub use model::{ActionsConfig, AuthConfig, RuntimeConfig, RuntimeStatusDto, WorkspaceProfile};
