//! Isolate process-global production-style stores without disabling parallel tests.
//! A single selected case still executes its real HTTP and concurrent-write assertions.
use std::io::Read;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const CHILD_CASE: &str = "MCP_TEST_ISOLATED_CONFIGURATION_CASE";

pub(super) fn run_isolated(case: &str) -> bool {
    let test = format!("commands::configuration::tests::{case}");
    if std::env::var(CHILD_CASE).as_deref() == Ok(test.as_str()) {
        return false;
    }
    let logs = tempfile::tempdir().expect("isolated test log directory");
    let path = logs.path().join("child.log");
    let stdout = std::fs::File::create(&path).expect("child log");
    let stderr = stdout.try_clone().expect("child stderr");
    let mut child = Command::new(std::env::current_exe().expect("test executable"))
        .args(["--exact", &test, "--nocapture"])
        .env(CHILD_CASE, &test)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn().expect("isolated test child");
    let deadline = Instant::now() + Duration::from_secs(90);
    let status = loop {
        if let Some(status) = child.try_wait().expect("poll isolated test") { break Some(status); }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            break None;
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let mut output = String::new();
    std::fs::File::open(path).expect("read child log")
        .take(64 * 1024).read_to_string(&mut output).expect("bounded child output");
    assert!(status.is_some_and(|s| s.success()), "{test}: {status:?}\n{output}");
    // A misspelled --exact filter runs zero tests and exits successfully. Never accept that.
    assert!(output.contains("running 1 test") && output.contains("1 passed; 0 failed"),
        "isolated case did not execute exactly one passing test: {test}\n{output}");
    true
}
