//! No arbitrary commands: fixed offline cases, clean inherited fixture environment,
//! private stdio files, bounded waits. The native network gate runs afterwards.
use std::os::windows::process::CommandExt;
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

fn command(exe: &Path, args: &[&str], workspace: &Path, code: &Path) -> serde_json::Value {
    let stdout = fs::File::create(workspace.join("runtime-stdout.txt")).unwrap();
    let stderr = fs::File::create(workspace.join("runtime-stderr.txt")).unwrap();
    let mut cmd = Command::new(exe);
    // cmd.exe has shell parsing rather than CommandLineToArgvW semantics.
    // Only the fixed /d /s /c or /d /q /c strings below reach raw_arg.
    if exe.file_name().is_some_and(|name| name == "cmd.exe") {
        assert_eq!(args.len(), 4);
        cmd.args(&args[..3]).raw_arg(args[3]);
    } else {
        cmd.args(args);
    }
    cmd.current_dir(workspace)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    // Only this synthetic sandbox's executable/data directories plus the already
    // allowlisted OS PATH. Never inherit runner credentials, user config or HOME.
    let path = format!(
        "{};{}",
        code.join("runtime").display(),
        std::env::var("Path").unwrap_or_default()
    );
    cmd.env("PATH", path)
        .env("HOME", workspace)
        .env("USERPROFILE", workspace)
        .env("APPDATA", workspace)
        .env("LOCALAPPDATA", workspace)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONLEGACYWINDOWSSTDIO", "0")
        .env("npm_config_cache", workspace.join("npm-cache"))
        .env("npm_config_userconfig", workspace.join("empty.npmrc"))
        .env(
            "npm_config_globalconfig",
            workspace.join("empty-global.npmrc"),
        )
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", workspace.join("empty.gitconfig"))
        .env("GIT_TERMINAL_PROMPT", "0")
        .env("POWERSHELL_TELEMETRY_OPTOUT", "1")
        .env("POWERSHELL_UPDATECHECK", "Off");
    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(error) => {
            return serde_json::json!({"started":false,"spawn_error":error.raw_os_error(),"exit":null,"timeout":false})
        }
    };
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                return serde_json::json!({"started":true,"exit":status.code(),"exit_unsigned":status.code().map(|v| v as u32),"exit_hex":status.code().map(|v| format!("{:08X}", v as u32)),"timeout":false})
            }
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
            Ok(None) => {
                let killed = child.kill().is_ok();
                let reaped = child.wait().is_ok();
                return serde_json::json!({"started":true,"exit":null,"timeout":true,"child_killed":killed,"child_reaped":reaped});
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return serde_json::json!({"started":true,"wait_error":error.raw_os_error(),"exit":null,"timeout":false});
            }
        }
    }
}

pub fn observe(workspace: &Path, outside: &Path) {
    let exe = std::env::current_exe().unwrap();
    let code = exe.parent().unwrap();
    let case = fs::read_to_string(code.join("case.txt")).unwrap();
    let runtime = code.join("runtime");
    // raw cmd tails only interpolate this generated private path. Refuse shell
    // expansion syntax instead of trying to escape arbitrary caller input.
    if runtime.to_string_lossy().chars().any(|c| {
        matches!(
            c,
            '"' | '%' | '!' | '\r' | '\n' | '&' | '|' | '<' | '>' | '^'
        )
    }) {
        fs::write(
            workspace.join("runtime-result.json"),
            "{\"classification\":\"unsafe_fixture_path\",\"passed\":false}",
        )
        .unwrap();
        return;
    }
    fs::write(workspace.join("seed.txt"), "runtime-ok\n").unwrap();
    fs::write(
        workspace.join("package.json"),
        "{\"name\":\"lpac-offline-fixture\",\"version\":\"1.0.0\"}\n",
    )
    .unwrap();
    for name in ["empty.npmrc", "empty-global.npmrc", "empty.gitconfig"] {
        fs::write(workspace.join(name), "").unwrap();
    }
    let mutation = workspace.join("mutation.txt");
    let python = "from pathlib import Path; p=Path('mutation.txt'); p.write_text('runtime-ok'); print(p.read_text())";
    let node = "const fs=require('node:fs');fs.writeFileSync('mutation.txt','runtime-ok');console.log(fs.readFileSync('mutation.txt','utf8'))";
    let powershell = "[IO.File]::WriteAllText('mutation.txt','runtime-ok'); [Console]::WriteLine([IO.File]::ReadAllText('mutation.txt'))";
    let cmd_exe = code.join("cmd.exe");
    let (program, args, expected, mutation_kind): (PathBuf, Vec<&str>, &str, &str) = match case.trim() {
        "python-budget" => (runtime.join("python.exe"), vec!["-c", "print('budget')"], "budget", "none"),
        "python-workspace" => (runtime.join("python.exe"), vec!["-I", "-c", python], "runtime-ok", "file"),
        "node-workspace" => (runtime.join("node.exe"), vec!["-e", node], "runtime-ok", "file"),
        // Exercise the actual npm.cmd shim, including its node child. No package
        // download, install, lifecycle script or executable lookup outside copies.
        "npm-cmd" => (cmd_exe.clone(), vec!["/d", "/s", "/c", "runtime\\npm.cmd --offline --ignore-scripts --no-audit --no-fund pkg set description=runtime-ok && runtime\\npm.cmd --offline --ignore-scripts --no-audit --no-fund pkg get description"], "\"runtime-ok\"", "package"),
        "git-local" => (cmd_exe.clone(), vec!["/d", "/s", "/c", "runtime\\cmd\\git.exe init --quiet repository && runtime\\cmd\\git.exe -C repository hash-object -w ..\\seed.txt"], "f7366408c17cc3dd009ff89e36672da972918774", "git"),
        "cmd-workspace" => (cmd_exe.clone(), vec!["/d", "/q", "/c", "echo runtime-ok>mutation.txt & type mutation.txt"], "runtime-ok", "file-trim"),
        "powershell-workspace" => (runtime.join("powershell.exe"), vec!["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", powershell], "runtime-ok", "file"),
        "pwsh-workspace" => (runtime.join("pwsh.exe"), vec!["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", powershell], "runtime-ok", "file"),
        _ => {
            fs::write(workspace.join("runtime-result.json"), "{\"classification\":\"invalid_fixed_case\",\"passed\":false}").unwrap();
            return;
        }
    };
    // cmd uses fixed quoted absolute paths to the private copied runtime.
    let mut command_args = args.iter().map(|s| s.to_string()).collect::<Vec<_>>();
    if matches!(case.trim(), "npm-cmd" | "git-local") {
        let prefix = format!("\"{}\\", runtime.display());
        command_args[3] = command_args[3]
            .replace("runtime\\npm.cmd", &format!("{}npm.cmd\"", prefix))
            .replace(
                "runtime\\cmd\\git.exe",
                &format!("{}cmd\\git.exe\"", prefix),
            );
        command_args[3] = format!("\"{}\"", command_args[3]);
    }
    let refs = command_args.iter().map(String::as_str).collect::<Vec<_>>();
    let process = command(&program, &refs, workspace, code);
    let output = fs::read_to_string(workspace.join("runtime-stdout.txt")).unwrap_or_default();
    let output_ok = output.trim() == expected;
    let mutation_ok = match mutation_kind {
        "none" => true,
        "file" => fs::read_to_string(&mutation).is_ok_and(|s| s == "runtime-ok"),
        "file-trim" => fs::read_to_string(&mutation).is_ok_and(|s| s.trim() == "runtime-ok"),
        "package" => fs::read(workspace.join("package.json"))
            .ok()
            .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
            .is_some_and(|v| v["description"] == "runtime-ok"),
        "git" if output_ok => {
            let hash = output.trim();
            workspace
                .join("repository/.git/objects")
                .join(&hash[..2])
                .join(&hash[2..])
                .is_file()
        }
        _ => false,
    };
    let exit_ok = process["started"] == true && process["exit"] == 0 && process["timeout"] == false;
    let process_classification = if process["started"] == false {
        "spawn_failed"
    } else if process["timeout"] == true {
        "deadline_exceeded"
    } else if !exit_ok {
        "nonzero_exit_or_wait_failure"
    } else if !output_ok || !mutation_ok {
        "positive_operation_failed"
    } else {
        "positive_operation_completed"
    };
    // Filesystem canaries are rechecked after the actual runtime. These remain
    // independent of the WinSock stage and never assert connectivity denial.
    let outside_read_denied = fs::read(outside.join("canary.txt")).is_err();
    let outside_write_denied =
        fs::write(outside.join("probe-write.txt"), "runtime-escape").is_err();
    let result = serde_json::json!({
        "case":case.trim(),"process":process,"process_classification":process_classification,"output_ok":output_ok,
        "executable":program,"argv":command_args,"expected_output":expected,
        "mutation_required":mutation_kind != "none","mutation_ok":mutation_ok,
        "parent_fixture_outside_read_denied":outside_read_denied,"parent_fixture_outside_write_denied":outside_write_denied,
        "child_containment_independently_measured":false,"deadline_seconds":30,
        "passed":exit_ok && output_ok && mutation_ok && outside_read_denied && outside_write_denied,
        "classification":"offline_runtime_only","network_denial_proven":false
    });
    fs::write(
        workspace.join("runtime-result.json"),
        serde_json::to_vec_pretty(&result).unwrap(),
    )
    .unwrap();
}
