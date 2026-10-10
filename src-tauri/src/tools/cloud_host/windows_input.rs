//! Register actual independent input root; neither snapshot identity nor grant.
use super::NativeToolHost;
use crate::tools::windows_vm::input::WindowsInputAuthority;
use std::sync::Arc;
pub(super) fn pin_input_authority(host: &NativeToolHost)
    -> Result<Arc<WindowsInputAuthority>, &'static str> {
    WindowsInputAuthority::pin(host.id, &host.profile, host.context.workspace.root()).map(Arc::new)
}
