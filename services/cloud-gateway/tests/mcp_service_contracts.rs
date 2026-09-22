use std::process::Command;

fn exe() -> &'static str {
    env!("CARGO_BIN_EXE_coding-tools-mcp-gateway")
}

#[test]
fn mcp_gateway_help_and_version_need_no_credentials() {
    for arg in ["--help", "--version"] {
        let r = Command::new(exe()).arg(arg).output().unwrap();
        assert!(r.status.success());
        assert!(r.stderr.is_empty());
    }
}
#[test]
fn mcp_gateway_unknown_arguments_are_not_echoed() {
    let r = Command::new(exe())
        .arg("canary-secret-in-arg")
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(!String::from_utf8_lossy(&r.stderr).contains("canary"));
}
