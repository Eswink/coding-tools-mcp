/* Stage I source candidate. No runtime/kernel-support qualification. */
#ifndef RC_SYSCALL_X86_64_H
#define RC_SYSCALL_X86_64_H
#if !defined(__x86_64__) || defined(__ILP32__)
#error "Only the Linux x86-64 LP64 syscall ABI is specified"
#endif
typedef unsigned long rc_u64;
typedef unsigned int rc_u32;
static inline long rc_sc6(long n, long a, long b, long c, long d, long e, long f) {
    register long r10 __asm__("r10") = d;
    register long r8 __asm__("r8") = e;
    register long r9 __asm__("r9") = f;
    long result;
    __asm__ volatile ("syscall" : "=a"(result)
        : "a"(n), "D"(a), "S"(b), "d"(c), "r"(r10), "r"(r8), "r"(r9)
        : "rcx", "r11", "memory", "cc");
    return result;
}
static inline long rc_sc0(long n) { return rc_sc6(n,0,0,0,0,0,0); }
static inline long rc_sc1(long n,long a) { return rc_sc6(n,a,0,0,0,0,0); }
static inline long rc_sc2(long n,long a,long b) { return rc_sc6(n,a,b,0,0,0,0); }
static inline long rc_sc3(long n,long a,long b,long c) { return rc_sc6(n,a,b,c,0,0,0); }
static inline long rc_sc4(long n,long a,long b,long c,long d) { return rc_sc6(n,a,b,c,d,0,0); }
static inline long rc_sc5(long n,long a,long b,long c,long d,long e) { return rc_sc6(n,a,b,c,d,e,0); }
#define RC_NR_READ 0
#define RC_NR_WRITE 1
#define RC_NR_CLOSE 3
#define RC_NR_POLL 7
#define RC_NR_RT_SIGACTION 13
#define RC_NR_RT_SIGPROCMASK 14
#define RC_NR_DUP2 33
#define RC_NR_NANOSLEEP 35
#define RC_NR_GETPID 39
#define RC_NR_EXIT 60
#define RC_NR_FCNTL 72
#define RC_NR_SETSID 112
#define RC_NR_PRCTL 157
#define RC_NR_CLOCK_GETTIME 228
#define RC_NR_EXIT_GROUP 231
#define RC_NR_WAITID 247
#define RC_NR_OPENAT 257
#define RC_NR_PIPE2 293
#define RC_NR_PIDFD_SEND_SIGNAL 424
#define RC_NR_PIDFD_OPEN 434
#define RC_NR_CLONE3 435
#define RC_NR_CLOSE_RANGE 436
#define RC_NR_MEMFD_CREATE 319
#define RC_NR_EXECVEAT 322
#define RC_SIGTERM 15
#define RC_SIGKILL 9
#define RC_SIGCHLD 17
#define RC_SIGPIPE 13
#define RC_EINTR 4
#define RC_ECHILD 10
#define RC_EAGAIN 11
#define RC_ESRCH 3
#define RC_WNOHANG 1
#define RC_WEXITED 4
#define RC_WNOWAIT 0x01000000
#define RC_P_ALL 0
#define RC_P_PIDFD 3
#define RC_CLONE_PIDFD 0x00001000UL
#define RC_PR_SET_CHILD_SUBREAPER 36
#define RC_PR_GET_CHILD_SUBREAPER 37
#define RC_O_CLOEXEC 0x80000
#define RC_O_NONBLOCK 0x800
#define RC_F_GETFL 3
#define RC_F_SETFL 4
#define RC_AT_FDCWD (-100)
#define RC_AT_EMPTY_PATH 0x1000
#define RC_POLLIN 1
#define RC_POLLERR 8
#define RC_POLLHUP 16
#define RC_SIG_SETMASK 2
#define RC_MAX_HELD 128
#define RC_MAX_CANDIDATES 8192
#define RC_TRANSPORT_LIMIT (2UL * 1024UL * 1024UL)
#define RC_STOP_NS 2000000000UL
struct rc_timespec { long tv_sec; long tv_nsec; };
struct rc_pollfd { int fd; short events; short revents; };
struct rc_sigaction { rc_u64 handler, flags, restorer, mask; };
struct rc_clone_args {
    rc_u64 flags, pidfd, child_tid, parent_tid, exit_signal;
    rc_u64 stack, stack_size, tls, set_tid, set_tid_size, cgroup;
};
/* Linux x86-64 siginfo_t: aligned union begins at offset16. */
struct rc_siginfo {
    int signo, error, code, align_pad;
    int pid; rc_u32 uid; int status, status_pad;
    long utime, stime; unsigned char reserved[80];
};
struct rc_owned_fd { long fd; unsigned int used, close_unknown; };
_Static_assert(sizeof(long)==8,"LP64 required");
_Static_assert(sizeof(struct rc_siginfo)==128,"kernel siginfo size");
_Static_assert(__builtin_offsetof(struct rc_siginfo,pid)==16,"kernel child PID offset");
_Static_assert(__builtin_offsetof(struct rc_siginfo,status)==24,"kernel status offset");
_Static_assert(sizeof(struct rc_clone_args)==88,"clone_args v2 size");
_Static_assert(sizeof(struct rc_sigaction)==32,"kernel sigaction LP64");
#endif
