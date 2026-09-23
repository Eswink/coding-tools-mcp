from pathlib import Path
import hashlib

path = Path("src-tauri/src/tools/异步命令v1.rs")
text = path.read_text(encoding="utf-8")

old_pre_spawn = '''    if ctx.exec_tasks.checkpoint(job).is_err() {\n        job.finish(Status::Failed, json!({"command_ok":false, "termination_reason":"storage_failed_before_spawn"}));\n        return;\n    }\n    // Keep ALL policy/baseline/operation logging in the one shared execution dispatcher.\n'''
new_pre_spawn = '''    // reserve() already persisted the queued no-replay record. Never put a durable\n    // filesystem checkpoint between the public Running state and actual child spawn.\n    // Keep ALL policy/baseline/operation logging in the one shared execution dispatcher.\n'''

old_post_spawn = '''    job.data.lock().expect("job state").session = Some(session.clone());\n    // Noninteractive tasks cannot supply stdin. Close it so read-to-EOF programs do not hang.\n    tauri::async_runtime::block_on(async {\n        session.stdin.lock().await.take();\n        session.mark_stdin_closed();\n    });\n    let mut checkpoint_at = std::time::Instant::now();\n'''
new_post_spawn = '''    job.data.lock().expect("job state").session = Some(session.clone());\n    // Once the child exists, persist Running + session ownership. If that durable\n    // checkpoint fails, stop the child and fail closed rather than leaving an\n    // untracked process behind or inviting an automatic retry.\n    if ctx.exec_tasks.checkpoint(job).is_err() {\n        session.mark_termination_reason("killed");\n        let waited = tauri::async_runtime::block_on(async {\n            tokio::time::timeout(Duration::from_secs(5), session.kill_and_wait())\n                .await\n                .is_ok()\n        });\n        tauri::async_runtime::block_on(async {\n            session.refresh_status().await;\n            session.wait_for_readers().await;\n        });\n        let process_may_be_running = !waited || !session.has_exited();\n        let mut failure = session.snapshot(0);\n        failure["command_ok"] = json!(false);\n        failure["output_complete"] = json!(session.readers_completed());\n        failure["process_may_be_running"] = json!(process_may_be_running);\n        failure["termination_reason"] = json!("storage_failed_after_spawn");\n        failure["error"] = json!({\n            "code": "EXEC_TASK_CHECKPOINT_FAILED",\n            "message": if process_may_be_running {\n                "Durable task checkpoint failed after child start and termination could not be confirmed; inspect local processes and do not retry automatically"\n            } else {\n                "Durable task checkpoint failed after child start; child was terminated and the command must not be retried automatically"\n            }\n        });\n        if let Some(operation) = result.get("operation_id") {\n            failure["operation_id"] = operation.clone();\n        }\n        job.finish(Status::Failed, failure);\n        ctx.sessions.remove(&session.session_id);\n        return;\n    }\n    // Noninteractive tasks cannot supply stdin. Close it so read-to-EOF programs do not hang.\n    tauri::async_runtime::block_on(async {\n        session.stdin.lock().await.take();\n        session.mark_stdin_closed();\n    });\n    let mut checkpoint_at = std::time::Instant::now();\n'''

if text.count(old_pre_spawn) != 1:
    raise SystemExit(f"expected exactly one pre-spawn checkpoint, found {text.count(old_pre_spawn)}")
text = text.replace(old_pre_spawn, new_pre_spawn, 1)
if text.count(old_post_spawn) != 1:
    raise SystemExit(f"expected exactly one post-spawn insertion point, found {text.count(old_post_spawn)}")
text = text.replace(old_post_spawn, new_post_spawn, 1)
path.write_text(text, encoding="utf-8", newline="\n")
print(hashlib.sha256(path.read_bytes()).hexdigest())
