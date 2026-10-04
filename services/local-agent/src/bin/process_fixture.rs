use std::{
    env,
    io::{Read, Write},
    process::{Command, ExitCode},
    thread,
    time::Duration,
};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("echo") => {
            let value = args.next().unwrap_or_default();
            println!("stdout:{value}");
            eprintln!("stderr:{value}");
            ExitCode::SUCCESS
        }
        Some("stdin") => {
            let mut bytes = Vec::new();
            std::io::stdin().read_to_end(&mut bytes).unwrap();
            print!("stdin:{}:", bytes.len());
            std::io::stdout().write_all(&bytes).unwrap();
            std::io::stdout().flush().unwrap();
            ExitCode::SUCCESS
        }
        Some("sleep") => {
            let ms = args
                .next()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(60_000);
            thread::sleep(Duration::from_millis(ms));
            ExitCode::SUCCESS
        }
        Some("flood") => {
            let bytes = args
                .next()
                .and_then(|v| v.parse::<usize>().ok())
                .unwrap_or(1024 * 1024);
            let chunk = vec![b'x'; 4096];
            let mut remaining = bytes;
            let mut out = std::io::stdout().lock();
            while remaining != 0 {
                let take = remaining.min(chunk.len());
                if out.write_all(&chunk[..take]).is_err() {
                    break;
                }
                remaining -= take;
            }
            let _ = out.flush();
            thread::sleep(Duration::from_secs(30));
            ExitCode::SUCCESS
        }
        Some("exit") => {
            let code = args.next().and_then(|v| v.parse::<u8>().ok()).unwrap_or(7);
            ExitCode::from(code)
        }
        Some("env") => {
            let visible = env::var("CTM_TEST_VISIBLE").unwrap_or_else(|_| "<missing>".into());
            let path = if env::var_os("PATH").is_some() {
                "present"
            } else {
                "missing"
            };
            println!("visible={visible};path={path}");
            ExitCode::SUCCESS
        }
        Some("spawn-grandchild") => {
            let exe = env::current_exe().unwrap();
            let mut child = Command::new(exe).arg("sleep").arg("60000").spawn().unwrap();
            println!("grandchild_pid={}", child.id());
            std::io::stdout().flush().unwrap();
            thread::sleep(Duration::from_secs(60));
            let _ = child.kill();
            let _ = child.wait();
            ExitCode::SUCCESS
        }
        Some("spawn-grandchild-exit") => {
            let exe = env::current_exe().unwrap();
            let child = Command::new(exe).arg("sleep").arg("60000").spawn().unwrap();
            println!("grandchild_pid={}", child.id());
            std::io::stdout().flush().unwrap();
            drop(child);
            ExitCode::SUCCESS
        }
        Some("spawn-private-descendant") => spawn_private_descendant(args),
        Some("private-descendant") => {
            println!("descendant_ready={}", std::process::id());
            std::io::stdout().flush().unwrap();
            // Neither parent exit nor stdin EOF ends this bounded lifetime.
            thread::sleep(Duration::from_secs(60));
            ExitCode::SUCCESS
        }
        _ => ExitCode::from(2),
    }
}

fn spawn_private_descendant(mut args: impl Iterator<Item = String>) -> ExitCode {
    use std::{
        io::{BufRead, BufReader},
        path::PathBuf,
        process::Stdio,
        sync::mpsc,
        time::Instant,
    };

    let (Some(ready), Some(release)) = (args.next(), args.next()) else {
        return ExitCode::from(2);
    };
    let release = PathBuf::from(release);
    let mut child = Command::new(env::current_exe().unwrap())
        .arg("private-descendant")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    // The descendant must not inherit either captured parent output pipe.
    let pipe = child.stdout.take().unwrap();
    let (sender, receiver) = mpsc::sync_channel(1);
    let reader = thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(pipe).read_line(&mut line).map(|_| line);
        let _ = sender.send(result);
    });
    let expected = format!("descendant_ready={}\n", child.id());
    let ready = match receiver.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(line)) if line == expected => std::fs::write(ready, &line).is_ok(),
        _ => false,
    };
    if !ready {
        let _ = child.kill();
        let _ = child.wait();
        let _ = reader.join();
        return ExitCode::from(3);
    }
    let _ = reader.join();
    println!("parent_ready");
    eprintln!("parent_ready");
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if release.is_file() {
            // The test already owns a process handle before allowing this exit.
            drop(child);
            return ExitCode::SUCCESS;
        }
        thread::sleep(Duration::from_millis(10));
    }
    let _ = child.kill();
    let _ = child.wait();
    ExitCode::from(4)
}
