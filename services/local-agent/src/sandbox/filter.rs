//! Linux x86_64 seccomp restrictions complementing Landlock ABI3.
//! This is not a kernel-vulnerability boundary or a syscall emulation layer.
use libc::sock_filter;

const LOAD: u16 = 0x20; // BPF_LD | BPF_W | BPF_ABS
const EQUAL: u16 = 0x15;
const SET: u16 = 0x45;
const GREATER_EQUAL: u16 = 0x35;
const RETURN: u16 = 0x06;
const ALLOW: u32 = 0x7fff_0000;
const ERRNO: u32 = 0x0005_0000;
const KILL: u32 = 0x8000_0000;

fn statement(code: u16, k: u32) -> sock_filter {
    sock_filter {
        code,
        jt: 0,
        jf: 0,
        k,
    }
}

fn jump(code: u16, k: u32, jt: u8, jf: u8) -> sock_filter {
    sock_filter { code, jt, jf, k }
}

pub(super) fn program() -> Vec<sock_filter> {
    let denied = ERRNO | libc::EPERM as u32;
    let unavailable = ERRNO | libc::ENOSYS as u32;
    let mut code = vec![
        statement(LOAD, 4),             // seccomp_data.arch
        jump(EQUAL, 0xc000_003e, 1, 0), // AUDIT_ARCH_X86_64
        statement(RETURN, KILL),
        statement(LOAD, 0),                     // seccomp_data.nr
        jump(GREATER_EQUAL, 0x4000_0000, 0, 1), // reject x32 syscall ABI
        statement(RETURN, unavailable),
        // Unknown/new syscall ranges are unavailable until explicitly reviewed.
        // In particular, Linux 6.13+ *xattrat and file_setattr must not bypass
        // the older metadata-operation restrictions below.
        jump(GREATER_EQUAL, 335, 0, 2),
        jump(GREATER_EQUAL, 424, 1, 0),
        statement(RETURN, unavailable),
        jump(GREATER_EQUAL, 453, 0, 1),
        statement(RETURN, unavailable),
        jump(EQUAL, libc::SYS_clone3 as u32, 0, 1),
        statement(RETURN, unavailable), // libc may fall back to filtered clone
    ];
    let blocked = [
        libc::SYS_socket,
        libc::SYS_socketpair,
        libc::SYS_connect,
        libc::SYS_bind,
        libc::SYS_listen,
        libc::SYS_accept,
        libc::SYS_accept4,
        libc::SYS_sendto,
        libc::SYS_recvfrom,
        libc::SYS_sendmsg,
        libc::SYS_recvmsg,
        libc::SYS_sendmmsg,
        libc::SYS_recvmmsg,
        libc::SYS_ptrace,
        libc::SYS_process_vm_readv,
        libc::SYS_process_vm_writev,
        libc::SYS_pidfd_getfd,
        libc::SYS_pidfd_send_signal,
        libc::SYS_pidfd_open,
        libc::SYS_process_madvise,
        libc::SYS_process_mrelease,
        libc::SYS_kill,
        libc::SYS_tkill,
        libc::SYS_tgkill,
        libc::SYS_rt_sigqueueinfo,
        libc::SYS_rt_tgsigqueueinfo,
        libc::SYS_setpriority,
        libc::SYS_sched_setparam,
        libc::SYS_sched_setscheduler,
        libc::SYS_sched_setaffinity,
        libc::SYS_sched_setattr,
        libc::SYS_setsid,
        libc::SYS_setpgid,
        libc::SYS_unshare,
        libc::SYS_setns,
        libc::SYS_mount,
        libc::SYS_umount2,
        libc::SYS_pivot_root,
        libc::SYS_chroot,
        libc::SYS_open_tree,
        libc::SYS_move_mount,
        libc::SYS_fsopen,
        libc::SYS_fsconfig,
        libc::SYS_fsmount,
        libc::SYS_fspick,
        libc::SYS_mount_setattr,
        libc::SYS_open_by_handle_at,
        libc::SYS_name_to_handle_at,
        libc::SYS_bpf,
        libc::SYS_perf_event_open,
        libc::SYS_userfaultfd,
        libc::SYS_io_uring_setup,
        libc::SYS_io_uring_enter,
        libc::SYS_io_uring_register,
        libc::SYS_keyctl,
        libc::SYS_add_key,
        libc::SYS_request_key,
        libc::SYS_capset,
        libc::SYS_init_module,
        libc::SYS_finit_module,
        libc::SYS_delete_module,
        libc::SYS_kexec_load,
        libc::SYS_kexec_file_load,
        libc::SYS_reboot,
        libc::SYS_fanotify_init,
        libc::SYS_swapon,
        libc::SYS_swapoff,
        libc::SYS_shmget,
        libc::SYS_shmat,
        libc::SYS_shmctl,
        libc::SYS_shmdt,
        libc::SYS_msgget,
        libc::SYS_msgsnd,
        libc::SYS_msgrcv,
        libc::SYS_msgctl,
        libc::SYS_semget,
        libc::SYS_semop,
        libc::SYS_semtimedop,
        libc::SYS_semctl,
        libc::SYS_mq_open,
        libc::SYS_mq_unlink,
        // ABI3 does not mediate these metadata changes. Do not allow them
        // outside the workspace indirectly through global paths or descriptors.
        libc::SYS_chmod,
        libc::SYS_fchmod,
        libc::SYS_fchmodat,
        452, // fchmodat2
        libc::SYS_chown,
        libc::SYS_fchown,
        libc::SYS_lchown,
        libc::SYS_fchownat,
        libc::SYS_utime,
        libc::SYS_utimes,
        libc::SYS_futimesat,
        libc::SYS_utimensat,
        libc::SYS_setxattr,
        libc::SYS_lsetxattr,
        libc::SYS_fsetxattr,
        libc::SYS_removexattr,
        libc::SYS_lremovexattr,
        libc::SYS_fremovexattr,
        libc::SYS_personality,
        libc::SYS_acct,
    ];
    for syscall in blocked {
        code.push(jump(EQUAL, syscall as u32, 0, 1));
        code.push(statement(RETURN, denied));
    }
    // Prevent new namespaces and ancestry/process-group escape through clone.
    let forbidden_clone_flags = libc::CLONE_PARENT
        | libc::CLONE_PTRACE
        | libc::CLONE_UNTRACED
        | libc::CLONE_NEWNS
        | libc::CLONE_NEWCGROUP
        | libc::CLONE_NEWUTS
        | libc::CLONE_NEWIPC
        | libc::CLONE_NEWUSER
        | libc::CLONE_NEWPID
        | libc::CLONE_NEWNET;
    code.extend([
        jump(EQUAL, libc::SYS_clone as u32, 0, 4),
        statement(LOAD, 16), // args[0], little-endian low word
        jump(SET, forbidden_clone_flags as u32, 0, 1),
        statement(RETURN, denied),
        statement(LOAD, 0),
        // Terminal injection is unnecessary even with a private PTY.
        jump(EQUAL, libc::SYS_ioctl as u32, 0, 6),
        statement(LOAD, 24), // args[1]
        jump(EQUAL, libc::TIOCSTI as u32, 0, 1),
        statement(RETURN, denied),
        jump(EQUAL, libc::TIOCLINUX as u32, 0, 1),
        statement(RETURN, denied),
        statement(LOAD, 0),
        jump(EQUAL, libc::SYS_prlimit64 as u32, 0, 4),
        statement(LOAD, 16),
        jump(EQUAL, 0, 1, 0), // self only; other processes are not ours
        statement(RETURN, denied),
        statement(LOAD, 0),
        statement(RETURN, ALLOW),
    ]);
    code
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evaluate(nr: u32, arch: u32, arg0: u32, arg1: u32) -> u32 {
        let code = program();
        let mut value = 0;
        let mut pc = 0usize;
        for _ in 0..code.len() {
            let instruction = &code[pc];
            match instruction.code {
                LOAD => {
                    value = match instruction.k {
                        0 => nr,
                        4 => arch,
                        16 => arg0,
                        24 => arg1,
                        _ => panic!("unexpected seccomp field"),
                    }
                }
                EQUAL | SET | GREATER_EQUAL => {
                    let matched = match instruction.code {
                        EQUAL => value == instruction.k,
                        SET => value & instruction.k != 0,
                        _ => value >= instruction.k,
                    };
                    pc += usize::from(if matched {
                        instruction.jt
                    } else {
                        instruction.jf
                    });
                }
                RETURN => return instruction.k,
                _ => panic!("unexpected instruction"),
            }
            pc += 1;
        }
        panic!("filter did not return")
    }

    #[test]
    fn incompatible_abis_never_reach_allow() {
        assert_eq!(evaluate(0, 0x4000_0003, 0, 0), KILL);
        assert_eq!(
            evaluate(0x4000_0000, 0xc000_003e, 0, 0),
            ERRNO | libc::ENOSYS as u32
        );
    }

    #[test]
    fn clone_and_terminal_rules_do_not_skip_final_restrictions() {
        let arch = 0xc000_003e;
        assert_eq!(
            evaluate(libc::SYS_clone as u32, arch, libc::SIGCHLD as u32, 0),
            ALLOW
        );
        assert_eq!(
            evaluate(libc::SYS_clone as u32, arch, libc::CLONE_PARENT as u32, 0),
            ERRNO | libc::EPERM as u32
        );
        assert_eq!(
            evaluate(libc::SYS_ioctl as u32, arch, 0, libc::TIOCSTI as u32),
            ERRNO | libc::EPERM as u32
        );
        assert_eq!(
            evaluate(libc::SYS_ioctl as u32, arch, 0, libc::TIOCGWINSZ as u32),
            ALLOW
        );
    }

    #[test]
    fn network_cross_process_and_metadata_syscalls_are_denied() {
        for nr in [
            libc::SYS_socket,
            libc::SYS_connect,
            libc::SYS_setsid,
            libc::SYS_setpgid,
            libc::SYS_process_vm_readv,
            libc::SYS_io_uring_setup,
            libc::SYS_chmod,
            libc::SYS_fchmodat,
            452,
            libc::SYS_setxattr,
        ] {
            assert_eq!(
                evaluate(nr as u32, 0xc000_003e, 0, 0),
                ERRNO | libc::EPERM as u32
            );
        }
        assert_eq!(evaluate(libc::SYS_read as u32, 0xc000_003e, 0, 0), ALLOW);
    }
    #[test]
    fn unreviewed_system_calls_never_reach_allow() {
        for nr in [335, 336, 400, 453, 463, 466, 469, 472, 548, u32::MAX] {
            assert_eq!(
                evaluate(nr, 0xc000_003e, 0, 0),
                ERRNO | libc::ENOSYS as u32,
                "unreviewed syscall {nr}"
            );
        }
        assert_eq!(evaluate(libc::SYS_read as u32, 0xc000_003e, 0, 0), ALLOW);
        assert_eq!(evaluate(libc::SYS_futex as u32, 0xc000_003e, 0, 0), ALLOW);
    }

    #[test]
    fn queued_signals_and_foreign_scheduler_control_are_denied() {
        for nr in [
            libc::SYS_rt_sigqueueinfo,
            libc::SYS_rt_tgsigqueueinfo,
            libc::SYS_setpriority,
            libc::SYS_sched_setparam,
            libc::SYS_sched_setscheduler,
            libc::SYS_sched_setaffinity,
            libc::SYS_sched_setattr,
        ] {
            assert_eq!(
                evaluate(nr as u32, 0xc000_003e, 0, 0),
                ERRNO | libc::EPERM as u32,
                "cross-process syscall {nr}"
            );
        }
    }
}
