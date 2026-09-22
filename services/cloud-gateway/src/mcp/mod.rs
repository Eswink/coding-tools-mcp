//! Production cloud MCP control-plane adapter. No local tool side effects are executed here.
mod http;
mod protocol;

pub use http::{routes, McpState};
pub use protocol::{catalog, MODERN, VERSIONS};
