//! Fixed synthetic kernel probes. Not a public tool or arbitrary-command runner.
#[cfg(windows)]
fn main() {
    use std::{
        fs,
        net::{SocketAddr, TcpStream},
        time::Duration,
    };
    use windows::Win32::Foundation::CloseHandle;
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
    let endpoint: SocketAddr = args[4].to_str().unwrap().parse().unwrap();
    let mut token = windows::Win32::Foundation::HANDLE::default();
    let mut is_container = 0u32;
    let mut returned = 0u32;
    unsafe {
        OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token).unwrap();
        GetTokenInformation(
            token,
            TokenIsAppContainer,
            Some((&mut is_container as *mut u32).cast()),
            4,
            &mut returned,
        )
        .unwrap();
        CloseHandle(token).unwrap();
    }
    let token_ok = (is_container != 0) == sandbox;
    let inside = root.join("inside-result.txt");
    let inside_ok = fs::write(&inside, b"inside-owned-fixture").is_ok()
        && fs::read(&inside)
            .map(|b| b == b"inside-owned-fixture")
            .unwrap_or(false);
    let outside_read = fs::read(outside.join("canary.txt")).is_ok();
    let outside_write = fs::write(outside.join("probe-write.txt"), b"synthetic").is_ok();
    let network = TcpStream::connect_timeout(&endpoint, Duration::from_secs(2)).is_ok();
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
