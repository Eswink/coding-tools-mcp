use super::{ExecError, ExecErrorKind, ExecSpec, MAX_TOKEN_BYTES};

impl ExecSpec {
    /// Host-only argv[0] preservation for a pinned executable launch path.
    /// This changes no executable selection, policy or sandbox. No serialized
    /// tool argument exposes it; the trusted caller binds it in local approval.
    #[cfg(unix)]
    pub fn with_argv0(mut self, argv0: String) -> Result<Self, ExecError> {
        if argv0.is_empty() || argv0.len() > MAX_TOKEN_BYTES || argv0.chars().any(char::is_control)
        {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "invalid host argv0",
            ));
        }
        self.argv0 = Some(argv0);
        Ok(self)
    }
}

#[cfg(all(test, unix))]
mod argv0_tests {
    use super::*;
    use crate::ProcessManager;
    #[tokio::test]
    async fn host_argv0_is_preserved_without_changing_program_selection() {
        let spec = ExecSpec::new(
            vec!["/bin/sh".into(), "-c".into(), "printf '%s' \"$0\"".into()],
            std::env::temp_dir(),
        )
        .unwrap()
        .with_argv0("native-approved-shell".into())
        .unwrap();
        assert_eq!(spec.argv()[0], "/bin/sh");
        let result = ProcessManager::new(1).unwrap().run(spec).await.unwrap();
        assert!(result.command_ok());
        assert_eq!(result.stdout, b"native-approved-shell");
    }
    #[test]
    fn host_argv0_is_bounded_and_not_an_executable_override() {
        for value in [
            String::new(),
            "x".repeat(MAX_TOKEN_BYTES + 1),
            "bad\0value".into(),
        ] {
            assert!(ExecSpec::new(vec!["/bin/sh".into()], std::env::temp_dir())
                .unwrap()
                .with_argv0(value)
                .is_err());
        }
    }
}
