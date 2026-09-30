//! Required kernel boundary descriptors, never authorization or enforcement proof.
//! A declared backend cannot be substituted for a successfully constructed host policy.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequiredIsolationBackend {
    LinuxLandlockSeccomp,
    WindowsLpac,
    Unsupported,
}

/// A requirement descriptor only. It deliberately contains no workspace, grant,
/// capability override, or success/enforced field and cannot launch a process.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct IsolationRequirements {
    backend: RequiredIsolationBackend,
}

impl IsolationRequirements {
    pub const fn for_current_platform() -> Self {
        let backend = if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            RequiredIsolationBackend::LinuxLandlockSeccomp
        } else if cfg!(all(target_os = "windows", target_arch = "x86_64")) {
            RequiredIsolationBackend::WindowsLpac
        } else {
            RequiredIsolationBackend::Unsupported
        };
        Self { backend }
    }

    pub const fn backend(self) -> RequiredIsolationBackend {
        self.backend
    }

    pub const fn network_denied(self) -> bool {
        true
    }

    pub const fn workspace_write_boundary_required(self) -> bool {
        true
    }

    /// Windows production preparation and integration are not implemented by
    /// the native fixture. Callers must not use that fixture as a fallback.
    pub const fn windows_production_integration_available(self) -> bool {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requirement_descriptor_never_asserts_windows_execution_support() {
        for backend in [
            RequiredIsolationBackend::LinuxLandlockSeccomp,
            RequiredIsolationBackend::WindowsLpac,
            RequiredIsolationBackend::Unsupported,
        ] {
            let requirements = IsolationRequirements { backend };
            assert!(requirements.network_denied());
            assert!(requirements.workspace_write_boundary_required());
            assert!(!requirements.windows_production_integration_available());
            assert_eq!(requirements.backend(), backend);
        }
    }
}
