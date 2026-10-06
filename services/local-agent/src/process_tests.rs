use super::*;

#[test]
fn spec_bounds_fail_before_spawn() {
    let cwd = std::env::current_dir().unwrap();
    assert!(ExecSpec::new(Vec::new(), &cwd).is_err());
    assert!(ExecSpec::new(vec!["relative-program".into()], &cwd).is_err());

    let exe = std::env::current_exe().unwrap().display().to_string();
    assert!(ExecSpec::new(vec![exe.clone(), "x".repeat(MAX_TOKEN_BYTES + 1)], &cwd).is_err());
    assert!(ExecSpec::new(vec![exe.clone()], &cwd)
        .unwrap()
        .with_stdin(vec![0; MAX_STDIN_BYTES + 1])
        .is_err());
    assert!(ExecSpec::new(vec![exe.clone()], &cwd)
        .unwrap()
        .with_timeout(Duration::ZERO)
        .is_err());
    assert!(ExecSpec::new(vec![exe], &cwd)
        .unwrap()
        .with_stream_limit(MAX_STREAM_BYTES + 1)
        .is_err());
}

#[tokio::test]
async fn stream_read_error_is_incomplete_not_success() {
    use std::{
        pin::Pin,
        task::{Context, Poll},
    };
    use tokio::io::ReadBuf;

    struct ErrorAfterData {
        delivered: bool,
    }

    impl AsyncRead for ErrorAfterData {
        fn poll_read(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
            buf: &mut ReadBuf<'_>,
        ) -> Poll<std::io::Result<()>> {
            let this = self.get_mut();
            if !this.delivered {
                this.delivered = true;
                buf.put_slice(b"partial");
                Poll::Ready(Ok(()))
            } else {
                Poll::Ready(Err(std::io::Error::other("fixture read failure")))
            }
        }
    }

    let state = Arc::new(Mutex::new(StreamState::default()));
    let (overflow, _rx) = mpsc::unbounded_channel();
    let complete = read_bounded(
        ErrorAfterData { delivered: false },
        state.clone(),
        1024,
        overflow,
    )
    .await;
    assert!(!complete);
    let captured = take_stream(&state);
    assert_eq!(captured.retained, b"partial");
    assert!(!captured.truncated);
}

#[test]
fn debug_redacts_command_environment_and_working_directory() {
    let cwd = std::env::current_dir().unwrap();
    let exe = std::env::current_exe().unwrap().display().to_string();
    let spec = ExecSpec::new(vec![exe, "secret-argument".into()], &cwd)
        .unwrap()
        .with_env("SECRET_KEY", "secret-value")
        .unwrap();
    let rendered = format!("{spec:?}");
    assert!(!rendered.contains("secret-argument"));
    assert!(!rendered.contains("secret-value"));
    assert!(!rendered.contains(&cwd.display().to_string()));
}
