//! Fixed synthetic kernel probes. Not a public tool or arbitrary-command runner.
#[cfg(windows)]
fn main() {
    use std::{
        fs,
        net::{SocketAddr, TcpStream},
        time::Duration,
    };
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::Networking::WinSock::{WSACleanup, WSAStartup, WSADATA};
    use windows::Win32::Security::{GetTokenInformation, TokenIsAppContainer, TOKEN_QUERY};
    use windows::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 5 {
        std::process::exit(90);
    }
    let sandbox = args[1] == "sandbox";
    if !sandbox && args[1] != "control" {
        std::process::exit(91);
    }
    let root = std::path::Path::new(&args[2]);
    let outside = std::path::Path::new(&args[3]);
    let endpoint: SocketAddr = match args[4].to_str().and_then(|s| s.parse().ok()) {
        Some(endpoint) => endpoint,
        None => std::process::exit(96),
    };
    let mut token = windows::Win32::Foundation::HANDLE::default();
    let mut is_container = 0u32;
    let mut returned = 0u32;
    unsafe {
        if let Err(error) = OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) {
            std::process::exit(1000 + (error.code().0 as u32 & 0xffff) as i32);
        }
        if let Err(error) = GetTokenInformation(
            token,
            TokenIsAppContainer,
            Some((&mut is_container as *mut u32).cast()),
            4,
            &mut returned,
        ) {
            std::process::exit(2000 + (error.code().0 as u32 & 0xffff) as i32);
        }
        if let Err(error) = CloseHandle(token) {
            std::process::exit(3000 + (error.code().0 as u32 & 0xffff) as i32);
        }
        if returned != 4 {
            std::process::exit(97);
        }
    }
    let token_ok = (is_container != 0) == sandbox;
    let inside = root.join("inside-result.txt");
    let inside_ok = fs::write(&inside, b"inside-owned-fixture").is_ok()
        && fs::read(&inside)
            .map(|b| b == b"inside-owned-fixture")
            .unwrap_or(false);
    let outside_read = fs::read(outside.join("canary.txt")).is_ok();
    let outside_write = fs::write(outside.join("probe-write.txt"), b"synthetic").is_ok();
    let preliminary = format!(
        "token={}\ninside={}\noutside_read={}\noutside_write={}\n",
        token_ok,
        inside_ok,
        outside_read != sandbox,
        outside_write != sandbox
    );
    if fs::write(root.join("pre-network.txt"), preliminary).is_err() {
        std::process::exit(98);
    }
    // Observe the WinSock initialization error directly instead of treating a
    // Rust std initialization panic as network denial. No capability is added.
    unsafe {
        let mut data = WSADATA::default();
        let result = WSAStartup(0x0202, &mut data);
        if result != 0 {
            std::process::exit(5000 + result);
        }
        if WSACleanup() != 0 {
            std::process::exit(4999);
        }
    }
    // A runtime initialization panic is setup failure, never a denied socket.
    let network = match std::panic::catch_unwind(|| {
        TcpStream::connect_timeout(&endpoint, Duration::from_secs(2)).is_ok()
    }) {
        Ok(connected) => connected,
        Err(_) => std::process::exit(4000),
    };
    let expected_access = !sandbox;
    let results = [
        token_ok,
        inside_ok,
        outside_read == expected_access,
        outside_write == expected_access,
        network == expected_access,
    ];
    // Fixed booleans only; no paths, environment, credentials or output payload.
    let receipt = format!(
        "token={}\ninside={}\noutside_read={}\noutside_write={}\nnetwork={}\n",
        results[0], results[1], results[2], results[3], results[4]
    );
    if fs::write(root.join("receipt.txt"), receipt).is_err() {
        std::process::exit(92);
    }
    if results.iter().all(|v| *v) {
        std::process::exit(0);
    }
    std::process::exit(20);
}
#[cfg(not(windows))]
fn main() {
    eprintln!("Windows native fixture unavailable on this platform");
    std::process::exit(78);
}
