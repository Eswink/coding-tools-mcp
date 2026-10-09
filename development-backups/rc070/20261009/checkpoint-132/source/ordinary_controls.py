"""Actual tiny ordinary Python child controls; never Cargo/compiler/SUT.

Mock cases are explicitly labelled; they prove object/control behavior only.
All outputs live in a private new test directory. No native-family owner.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ordinary_build_collector04', HERE / 'collector.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
EXE = Path(sys.executable).resolve(strict=True)
EXE_SHA = hashlib.sha256(EXE.read_bytes()).hexdigest()
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}
CASES = []


def flattened(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for item in error.exceptions for leaf in flattened(item)]
    return [error]


def record(name, scope, **fields):
    CASES.append({'case': name, 'result': 'PASS', 'scope': scope, **fields})


def capture(root, source, before=lambda: None, after=lambda: None, **kwargs):
    out = root / ('case-' + str(len(CASES)))
    out.mkdir(mode=0o700)
    return c.collect_build_streams((str(EXE), '-I', '-B', '-c', source), str(root), ENV,
                                  EXE_SHA, str(out), before, after, seconds=6, **kwargs), out


def expect(name, operation, kind, *, identity=None, scope='actual_ordinary_child'):
    try:
        operation()
    except BaseException as error:
        leaves = flattened(error)
        assert isinstance(error, kind) or any(isinstance(x, kind) for x in leaves), (name, [type(x).__name__ for x in leaves])
        if identity is not None:
            assert any(x is identity for x in leaves), name
        record(name, scope, exception_types=[type(x).__name__ for x in leaves])
        return error
    raise AssertionError('expected_failure:' + name)


def run(root):
    # Full raw positive stream equality: stderr must never enter JSON stdout.
    result, out = capture(root, 'import os; os.write(1,b\'{"x":1}\\n\'); os.write(2,b"warning\\n"); os.write(1,b\'{"x":2}\\n\')')
    assert (out / 'stdout.raw').read_bytes() == b'{"x":1}\n{"x":2}\n'
    assert (out / 'stderr.raw').read_bytes() == b'warning\n'
    assert result['ordinary_capture_pass'] and not result['qualifies_native_family'] and not result['partial']
    assert all(x['state'] == 'CLOSED' for x in result['resources'])
    assert all(x['eof'] for x in result['streams'].values())
    record('independent_complete_raw_streams_and_all_owned_closes', 'actual_ordinary_child', stdout_bytes=16, stderr_bytes=8)
    result, out = capture(root, "import os; os.write(1,b'o'*1048576); os.write(2,b'e'*1048576)")
    assert result['ordinary_capture_pass'] and not result['partial']
    assert (out/'stdout.raw').read_bytes()==b'o'*1048576 and (out/'stderr.raw').read_bytes()==b'e'*1048576
    record('exact_aggregate2MiB_EOF_success_not_false_overflow', 'actual_ordinary_child', retained_bytes=c.MAX_BYTES)
    # Both streams individually below2MiB; combined output exceeds the true cap.
    expect('aggregate2MiB_overflow_is_partial_FAIL', lambda: capture(root, "import os; os.write(1,b'o'*1100000); os.write(2,b'e'*1100000)"), c.LogLimitExceeded)
    attempt = c._ATTEMPTS[-1]
    out = root / 'case-2'
    assert (out / 'stdout.raw').stat().st_size + (out / 'stderr.raw').stat().st_size == c.MAX_BYTES
    assert attempt['partial'] and attempt['log_overflow'] and not attempt['ordinary_capture_pass']
    assert all(x['state'] == 'CLOSED' for x in attempt['resources'])
    record('overflow_prefix_bounded_not_complete_evidence', 'actual_ordinary_child', retained_bytes=c.MAX_BYTES)
    expect('native_nonzero_exit_denies_complete_capture', lambda: capture(root, 'import os;os.write(2,b"error\\n");raise SystemExit(9)'), subprocess.CalledProcessError)
    assert c._ATTEMPTS[-1]['observed_returncode'] == 9 and not c._ATTEMPTS[-1]['ordinary_capture_pass']
    record('nonzero_primary_original_returncode_preserved', 'actual_ordinary_child')
    # Reserve4 inside6; TERM ignored so genuine KILL and bounded reap required.
    expect('whole_deadline_reserves_TERM2_KILL2', lambda: capture(root, 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)'), c.WholeDeadlineExceeded)
    attempt = c._ATTEMPTS[-1]
    assert attempt['term_attempted'] and attempt['kill_attempted'] and attempt['observed_returncode'] == -9
    assert attempt['elapsed_seconds'] < 6.0 and all(x['state'] == 'CLOSED' for x in attempt['resources'])
    record('real_created_child_KILL_reap_all_closes_within_whole', 'actual_ordinary_child')
    for label, args, typ in [
        ('relative_executable', ('python3',), ValueError),
        ('wrong_executable_hash', (str(EXE),), RuntimeError),
        ('unsafe_environment', (str(EXE),), ValueError),
        ('oversized_byte_cap', (str(EXE),), ValueError),
        ('oversized_budget', (str(EXE),), ValueError)]:
        out = root / ('case-' + str(len(CASES)));out.mkdir(mode=0o700)
        changes={'argv':args,'cwd':str(root),'env':ENV,'executable_sha256':EXE_SHA,'output_dir':str(out),'before_fence':lambda:None,'after_fence':lambda:None,'seconds':6,'byte_limit':c.MAX_BYTES}
        if label=='wrong_executable_hash':changes['executable_sha256']='0'*64
        if label=='unsafe_environment':changes['env']={'X':'a\x00b'}
        if label=='oversized_byte_cap':changes['byte_limit']=c.MAX_BYTES+1
        if label=='oversized_budget':changes['seconds']=481
        expect(label,lambda changes=changes:c.collect_build_streams(**changes),typ,scope='actual_prelaunch_denial_no_child')
        assert not c._ATTEMPTS[-1]['child']['attempted']
    for label, value in [('preexisting_output', 'x'), ('wrong_directory_mode', None)]:
        out=root / ('case-' + str(len(CASES)));out.mkdir(mode=0o700)
        if value is not None:(out/'existing').write_text(value)
        else:out.chmod(0o755)
        expect(label,lambda out=out:c.collect_build_streams((str(EXE),'-c','pass'),str(root),ENV,EXE_SHA,str(out),lambda:None,lambda:None,seconds=6),RuntimeError,scope='actual_prelaunch_denial_no_child')
        assert not c._ATTEMPTS[-1]['child']['attempted']
    primary=KeyboardInterrupt('ordinary_before_cancel'); seen=[]
    def before():raise primary
    expect('before_cancel_original_object_and_after_guard',lambda:capture(root,'pass',before,lambda:seen.append('after')),KeyboardInterrupt,identity=primary,scope='actual_prelaunch_cancel_no_child')
    assert seen==['after'] and not c._ATTEMPTS[-1]['child']['attempted']
    after_error=SystemExit('ordinary_after_cancel')
    def after():raise after_error
    expect('after_cancel_denies_native0_and_preserves_object',lambda:capture(root,'pass',after=after),SystemExit,identity=after_error)
    assert c._ATTEMPTS[-1]['observed_returncode']==0 and not c._ATTEMPTS[-1]['ordinary_capture_pass']
    first=SystemExit('primary-before');second=KeyboardInterrupt('after-secondary')
    def badbefore():raise first
    def badafter():raise second
    error=expect('independent_before_and_after_strong_exception_objects',lambda:capture(root,'pass',badbefore,badafter),BaseExceptionGroup,scope='actual_prelaunch_cancel_no_child')
    assert any(x is first for x in flattened(error)) and any(x is second for x in flattened(error))
    # Mock observer wraps a genuine created Python subprocess. No arbitrary PID.
    real_popen=c.subprocess.Popen; poll_error=KeyboardInterrupt('injected-poll-cancel'); primary_error=SystemExit('injected-selector-cancel')
    proxies=[]
    class Proxy:
        def __init__(self, process):self.actual=process;self.polls=0;self.waits=0
        def __getattr__(self,name):return getattr(self.actual,name)
        def poll(self):
            self.polls+=1
            if self.polls==1:raise poll_error
            return self.actual.poll()
        def wait(self,timeout):self.waits+=1;return self.actual.wait(timeout=timeout)
    real_selector=c.selectors.DefaultSelector
    class Selector:
        def __init__(self):self.actual=real_selector()
        def register(self,*a):return self.actual.register(*a)
        def get_map(self):return self.actual.get_map()
        def select(self,*a):raise primary_error
        def close(self):return self.actual.close()
    def popen(*a,**kw):
        proxy=Proxy(real_popen(*a,**kw));proxies.append(proxy);return proxy
    with patch.object(c.subprocess,'Popen',popen),patch.object(c.selectors,'DefaultSelector',Selector):
        error=expect('poll_cancel_still_independent_actual_child_wait_and_all_closes',lambda:capture(root,'import time;time.sleep(0.1)'),BaseExceptionGroup,scope='actual_ordinary_child_with_mock_observers')
    assert proxies[0].waits>=1 and proxies[0].actual.returncode==0
    assert any(x is poll_error for x in flattened(error)) and any(x is primary_error for x in flattened(error))
    assert c._ATTEMPTS[-1]['child']['object'] is proxies[0] and c._ATTEMPTS[-1]['child']['state']=='UNKNOWN'
    allocation_cancel=KeyboardInterrupt('pre-Popen-pipe-holder-allocation'); original_resource=c._resource; after_seen=[]
    def fail_resource(rec,name,close):
        if name=='stdout_pipe':raise allocation_cancel
        return original_resource(rec,name,close)
    with patch.object(c,'_resource',fail_resource):
        expect('prelinked_pipe_holder_allocation_cancel_is_0creator',lambda:capture(root,'pass',after=lambda:after_seen.append('after')),KeyboardInterrupt,identity=allocation_cancel,scope='actual_prelaunch_mock_allocation_no_child')
    assert not c._ATTEMPTS[-1]['child']['attempted'] and after_seen==['after']
    assert all(x['state']=='CLOSED' for x in c._ATTEMPTS[-1]['resources'])
    # Real created child: first stdout observation cancels; true Popen retains
    # both pipes. Finally observes them independently and actually closes each.
    pipe_cancel=KeyboardInterrupt('first-stdout-observation-after-real-Popen'); pipe_proxies=[]
    class PipeProxy:
        def __init__(self, actual):self.actual=actual;self.first=True
        def __getattr__(self,name):
            if name=='stdout' and self.first:
                self.first=False
                raise pipe_cancel
            return getattr(self.actual,name)
    def pipe_popen(*a,**kw):
        obj=PipeProxy(real_popen(*a,**kw));pipe_proxies.append(obj);return obj
    with patch.object(c.subprocess,'Popen',pipe_popen):
        expect('real_Popen_first_stdout_cancel_both_actual_pipes_closed',lambda:capture(root,'import time;time.sleep(0.1)'),KeyboardInterrupt,identity=pipe_cancel,scope='actual_ordinary_child_with_mock_pipe_observer')
    assert pipe_proxies[0].actual.stdout.closed and pipe_proxies[0].actual.stderr.closed
    assert pipe_proxies[0].actual.returncode is not None
    assert all(x['state']=='CLOSED' for x in c._ATTEMPTS[-1]['resources'])
    assert c._ATTEMPTS[-1]['pipes']['stdout']['errors'][0] is pipe_cancel
    # Pure mock resources: independent closes and original identities, no FDs.
    closed=[];close1=KeyboardInterrupt('close1');close2=SystemExit('close2')
    sample={'resources':[]}
    for name,error in [('a',close1),('b',close2),('c',None)]:
        def close(obj,name=name,error=error):
            closed.append(name)
            if error is not None:raise error
        item=c._resource(sample,name,close);item['object']=object();item['attempted']=True;item['state']='OWNED'
    errors=c.close_resources(sample)
    assert closed==['c','b','a'] and errors==[close2,close1]
    assert sample['resources'][0]['state']=='UNKNOWN' and sample['resources'][0]['object'] is not None
    assert c.close_resources(sample)==[] and closed==['c','b','a']
    record('mock_all_close_attempts_UNKNOWN_retention_no_retry', 'pure_mock_no_actual_fd_or_child')
    # Creator raises after declared mock effect: retain UNKNOWN, never reconstruct.
    mock_error=KeyboardInterrupt('mock_creator_after_effect');sample={'resources':[]};effects=[]
    item=c._resource(sample,'mock',lambda x:None)
    def creator():effects.append('effect');raise mock_error
    expect('mock_creator_effect_then_cancel_UNKNOWN',lambda:c._create_resource(item,creator),KeyboardInterrupt,identity=mock_error,scope='pure_mock_no_actual_fd_or_child')
    assert effects==['effect'] and item['state']=='UNKNOWN' and item['errors'][0] is mock_error
    # Actual file writes returning short positive counts must finish exact bytes.
    raw=root/'partial-write';fd=os.open(raw,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);original=c.os.write;sample={'streams':{'stdout':{'bytes_written':0}}};digest=hashlib.sha256()
    def short(fd,data):return original(fd,data[:3])
    try:
        with patch.object(c.os,'write',short):c._write_all(fd,b'1234567890',digest,sample,'stdout')
    finally:os.close(fd)
    assert raw.read_bytes()==b'1234567890' and sample['streams']['stdout']['bytes_written']==10 and digest.hexdigest()==hashlib.sha256(raw.read_bytes()).hexdigest()
    record('actual_short_writes_preserve_exact_original_bytes', 'actual_owned_file_only')
    # A real raw write effect followed by injected original cancel is partial
    # failure, but actual child wait/allcloses/afterfence must still happen.
    write_cancel=KeyboardInterrupt('injected_after_actual_raw_write'); real_writer=c._write_all; after_seen=[]
    def cancelled_write(fd,data,digest,rec,name):
        real_writer(fd,data[:1],digest,rec,name)
        raise write_cancel
    with patch.object(c,'_write_all',cancelled_write):
        expect('actual_raw_write_then_cancel_retains_original_and_allcloses',lambda:capture(root,'import os;os.write(1,b"abc");os.write(2,b"def")',after=lambda:after_seen.append('after')),KeyboardInterrupt,identity=write_cancel,scope='actual_ordinary_child_with_mock_writer_observer')
    assert after_seen==['after'] and c._ATTEMPTS[-1]['partial'] and not c._ATTEMPTS[-1]['ordinary_capture_pass']
    assert all(x['state']=='CLOSED' for x in c._ATTEMPTS[-1]['resources'])
    # Exact local AST fake-clock observer: late after fences must deny even exit0.
    real_clock=c.time.monotonic;calls=[]
    def late_after():calls.append('after');c.time.monotonic=lambda:real_clock()+10
    try:
        expect('late_after_guard_whole_deadline_denies_native0',lambda:capture(root,'pass',after=late_after),c.WholeDeadlineExceeded,scope='actual_ordinary_child_with_mock_clock')
    finally:c.time.monotonic=real_clock
    assert calls==['after'] and not c._ATTEMPTS[-1]['ordinary_capture_pass']
    return {'scope':'ORDINARY_ONLY_NOT_COMPILER_OR_NATIVE_FAMILY','cases':CASES,
            'named_pass':len(CASES),'actual_Cargo_compiler_SUT':0,'native_family_grants':0,
            'root_compiler_startup':'PENDING_runtime_closure_and_independent_peer'}


if __name__=='__main__':
    root=Path(tempfile.mkdtemp(prefix='ordinary04-',dir=str(HERE))).resolve();root.chmod(0o700)
    print(json.dumps(run(root),sort_keys=True))
