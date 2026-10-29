#![cfg(all(target_os = "linux", target_arch = "x86_64"))]
use coding_tools_local_agent::{ExecSpec, LinuxSandbox, ProcessManager};
use std::{
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let name = format!(
            "ctm-read-only-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let path = std::env::temp_dir().join(name);
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
#[tokio::test]
async fn read_only_policy_denies_workspace_mutation_and_external_access() {
    let fixture = Fixture::new();
    let root = fixture.0.join("workspace");
    std::fs::create_dir(&root).unwrap();
    std::fs::write(root.join("input.txt"), "seed").unwrap();
    std::fs::write(fixture.0.join("outside.txt"), "outside").unwrap();
    let code = "import pathlib,socket; p=pathlib.Path('.'); assert (p/'input.txt').read_text()=='seed'; checks=[lambda:(p/'output.txt').write_text('bad'),lambda:(p/'input.txt').rename(p/'renamed.txt'),lambda:(p/'..'/'outside.txt').read_text(),lambda:socket.socket()]; denied=0; exec(\"for check in checks:\\n try: check()\\n except PermissionError: denied+=1\"); assert denied==4; print('READ_ONLY_OK')";
    let policy = LinuxSandbox::new(&root).unwrap().read_only();
    let spec = ExecSpec::new(
        vec!["/usr/bin/python3".into(), "-c".into(), code.into()],
        &root,
    )
    .unwrap()
    .with_sandbox(policy);
    let outcome = ProcessManager::default().run(spec).await.unwrap();
    assert!(outcome.command_ok(), "{outcome:?}");
    assert!(String::from_utf8_lossy(&outcome.stdout).contains("READ_ONLY_OK"));
    assert!(!root.join("output.txt").exists());
    assert_eq!(
        std::fs::read_to_string(root.join("input.txt")).unwrap(),
        "seed"
    );
}
