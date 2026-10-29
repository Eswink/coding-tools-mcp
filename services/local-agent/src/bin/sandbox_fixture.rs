//! Test-only executable: no CLI is mounted into the desktop or cloud Agent.
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
fn main() {
    use std::{
        io::{Read, Write},
        os::unix::fs::PermissionsExt,
        time::Duration,
    };
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("filesystem") => {
            let outside = std::path::Path::new(&args[2]);
            std::fs::write("allowed.txt", b"inside").unwrap();
            assert_eq!(std::fs::read("allowed.txt").unwrap(), b"inside");
            assert!(std::fs::read(outside.join("secret")).is_err());
            assert!(std::fs::write(outside.join("write"), b"escape").is_err());
            assert!(std::fs::read("escape/secret").is_err());
            assert!(std::fs::write("escape/write", b"escape").is_err());
            assert!(std::fs::set_permissions(
                outside.join("secret"),
                std::fs::Permissions::from_mode(0o777)
            )
            .is_err());
            println!("filesystem-confined");
        }
        Some("review-boundary") => {
            for nr in [463, 466, 469, 472] {
                assert_eq!(unsafe { libc::syscall(nr, 0, 0, 0, 0, 0, 0) }, -1);
                assert_eq!(
                    std::io::Error::last_os_error().raw_os_error(),
                    Some(libc::ENOSYS),
                    "unreviewed syscall {nr}"
                );
            }
            for nr in [
                libc::SYS_rt_sigqueueinfo,
                libc::SYS_rt_tgsigqueueinfo,
                libc::SYS_sched_setparam,
                libc::SYS_sched_setaffinity,
            ] {
                // Invalid arguments cannot signal or modify any real process.
                assert_eq!(unsafe { libc::syscall(nr, -1, 0, 0, 0, 0, 0) }, -1);
                assert_eq!(
                    std::io::Error::last_os_error().raw_os_error(),
                    Some(libc::EPERM),
                    "cross-process syscall {nr}"
                );
            }
            println!("review-boundary-enforced");
        }
        Some("network") => {
            assert!(std::net::TcpListener::bind("127.0.0.1:0").is_err());
            assert!(std::net::UdpSocket::bind("127.0.0.1:0").is_err());
            assert!(std::os::unix::net::UnixStream::pair().is_err());
            assert_eq!(
                unsafe { libc::socket(libc::AF_INET6, libc::SOCK_STREAM, 0) },
                -1
            );
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
            println!("network-denied");
        }
        Some("session") => {
            assert_eq!(unsafe { libc::setsid() }, -1);
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
            assert_eq!(unsafe { libc::setpgid(0, 0) }, -1);
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
            assert_eq!(unsafe { libc::unshare(libc::CLONE_NEWUSER) }, -1);
            println!("session-confined");
        }
        Some("fd") => {
            let fd: i32 = args[2].parse().unwrap();
            assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFD) }, -1);
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EBADF)
            );
            println!("inherited-fd-closed");
        }
        Some("nested") => {
            let status = std::process::Command::new(std::env::current_exe().unwrap())
                .arg("network")
                .status()
                .unwrap();
            assert!(status.success());
            println!("descendant-confined");
        }
        Some("tree") => {
            let mut child = std::process::Command::new(std::env::current_exe().unwrap())
                .arg("hold")
                .spawn()
                .unwrap();
            println!("grandchild_pid={}", child.id());
            std::io::stdout().flush().unwrap();
            std::fs::write("parent-ready", b"ready").unwrap();
            let _ = child.wait();
        }
        Some("hold") => {
            std::fs::write("grandchild-ready", b"ready").unwrap();
            std::thread::sleep(Duration::from_secs(60));
        }
        Some("flood") => {
            let data = vec![b'x'; 65536];
            let _ = std::io::stdout().write_all(&data);
            let _ = std::io::stdout().flush();
            std::thread::sleep(Duration::from_secs(60));
        }
        Some("pty") => {
            assert_eq!(unsafe { libc::isatty(0) }, 1);
            let mut size = unsafe { std::mem::zeroed::<libc::winsize>() };
            assert_eq!(
                unsafe { libc::ioctl(0, libc::TIOCGWINSZ, &mut size as *mut libc::winsize) },
                0
            );
            println!("pty:{}x{}", size.ws_col, size.ws_row);
            std::io::stdout().flush().unwrap();
            let mut data = [0; 4];
            std::io::stdin().read_exact(&mut data).unwrap();
            assert_eq!(&data, b"ping");
            println!("pty-input-ok");
        }
        Some("marker") => {
            std::fs::write("must-not-run", b"executed").unwrap();
        }
        Some("denied-kernel") => {
            use coding_tools_local_agent::{ExecErrorKind, ExecSpec, LinuxSandbox, ProcessManager};
            let root = std::path::Path::new(&args[2]);
            let policy = LinuxSandbox::new(root).unwrap();
            let filter = [
                libc::sock_filter {
                    code: 0x20,
                    jt: 0,
                    jf: 0,
                    k: 0,
                },
                libc::sock_filter {
                    code: 0x15,
                    jt: 0,
                    jf: 1,
                    k: libc::SYS_landlock_create_ruleset as u32,
                },
                libc::sock_filter {
                    code: 0x06,
                    jt: 0,
                    jf: 0,
                    k: 0x0005_0000 | libc::ENOSYS as u32,
                },
                libc::sock_filter {
                    code: 0x06,
                    jt: 0,
                    jf: 0,
                    k: 0x7fff_0000,
                },
            ];
            let program = libc::sock_fprog {
                len: filter.len() as u16,
                filter: filter.as_ptr() as *mut libc::sock_filter,
            };
            assert_eq!(
                unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
                0
            );
            assert_eq!(
                unsafe {
                    libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog)
                },
                0
            );
            let spec = ExecSpec::new(
                vec![
                    std::env::current_exe().unwrap().display().to_string(),
                    "marker".into(),
                ],
                root,
            )
            .unwrap()
            .with_sandbox(policy);
            let runtime = tokio::runtime::Runtime::new().unwrap();
            let error = runtime
                .block_on(ProcessManager::default().run(spec))
                .unwrap_err();
            assert_eq!(error.kind, ExecErrorKind::Sandbox);
            assert!(!root.join("must-not-run").exists());
            println!("kernel-unavailable-failed-closed");
        }
        _ => std::process::exit(2),
    }
}

#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
fn main() {}
