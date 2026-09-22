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
            let code = args
                .next()
                .and_then(|v| v.parse::<u8>().ok())
                .unwrap_or(7);
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
            let mut child = Command::new(exe)
                .arg("sleep")
                .arg("60000")
                .spawn()
                .unwrap();
            println!("grandchild_pid={}", child.id());
            std::io::stdout().flush().unwrap();
            thread::sleep(Duration::from_secs(60));
            let _ = child.kill();
            let _ = child.wait();
            ExitCode::SUCCESS
        }
        _ => ExitCode::from(2),
    }
}
