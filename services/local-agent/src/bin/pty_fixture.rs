use std::{
    env,
    io::{IsTerminal, Read, Write},
    process::{Command, ExitCode},
    thread,
    time::Duration,
};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("echo") => {
            let value = args.next().unwrap_or_default();
            println!("terminal={}", std::io::stdout().is_terminal());
            println!("echo={value}");
            ExitCode::SUCCESS
        }
        Some("read-once") => {
            println!("terminal={}", std::io::stdin().is_terminal());
            std::io::stdout().flush().unwrap();
            let mut input = String::new();
            std::io::stdin().read_to_string(&mut input).unwrap();
            print!("input={input}");
            ExitCode::SUCCESS
        }
        Some("size-after") => {
            let ms = args.next().and_then(|v| v.parse().ok()).unwrap_or(250u64);
            thread::sleep(Duration::from_millis(ms));
            match terminal_size() {
                Some((columns, rows)) => {
                    println!("size={columns}x{rows}");
                    ExitCode::SUCCESS
                }
                None => ExitCode::from(3),
            }
        }
        Some("sleep") => {
            let ms = args.next().and_then(|v| v.parse().ok()).unwrap_or(60_000u64);
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
        _ => ExitCode::from(2),
    }
}

#[cfg(unix)]
fn terminal_size() -> Option<(u16, u16)> {
    let mut size = unsafe { std::mem::zeroed::<libc::winsize>() };
    if unsafe { libc::ioctl(libc::STDOUT_FILENO, libc::TIOCGWINSZ as _, &mut size) } == -1 {
        None
    } else {
        Some((size.ws_col, size.ws_row))
    }
}

#[cfg(windows)]
fn terminal_size() -> Option<(u16, u16)> {
    use windows::Win32::System::Console::{
        GetConsoleScreenBufferInfo, GetStdHandle, CONSOLE_SCREEN_BUFFER_INFO, STD_OUTPUT_HANDLE,
    };
    let handle = unsafe { GetStdHandle(STD_OUTPUT_HANDLE) }.ok()?;
    let mut info = CONSOLE_SCREEN_BUFFER_INFO::default();
    unsafe { GetConsoleScreenBufferInfo(handle, &mut info) }.ok()?;
    Some((
        (info.srWindow.Right - info.srWindow.Left + 1) as u16,
        (info.srWindow.Bottom - info.srWindow.Top + 1) as u16,
    ))
}
