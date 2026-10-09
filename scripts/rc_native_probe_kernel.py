"""Native private subreaper children only; exact V5 identity/closure fragments."""
import hashlib
import os
from pathlib import Path
import signal
import stat
import time
from rc_native_probe_restore import sha

def identity(path):
    path = Path(path)
    info = path.stat()
    return dict(realpath=str(path.resolve()), size=info.st_size, mode=stat.S_IMODE(info.st_mode),
                uid=info.st_uid, gid=info.st_gid, nlink=info.st_nlink, sha256=sha(path.read_bytes()))

def realm():
    return dict(uid=os.getuid(), euid=os.geteuid(), gid=os.getgid(), egid=os.getegid(),
                uname=list(os.uname()), boot_id_sha256=sha(Path('/proc/sys/kernel/random/boot_id').read_bytes()),
                pid_namespace=os.readlink('/proc/self/ns/pid'))

def proc_fields(path):
    return {key: value.strip() for key, value in
            (line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)}

def kernel(pid, fd):
    # pid is in the caller's native namespace; /proc may expose an ancestor.
    own = proc_fields(Path('/proc/self/status'))
    depth = len(own['NSpid'].split())-1
    assert int(own['NSpid'].split()[depth]) == os.getpid()
    bound = proc_fields(Path('/proc/self/fdinfo/'+str(fd)))
    values = bound['NSpid'].split()
    assert len(values) > depth and int(values[depth]) == pid
    status = proc_fields(Path('/proc/'+bound['Pid']+'/status'))
    assert status['Pid'] == bound['Pid'] and status['NSpid'].split() == values
    raw = Path('/proc/'+bound['Pid']+'/stat').read_text()
    assert raw.split(' ', 1)[0] == bound['Pid']
    fields = raw[raw.rfind(')')+2:].split()
    again = proc_fields(Path('/proc/self/fdinfo/'+str(fd)))
    assert again['Pid'] == bound['Pid'] and again['NSpid'].split() == values
    assert int(fields[1]) == int(own['Pid'])
    return dict(pid=pid, proc_pid=bound['Pid'], NSpid=values, state=fields[0],
                ppid=os.getpid(), proc_ppid=int(fields[1]), pgid=os.getpgid(pid),
                sid=os.getsid(pid), starttime=int(fields[19]))

def owned_family_close(deadline, evidence):
    # Only this private subreaper's kernel children; namespace and pidfd rebound
    # before signalling. Repeat after reaping: grandchildren can be adopted later.
    own = proc_fields(Path('/proc/self/status'))
    depth = len(own['NSpid'].split())-1
    assert int(own['NSpid'].split()[depth]) == os.getpid()
    while time.monotonic() < deadline:
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return True
        for path in Path('/proc').glob('[0-9]*/status'):
            try:
                fields = proc_fields(path)
            except (FileNotFoundError, ProcessLookupError):
                continue
            if fields['PPid'] != own['Pid']:
                continue
            values = fields['NSpid'].split()
            assert len(values) > depth
            native = int(values[depth])
            fd = os.pidfd_open(native)
            try:
                bound = proc_fields(Path('/proc/self/fdinfo/'+str(fd)))
                again = proc_fields(path)
                assert bound['Pid'] == fields['Pid'] and bound['NSpid'].split() == values
                assert again['PPid'] == own['Pid'] and again['NSpid'].split() == values and again['Pid'] == fields['Pid']
                observed = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                live = observed is None
                if live:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                while observed is None and time.monotonic() < deadline:
                    time.sleep(.01)
                    observed = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                assert observed is not None, 'owned descendant exit UNKNOWN'
                reaped = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG)
                assert reaped == observed
                evidence.append(dict(native=native, proc_pid=fields['Pid'], NSpid=values,
                                     code=reaped.si_code, status=reaped.si_status, unexpectedly_live=live))
            finally:
                os.close(fd)
        time.sleep(.01)
    raise TimeoutError('owned family closure UNKNOWN')
