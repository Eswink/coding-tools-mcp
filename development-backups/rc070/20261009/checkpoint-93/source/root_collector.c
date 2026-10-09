/* Stage I ONLY. Built-in fixtures; never executes Python or a user command.
 * Source protocol is new B/EMPTY evidence, not original worker READY/DONE.
 * The creator must map only command0/private protocol1/devnull2 at exec.
 */
#include "syscall_x86_64.h"
#define FD_SLOTS (RC_MAX_HELD + 6)
#define PROC_BYTES (RC_MAX_CANDIDATES * 11 + 1)
static struct rc_owned_fd fds[FD_SLOTS];
static int children[RC_MAX_HELD]; /* ledger slot indexes, never PID authority */
static long child_pids[RC_MAX_HELD]; /* dedup only after native own-child authority */
static int transport = -1, transport_eof, unknown, launched, stopping;
static rc_u64 bytes, deadline, stop_begin, candidates;
static char proc_buf[PROC_BYTES], command[512];
static unsigned int command_used;

static void rc_zero(void *p, unsigned long n) {
    unsigned char *b=p; while(n--) *b++=0;
}
static int rc_fd_take(long fd) {
    for(int i=0;i<FD_SLOTS;i++) if(!fds[i].used) {
        fds[i].used=1; fds[i].close_unknown=0; fds[i].fd=fd; return i;
    }
    return -1;
}
static void rc_fd_close(int slot) {
    if(slot<0 || !fds[slot].used) return;
    long fd=fds[slot].fd;
    /* Retire the number before real close: UNKNOWN must never retry it. */
    fds[slot].fd=-1;
    if(fd>=0 && rc_sc1(RC_NR_CLOSE,fd)!=0) {
        fds[slot].close_unknown=1; unknown=1;
    } else fds[slot].used=0;
}
static rc_u64 rc_now_ns(void) {
    struct rc_timespec t;
    if(rc_sc2(RC_NR_CLOCK_GETTIME,1,(long)&t)!=0 || t.tv_sec<0 || t.tv_nsec<0) {
        unknown=1; return 0;
    }
    return (rc_u64)t.tv_sec*1000000000UL+(rc_u64)t.tv_nsec;
}
static void rc_pause(long nanoseconds) {
    struct rc_timespec t={0,nanoseconds};
    long x=rc_sc2(RC_NR_NANOSLEEP,(long)&t,0);
    if(x!=0 && x!=-RC_EINTR) unknown=1;
}
static int rc_emit(const char *line) {
    if(bytes>RC_TRANSPORT_LIMIT-2) { unknown=1; return -1; }
    long n=rc_sc3(RC_NR_WRITE,1,(long)line,2);
    if(n>0) bytes+=(rc_u64)n;
    return n==2 ? 0 : -1;
}
static int rc_sig_policy(int fixture) {
    struct rc_sigaction a={0,0,0,0};
    a.handler=fixture ? 0 : 1; /* DFL child / IGN collector */
    if(rc_sc4(RC_NR_RT_SIGACTION,RC_SIGTERM,(long)&a,0,8)!=0) return -1;
    a.handler=1;
    if(rc_sc4(RC_NR_RT_SIGACTION,RC_SIGPIPE,(long)&a,0,8)!=0) return -1;
    a.handler=0;
    if(rc_sc4(RC_NR_RT_SIGACTION,RC_SIGCHLD,(long)&a,0,8)!=0) return -1;
    rc_u64 empty=0;
    return rc_sc4(RC_NR_RT_SIGPROCMASK,RC_SIG_SETMASK,(long)&empty,0,8)==0 ? 0 : -1;
}
static unsigned int rc_uint(char *b, rc_u64 n) {
    char rev[20]; unsigned int k=0,j=0;
    do { rev[k++]=(char)('0'+n%10); n/=10; } while(n);
    while(k) b[j++]=rev[--k];
    return j;
}
static void rc_path_pid(char *path) {
    const char *prefix="/proc/self/task/", *suffix="/children";
    unsigned int i=0; while(*prefix) path[i++]=*prefix++;
    i+=rc_uint(path+i,(rc_u64)rc_sc0(RC_NR_GETPID));
    while(*suffix) path[i++]=*suffix++;
    path[i]=0;
}
static __attribute__((noreturn)) void rc_fixture(unsigned int mode, int writer) {
    if(rc_sc2(RC_NR_DUP2,writer,1)!=1 || rc_sc2(RC_NR_DUP2,writer,2)!=2)
        rc_sc1(RC_NR_EXIT,111);
    /* Child output descriptors are separate from the private root writer. */
    if(rc_sc1(RC_NR_CLOSE,0)!=0 || rc_sc3(RC_NR_CLOSE_RANGE,3,0xffffffffUL,0)!=0 || rc_sig_policy(1)!=0)
        rc_sc1(RC_NR_EXIT,112);
    if(mode==1) rc_sc1(RC_NR_EXIT,21);
    if(mode==2) rc_pause(300000000);
    if(mode==3 || mode==4 || mode==5) {
        struct rc_clone_args a; int child_fd=-1;
        rc_zero(&a,sizeof(a)); a.flags=RC_CLONE_PIDFD;
        a.pidfd=(rc_u64)&child_fd; a.exit_signal=RC_SIGCHLD;
        long pid=rc_sc2(RC_NR_CLONE3,(long)&a,sizeof(a));
        if(pid<0) rc_sc1(RC_NR_EXIT,113);
        if(pid>0) {
            if(rc_sc1(RC_NR_CLOSE,child_fd)!=0) rc_sc1(RC_NR_EXIT,114);
            rc_sc1(RC_NR_EXIT,0); /* force real subreaper adoption */
        }
        if(mode==4) {
            child_fd=-1;
            pid=rc_sc2(RC_NR_CLONE3,(long)&a,sizeof(a));
            if(pid<0) rc_sc1(RC_NR_EXIT,115);
            if(pid>0) {
                if(rc_sc1(RC_NR_CLOSE,child_fd)!=0) rc_sc1(RC_NR_EXIT,116);
                rc_sc1(RC_NR_EXIT,0);
            }
        }
        if(mode==5 && rc_sc0(RC_NR_SETSID)<0) rc_sc1(RC_NR_EXIT,117);
        for(;;) rc_pause(10000000);
    }
    if(mode==6) {
        char noise[4096]; for(unsigned int i=0;i<sizeof(noise);i++) noise[i]='N';
        for(unsigned int i=0;i<513;i++) {
            long n=rc_sc3(RC_NR_WRITE,1,(long)noise,sizeof(noise));
            if(n<0 && n!=-RC_EAGAIN && n!=-RC_EINTR) rc_sc1(RC_NR_EXIT,118);
            if(n<0) { i--; rc_pause(1000000); }
        }
    }
    if(mode==7) rc_sc1(RC_NR_EXIT,23);
    rc_sc1(RC_NR_EXIT,0);
    for(;;) rc_sc1(RC_NR_EXIT,119);
}
static int rc_launch(unsigned int mode) {
    int read_slot=rc_fd_take(-1), write_slot=rc_fd_take(-1), pid_slot=rc_fd_take(-1);
    if(read_slot<0 || write_slot<0 || pid_slot<0) { unknown=1; return -1; }
    int pipe[2]; long ret=rc_sc2(RC_NR_PIPE2,(long)pipe,RC_O_NONBLOCK|RC_O_CLOEXEC);
    if(ret!=0) { unknown=1; rc_fd_close(read_slot); rc_fd_close(write_slot); rc_fd_close(pid_slot); return -1; }
    fds[read_slot].fd=pipe[0]; fds[write_slot].fd=pipe[1];
    struct rc_clone_args a; int created_pidfd=-1;
    rc_zero(&a,sizeof(a)); a.flags=RC_CLONE_PIDFD;
    a.pidfd=(rc_u64)&created_pidfd; a.exit_signal=RC_SIGCHLD;
    launched=1; /* actual attempt is sticky, before creation syscall */
    ret=rc_sc2(RC_NR_CLONE3,(long)&a,sizeof(a));
    if(ret==0) rc_fixture(mode,pipe[1]);
    if(ret<0) {
        unknown=1; rc_fd_close(read_slot); rc_fd_close(write_slot); rc_fd_close(pid_slot); return -1;
    }
    fds[pid_slot].fd=created_pidfd; /* native return recorded before validation */
    children[0]=pid_slot; child_pids[0]=ret; transport=read_slot;
    rc_fd_close(write_slot);
    if(created_pidfd<0) { unknown=1; return -1; }
    return 0;
}
static void rc_drain(void) {
    if(transport<0 || transport_eof || fds[transport].fd<0) return;
    char buf[4096];
    for(unsigned int step=0;step<64;step++) {
        long n=rc_sc3(RC_NR_READ,fds[transport].fd,(long)buf,sizeof(buf));
        if(n>0) { bytes+=(rc_u64)n; if(bytes>RC_TRANSPORT_LIMIT) { unknown=1; return; } }
        else if(n==0) { transport_eof=1; rc_fd_close(transport); return; }
        else if(n==-RC_EAGAIN || n==-RC_EINTR) return;
        else { unknown=1; return; }
    }
}
static void rc_wait_held(void) {
    for(int i=0;i<RC_MAX_HELD;i++) if(children[i]>=0) {
        int slot=children[i]; long fd=fds[slot].fd;
        if(fd<0) { unknown=1; continue; }
        struct rc_siginfo info; rc_zero(&info,sizeof(info));
        long r=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,fd,(long)&info,RC_WEXITED|RC_WNOHANG|RC_WNOWAIT,0);
        if(r!=0) { unknown=1; continue; }
        if(info.pid!=0) {
            if(info.pid!=child_pids[i] || info.code<1 || info.code>3) {
                unknown=1; continue;
            }
            int observed_pid=info.pid, observed_code=info.code, observed_status=info.status;
            rc_zero(&info,sizeof(info));
            r=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,fd,(long)&info,RC_WEXITED|RC_WNOHANG,0);
            if(r!=0 || info.pid!=observed_pid || info.code!=observed_code ||
                    info.status!=observed_status) { unknown=1; continue; }
            children[i]=-1; rc_fd_close(slot);
        } else if(stopping) {
            rc_u64 now=rc_now_ns();
            long signal=(now && now-stop_begin>=200000000UL) ? RC_SIGKILL : RC_SIGTERM;
            r=rc_sc4(RC_NR_PIDFD_SEND_SIGNAL,fd,signal,0,0);
            if(r!=0 && r!=-RC_ESRCH) unknown=1;
        }
    }
}
static void rc_scan_adopted(void) {
    char path[64]; rc_path_pid(path);
    int slot=rc_fd_take(-1); if(slot<0) { unknown=1; return; }
    long fd=rc_sc4(RC_NR_OPENAT,RC_AT_FDCWD,(long)path,RC_O_CLOEXEC,0);
    fds[slot].fd=fd; if(fd<0) { unknown=1; rc_fd_close(slot); return; }
    unsigned long used=0;
    for(;;) {
        long n=rc_sc3(RC_NR_READ,fd,(long)(proc_buf+used),sizeof(proc_buf)-used);
        if(n==0) break;
        if(n<0 || (unsigned long)n>=sizeof(proc_buf)-used) { unknown=1; break; }
        used+=(unsigned long)n;
    }
    rc_fd_close(slot);
    unsigned long pos=0;
    while(pos<used) {
        while(pos<used && (proc_buf[pos]==' ' || proc_buf[pos]=='\n')) pos++;
        if(pos==used) break;
        rc_u64 pid=0; unsigned int digits=0;
        while(pos<used && proc_buf[pos]>='0' && proc_buf[pos]<='9') {
            pid=pid*10+(unsigned int)(proc_buf[pos++]-'0');
            if(++digits>10 || pid>2147483647UL) { unknown=1; return; }
        }
        if(!digits || !pid || (pos<used && proc_buf[pos]!=' ' && proc_buf[pos]!='\n') || ++candidates>RC_MAX_CANDIDATES) {
            unknown=1; return;
        }
        /* Proc PID is only a candidate. A pidfd alone does not grant ownership. */
        slot=rc_fd_take(-1); if(slot<0) { unknown=1; return; }
        fd=rc_sc2(RC_NR_PIDFD_OPEN,(long)pid,0); fds[slot].fd=fd;
        if(fd==-RC_ESRCH) { rc_fd_close(slot); continue; }
        if(fd<0) { unknown=1; rc_fd_close(slot); continue; }
        struct rc_siginfo info; rc_zero(&info,sizeof(info));
        long r=rc_sc5(RC_NR_WAITID,RC_P_PIDFD,fd,(long)&info,RC_WEXITED|RC_WNOHANG|RC_WNOWAIT,0);
        if(r==-RC_ECHILD) { rc_fd_close(slot); continue; }
        if(r!=0) { unknown=1; rc_fd_close(slot); continue; }
        /* Current real waitid above proves this fd is an actual own child.
         * PID comparison below ONLY deduplicates previously proven records;
         * it never grants ownership, signal/reap rights or family closure.
         * Single-threaded root is its sole reaper, so a still-held waitable
         * child cannot have its PID recycled between these operations.
         */
        int duplicate=0;
        for(int i=0;i<RC_MAX_HELD;i++)
            if(children[i]>=0 && child_pids[i]==(long)pid) { duplicate=1; break; }
        if(duplicate) { rc_fd_close(slot); continue; }
        int free_child=-1;
        for(int i=0;i<RC_MAX_HELD;i++) if(children[i]<0) { free_child=i; break; }
        if(free_child<0) { unknown=1; rc_fd_close(slot); return; }
        children[free_child]=slot; child_pids[free_child]=(long)pid;
    }
}
static int rc_all_empty(int require_io) {
    struct rc_siginfo info; rc_zero(&info,sizeof(info));
    long r=rc_sc5(RC_NR_WAITID,RC_P_ALL,0,(long)&info,RC_WEXITED|RC_WNOHANG|RC_WNOWAIT,0);
    if(r==-RC_ECHILD) {
        /* Negative exit uses only this genuine private-root kernel fact.
         * Stale/UNKNOWN fd records are not promoted to explicit retirement.
         * Kernel root death may retire them, but cannot mint positive EMPTY.
         */
        if(!require_io) return 1;
        for(int i=0;i<RC_MAX_HELD;i++) if(children[i]>=0) return 0;
        return !launched || transport_eof;
    }
    if(r!=0) unknown=1;
    return 0;
}
static void rc_cleanup(void) {
    if(!stopping) {
        stopping=1; stop_begin=rc_now_ns(); deadline=stop_begin+RC_STOP_NS;
        if(!stop_begin) unknown=1;
    }
}
static __attribute__((noreturn)) void rc_fail_hold(void) {
    /* No EMPTY after uncertainty/deadline. Never abandon any live family. */
    unknown=1;
    rc_cleanup();
    for(;;) {
        rc_wait_held();
        if(launched) rc_scan_adopted();
        rc_drain();
        if(rc_all_empty(0)) {
            /* Natural negative terminal, not E, success or native_closed.
             * This exact single-thread private root creates no further child;
             * no descendant exists to orphan between ECHILD and raw exit.
             * Root-private fd kernel retirement needs no uncertain-number retry.
             */
            rc_sc1(RC_NR_EXIT,1);
        }
        rc_pause(10000000);
    }
}
static int rc_parse(unsigned int n) {
    if(n==2 && command[0]=='S') { rc_cleanup(); return 0; }
    if(n==2 && command[0]=='C') return 2;
    if(n==4 && command[0]=='L' && command[1]==' ' && command[2]>='0' && command[2]<='7' && !launched && !stopping)
        return rc_launch((unsigned int)(command[2]-'0'));
    return -1;
}
static int rc_read_command(void) {
    /* One byte at a time avoids silently dropping a second protocol line. */
    char b; long n=rc_sc3(RC_NR_READ,0,(long)&b,1);
    if(n==-RC_EAGAIN || n==-RC_EINTR) return 0;
    if(n!=1 || command_used>=sizeof(command)) return -1;
    if(++bytes>RC_TRANSPORT_LIMIT) return -1;
    command[command_used++]=b;
    if(b=='\n') {
        int result=rc_parse(command_used); command_used=0; return result;
    }
    return 0;
}
long rc_root_main(void) {
    for(int i=0;i<RC_MAX_HELD;i++) children[i]=-1;
    (void)rc_fd_take(0); (void)rc_fd_take(1); (void)rc_fd_take(2);
    int subreaper=0;
    if(rc_sc5(RC_NR_PRCTL,RC_PR_GET_CHILD_SUBREAPER,(long)&subreaper,0,0,0)!=0 || subreaper!=1)
        rc_fail_hold(); /* birth stub must establish it before image exec */
    if(rc_sig_policy(0)!=0) rc_fail_hold();
    for(int fd=0;fd<2;fd++) {
        long flags=rc_sc2(RC_NR_FCNTL,fd,RC_F_GETFL);
        if(flags<0 || rc_sc3(RC_NR_FCNTL,fd,RC_F_SETFL,flags|RC_O_NONBLOCK)!=0) rc_fail_hold();
    }
    if(rc_emit("B\n")!=0) rc_fail_hold();
    int emitted=0;
    for(;;) {
        int request=rc_read_command();
        if(request<0 || (request==2 && !emitted)) { unknown=1; rc_cleanup(); }
        if(request==2 && emitted && !unknown) {
            /* The genuine private protocol FDs retire only after final C. */
            rc_fd_close(0); rc_fd_close(1); rc_fd_close(2);
            if(unknown) rc_fail_hold();
            return 0; /* collector closure only, never fixture/command success */
        }
        if(launched && !emitted) { rc_wait_held(); rc_scan_adopted(); rc_drain(); }
        if(unknown) rc_fail_hold();
        if(stopping && !emitted) {
            rc_u64 now=rc_now_ns();
            if(!now || now>=deadline) rc_fail_hold();
            if(!unknown && rc_all_empty(1)) {
                /* Never restart cleanup or admit a stale before-check clock. */
                now=rc_now_ns();
                if(unknown || !now || now>=deadline) rc_fail_hold();
                if(rc_emit("E\n")!=0) { unknown=1; rc_fail_hold(); }
                emitted=1;
            }
        }
        rc_pause(1000000);
    }
}
