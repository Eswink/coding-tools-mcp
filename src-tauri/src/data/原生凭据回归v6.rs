//! Opt-in native test. Unlike unit doubles, this must fail when the actual
//! OS credential service is unavailable. It only creates its own random entry.
use super::*;
use crate::data::key_store::{NativeKeyStore, SERVICE};

#[test]
fn native_keychain_cross_process_file_roundtrip() {
    const CHILD_PATH: &str = "CODING_TOOLS_NATIVE_TEST_CHILD_PATH";
    const PAYLOAD: &str = r#"{"token":"native-canary-v6","schema_version":1}"#;
    if let Ok(path) = std::env::var(CHILD_PATH) {
        Vault::new(&NativeKeyStore).write(Path::new(&path), PAYLOAD).expect("native child write");
        return;
    }
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("native-config.json");
    let id = codec::key_id_for_path(&path).unwrap();
    struct Cleanup(String);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            if let Ok(entry) = keyring::Entry::new(SERVICE, &self.0) {
                let _ = entry.delete_credential();
            }
        }
    }
    let _cleanup = Cleanup(id);
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "data::secure_file::native_tests::native_keychain_cross_process_file_roundtrip", "--nocapture"])
        .env(CHILD_PATH, &path).output().unwrap();
    assert!(output.status.success(), "native child failed: {}", String::from_utf8_lossy(&output.stderr));
    // Fresh provider in a different process proves this is not process-local memory.
    let (plaintext, encrypted) = Vault::new(&NativeKeyStore).read(&path).expect("native parent read");
    assert!(encrypted);
    assert_eq!(&*plaintext, PAYLOAD);
    assert!(!fs::read_to_string(&path).unwrap().contains("native-canary-v6"));
}


/// Exercise task journal admission/restoration with the production default key
/// provider in TWO fresh OS processes, not only an in-process MemoryKeys double.
#[test]
fn native_task_journal_cross_process_restore_and_missing_key() {
    use crate::tools::{call_tool, context::ToolContext, exec_tasks::ExecTaskStore};
    use crate::data::TaskArchive;
    use serde_json::{json, Value};
    use std::time::{Duration, Instant};
    const ROOT: &str = "CODING_TOOLS_NATIVE_TASK_TEST_ROOT";
    const ROLE: &str = "CODING_TOOLS_NATIVE_TASK_TEST_ROLE";
    const TEST: &str = "data::secure_file::native_tests::native_task_journal_cross_process_restore_and_missing_key";
    if let Some(dir) = std::env::var_os(ROOT) {
        let dir = PathBuf::from(dir);
        let journal = dir.join("journal");
        let role = std::env::var(ROLE).unwrap();
        let mut ctx = ToolContext::for_test(dir.join("workspace"), dir.join("harness")).unwrap();
        ctx.exec_tasks = ExecTaskStore::shared(journal.clone());
        let python = if cfg!(windows) { "python" } else { "python3" };
        let args = json!({"request_id":"native-finished", "timeout_ms":60000,
            "cmd":format!("{python} -c \"from pathlib import Path; Path('runs.txt').open('a').write('x'); print('任务密文恢复')\"")});
        if role == "write" {
            let accepted = call_tool(&ctx, "start_exec_task", &args);
            assert_eq!(accepted["ok"], true, "{accepted}");
            let id = accepted["job_id"].as_str().unwrap();
            let until = Instant::now() + Duration::from_secs(65);
            loop {
                let result = call_tool(&ctx, "get_exec_task", &json!({"job_id":id}));
                if result["terminal"] == true {
                    assert_eq!(result["status"], "succeeded", "{result}");
                    break;
                }
                assert!(Instant::now() < until, "{result}");
                std::thread::sleep(Duration::from_millis(25));
            }
            drop(ctx);
            // Completion is observable before the worker drops its final Arc.
            // Wait for the exclusive owner; never take over a live journal.
            let archive = loop {
                if let Ok(archive) = TaskArchive::open(&journal) { break archive; }
                assert!(Instant::now() < until, "journal owner was not released");
                std::thread::sleep(Duration::from_millis(25));
            };
            let mut pending = archive.load().unwrap().remove(0);
            let pending_id = uuid::Uuid::new_v4().to_string();
            pending["id"] = json!(pending_id);
            pending["request_id"] = json!("native-interrupted");
            pending["status"] = json!("running");
            pending["completed_at"] = Value::Null;
            pending["result"] = Value::Null;
            archive.save(&pending_id, || pending).unwrap();
        } else if role == "read" {
            let listed = call_tool(&ctx, "list_exec_tasks", &json!({}));
            assert_eq!(listed["ok"], true, "{listed}");
            let jobs = listed["jobs"].as_array().unwrap();
            assert_eq!(jobs.len(), 2);
            let done = jobs.iter().find(|j| j["request_id"] == "native-finished").unwrap();
            let detail = call_tool(&ctx, "get_exec_task", &json!({"job_id":done["job_id"]}));
            assert_eq!(detail["status"], "succeeded");
            assert!(detail["stdout"]["text"].as_str().unwrap().contains("任务密文恢复"));
            let retry = call_tool(&ctx, "start_exec_task", &args);
            assert_eq!(retry["deduplicated"], true);
            assert_eq!(retry["job_id"], done["job_id"]);
            let pending = jobs.iter().find(|j| j["request_id"] == "native-interrupted").unwrap();
            let detail = call_tool(&ctx, "get_exec_task", &json!({"job_id":pending["job_id"]}));
            assert_eq!(detail["status"], "interrupted");
            assert_eq!(detail["result"]["process_may_be_running"], true);
            let mut retry_args = args;
            retry_args["request_id"] = json!("native-interrupted");
            let retry = call_tool(&ctx, "start_exec_task", &retry_args);
            assert_eq!(retry["deduplicated"], true);
            assert_eq!(retry["status"], "interrupted");
        } else {
            assert_eq!(role, "missing-key");
            let listed = call_tool(&ctx, "list_exec_tasks", &json!({}));
            assert_eq!(listed["ok"], false, "missing OS key must never reset records");
            assert_eq!(call_tool(&ctx, "start_exec_task", &args)["ok"], false);
        }
        return;
    }
    let dir = tempfile::tempdir().unwrap();
    fs::create_dir(dir.path().join("workspace")).unwrap();
    fs::create_dir(dir.path().join("journal")).unwrap();
    let key_id = codec::key_id_for_path(&dir.path().join("journal/archive-key-v2")).unwrap();
    struct Cleanup(String);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            if let Ok(entry) = keyring::Entry::new(SERVICE, &self.0) { let _ = entry.delete_credential(); }
        }
    }
    let _cleanup = Cleanup(key_id.clone());
    let child = |role: &str| {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", TEST, "--nocapture"])
            .env(ROOT, dir.path()).env(ROLE, role).output().unwrap();
        assert!(output.status.success(), "native task {role} failed: {} {}",
            String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));
    };
    child("write");
    let records = fs::read_dir(dir.path().join("journal")).unwrap().map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|e| e == "json"))
        .map(|p| { let bytes = fs::read(&p).unwrap(); (p, bytes) }).collect::<Vec<_>>();
    assert_eq!(records.len(), 2);
    for (_, bytes) in &records {
        let raw = String::from_utf8_lossy(bytes);
        assert!(!raw.contains("native-finished") && !raw.contains("任务密文恢复"));
    }
    child("read");
    assert_eq!(fs::read_to_string(dir.path().join("workspace/runs.txt")).unwrap(), "x");
    keyring::Entry::new(SERVICE, &key_id).unwrap().delete_credential().unwrap();
    child("missing-key");
    for (path, bytes) in records { assert_eq!(fs::read(path).unwrap(), bytes); }
    assert_eq!(fs::read_to_string(dir.path().join("workspace/runs.txt")).unwrap(), "x");
}
