"""Real ordinary-child/fixture checks, not authenticated production backend probes."""
import contextlib
import hashlib
import io as streams
import json
import os
from pathlib import Path
import signal
import stat
import struct
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import appimage_relro_contract as c
import appimage_relro_guard as g
import desktop_glib_build_contract as base
import desktop_glib_deb_tests as old

CHILD = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <sys/stat.h>
int main(int argc,char**argv){
 const char *action=getenv("RELRO_TEST_ACTION");
 if(action && !strcmp(action,"signal")){raise(SIGTERM);return 1;}
 if(action && !strcmp(action,"exit")){fwrite("bad\0out",1,7,stdout);fputs("err",stderr);return 7;}
 if(action && !strcmp(action,"timeout")){sleep(10);return 0;}
 if(action && !strcmp(action,"overflow")){for(int j=0;j<2000000;j++)putchar('x');return 0;}
 int mutate=0,i=1;
 for(;i<argc;i++){
  if(!strcmp(argv[i],"--version")){puts("ordinary fixture child");return 0;}
  if(!strcmp(argv[i],"--set-rpath")||!strcmp(argv[i],"--remove-needed")||!strcmp(argv[i],"--set-interpreter")){mutate=1;i++;}
  else if(!strcmp(argv[i],"--print-rpath")||!strcmp(argv[i],"--print-interpreter")||!strcmp(argv[i],"--debug")){}
  else break;
 }
 if(i>=argc)return 9;
 if(access(argv[i],R_OK))return 8;
 if(mutate){char tmp[8192];snprintf(tmp,sizeof(tmp),"%s_patchelf_tmp",argv[i]);FILE*in=fopen(argv[i],"rb"),*out=fopen(tmp,"wb");if(!in||!out)return 8;int ch;while((ch=fgetc(in))!=EOF)fputc(ch,out);fputs("MUTATED",out);fclose(in);fclose(out);chmod(tmp,0600);if(rename(tmp,argv[i]))return 6;}
 else {fwrite("query\0out\n",1,10,stdout);fputs("queryerr\n",stderr);}
 return 0;
}
'''


def elf():
    blob = bytearray(old.elf())
    struct.pack_into('<H', blob, 56, 6)
    for index, fields in enumerate(((2, 6, 8192, 0x402000, 0x402000, 48, 48, 8),
        (0x6474e552, 4, 8192, 0x402000, 0x402000, 4096, 4096, 1),
        (0x6474e551, 6, 0, 0, 0, 0, 0, 16)), 3):
        struct.pack_into('<IIQQQQQQ', blob, 64+56*index, *fields)
    struct.pack_into('<qQqQqQ', blob, 8192, 30, 8, 0x6ffffffb, 0x8000001, 0, 0)
    return bytes(blob)


def write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)
    return path


class Fixture:
    def __init__(self, directory, backend):
        self.base = Path(directory)
        self.source, self.target, self.evidence = [self.base/n for n in ('source','target','evidence')]
        for root in (self.source,self.target,self.evidence): root.mkdir(mode=0o700)
        self.root = self.evidence/'appimage-relro'; self.root.mkdir(mode=0o700)
        self.appdir = self.target/'x86_64-unknown-linux-gnu/release/bundle/appimage/Coding Tools MCP.AppDir'
        self.compiled = elf(); self.payload = self.compiled.replace(old.deb.UNK,c.APP,1)
        write(self.evidence/'desktop.elf',self.compiled)
        write(self.source/'scripts/appimage_relro_guard.py',b'fixture source',0o755)
        self.tool = write(self.root/'original-patchelf',Path(backend).read_bytes(),0o500)
        sha = '1'*40
        producer = dict(provider='github-actions',repository='Eswink/coding-tools-mcp',source_sha=sha,workflow_sha=sha,
            run_id='1',run_attempt='1',workflow_ref='Eswink/coding-tools-mcp/.github/workflows/linux-rc-packages.yml@refs/heads/ci/preliminary-packages-test',
            job='build',runner_os='Linux',platform={'id':'ubuntu','version_id':'22.04'})
        self.config = dict(schema='appimage-relro-config-v1',profile=c.PROFILE,source_sha=sha,source_tree='2'*40,
            producer=producer,source_root=str(self.source),target_root=str(self.target),evidence_root=str(self.evidence),
            appdir_root=str(self.appdir),compiler_binding_path=str(self.root/'compiler-binding.json'),
            desktop_elf_path=str(self.evidence/'desktop.elf'),original_patchelf_path=str(self.tool),
            original_patchelf_size=c.TOOL_SIZE,original_patchelf_sha256=c.TOOL_SHA256,
            guard_path=str(self.source/'scripts/appimage_relro_guard.py'),guard_sha256=hashlib.sha256(b'fixture source').hexdigest(),
            guard_mode=0o755,python_path=str(Path(sys.executable).resolve()),python_sha256=base.file_record(Path(sys.executable).resolve(),single_link=False)['sha256'],python_version='Python '+sys.version.split()[0],
            protected=c.PROTECTED,caps=c.CAPS)
        base.write_json(self.root/'config.json',self.config); (self.root/'config.json').chmod(0o400)
        self.config_hash=base.file_record(self.root/'config.json')['sha256']
        binding={key:self.config[key] for key in ('profile','source_sha','source_tree','producer','target_root')}
        binding.update(schema='appimage-relro-compiler-v1',compiler_copies_sha256='4'*64,build_jsonl_sha256='5'*64,
            prebundle=c.byte_record(self.compiled),event_executable=str(self.target/'x86_64-unknown-linux-gnu/release/coding-tools-mcp-desktop'))
        base.write_json(self.root/'compiler-binding.json',binding)
        for name in ('lock','operations.jsonl'): write(self.root/name,b'')
        base.write_json(self.root/'state.json',dict(schema='appimage-relro-state-v1',config_sha256=self.config_hash,
            phase='prepared',next_sequence=1,completed_calls=0,total_hashed_bytes=g.BOOT_HASH_BYTES,journal_bytes=0))
        for path, pin in c.PROTECTED.items(): write(self.appdir/path,self.payload if pin['family']=='main' else self.compiled,pin['mode'])
        self.other=write(self.appdir/'usr/lib/other.so',b'ordinary owned target')

    def call(self,argv,verify_entry=False):
        out,err=streams.BytesIO(),streams.BytesIO()
        with patch.object(g.sys,'stdout',streams.TextIOWrapper(out,write_through=True)), patch.object(g.sys,'stderr',streams.TextIOWrapper(err,write_through=True)):
            code=g.guard_call(self.config,argv,verify_entry=verify_entry)
            stdout,stderr=out.getvalue(),err.getvalue()
        return code,stdout,stderr

    def rows(self): return [base.decode(line) for line in (self.root/'operations.jsonl').read_bytes().splitlines()]


class RelroGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        source=write(Path(cls.build.name)/'ordinary.c',CHILD.encode())
        cls.backend=Path(cls.build.name)/'ordinary'
        subprocess.run(['/usr/bin/gcc','-O2','-o',str(cls.backend),str(source)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.stack=contextlib.ExitStack(); self.addCleanup(self.stack.close)
        binary=self.backend.read_bytes()
        self.stack.enter_context(patch.object(c,'TOOL_SIZE',len(binary)))
        self.stack.enter_context(patch.object(c,'TOOL_SHA256',hashlib.sha256(binary).hexdigest()))
        pins={name:dict(pin) for name,pin in c.PROTECTED.items()}
        for pin in pins.values():
            if pin['family']!='main': pin.update(size=len(elf()),sha256=hashlib.sha256(elf()).hexdigest())
        self.stack.enter_context(patch.object(c,'PROTECTED',pins))
        self.f=Fixture(self.directory.name,self.backend)

    def setter(self,path=c.MAIN,value=None):
        return ['--set-rpath',value or c.PROTECTED[path]['rpath'],str(self.f.appdir/path)]

    def test_main_exact_app_marker_setter_preserves_all_bytes(self):
        path=self.f.appdir/c.MAIN; before=c.observe(path)[1]
        self.assertEqual(self.f.call(self.setter()),(0,b'',b''))
        self.assertEqual(before,c.observe(path)[1]); self.assertEqual(self.f.rows()[-1]['result'],'preserved')
        handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
        environment={'APPIMAGE_RELRO_CONFIG':str(self.f.root/'config.json'),'APPIMAGE_RELRO_CONFIG_SHA256':self.f.config_hash}
        with patch.dict(os.environ,environment),patch.object(g,'__file__',self.f.config['guard_path']):
            with self.assertRaises(SystemExit) as stopped: g.main(self.setter())
            self.assertEqual(stopped.exception.code,0)
        for sig,handler in handlers.items(): signal.signal(sig,handler)


    def test_all_eight_dso_alias_setters_preserve_original_bytes(self):
        for path in c.PROTECTED:
            if path!=c.MAIN:
                self.assertEqual(self.f.call(self.setter(path))[0],0)
                self.assertEqual((self.f.appdir/path).read_bytes(),self.f.compiled)
        self.assertEqual(len(self.f.rows()),16)

    def test_repeated_gtk_setters_are_idempotent_and_recorded(self):
        for _ in range(3): self.assertEqual(self.f.call(self.setter())[0],0)
        self.assertEqual([r['sequence'] for r in self.f.rows()],[1,1,2,2,3,3])
        self.assertEqual((self.f.appdir/c.MAIN).read_bytes(),self.f.payload)

    def test_protected_queries_delegate_exact_output_and_arguments(self):
        args=['--debug','--print-rpath',str(self.f.appdir/c.MAIN),'ignored']
        code,out,err=self.f.call(args)
        self.assertEqual((code,out,err),(0,b'query\0out\n',b'queryerr\n'))
        self.assertEqual(self.f.rows()[0]['argv'],args)
        host=write(Path(self.directory.name)/'host/libgio-2.0.so.0.7200.4',b'host fixture')
        alias=host.parent/'libgio-2.0.so.0'; alias.symlink_to(host.name)
        self.assertEqual(self.f.call(['--print-rpath',str(alias)])[0],0)
        self.assertEqual(self.f.rows()[-2]['before']['resolved'],str(host))

    def test_unprotected_setter_delegates_real_mutation_and_rename(self):
        before=self.f.other.stat().st_ino
        self.assertEqual(self.f.call(['--set-rpath','$ORIGIN',str(self.f.other)])[0],0)
        self.assertNotEqual(before,self.f.other.stat().st_ino)
        self.assertTrue(self.f.other.read_bytes().endswith(b'MUTATED'))

        for fault in ('writable','owner','replaced'):
            with tempfile.TemporaryDirectory() as directory:
                f=Fixture(directory,self.backend); parent=f.other.parent
                with contextlib.ExitStack() as patches:
                    if fault=='writable': parent.chmod(0o777)
                    elif fault=='owner':
                        original_fstat=os.fstat; inode=parent.stat().st_ino
                        def wrong_owner(fd):
                            info=original_fstat(fd)
                            if info.st_ino!=inode: return info
                            values=list(info); values[4]+=1
                            return os.stat_result(values)
                        patches.enter_context(patch.object(c.os,'fstat',side_effect=wrong_owner))
                    else:
                        delegate=g.delegate_original
                        def replace_parent(*args):
                            result=delegate(*args)
                            parent.rename(parent.with_name('old-lib')); parent.mkdir()
                            write(f.other,b'foreign replacement')
                            return result
                        patches.enter_context(patch.object(g,'delegate_original',side_effect=replace_parent))
                    self.assertEqual(f.call(['--set-rpath','$ORIGIN',str(f.other)])[0],125)
                self.assertTrue((f.root/'failed.json').exists())

    def test_other_unprotected_original_operations_delegate_unchanged(self):
        argv=['--remove-needed','x.so',str(self.f.other),'ignored']
        self.assertEqual(self.f.call(argv)[0],0)
        self.assertEqual(self.f.rows()[0]['argv'],argv)
        self.assertEqual(self.f.call(['--version'])[0],0)
        self.assertEqual(self.f.call(['--unknown']),(8,b'',b''))
        self.assertEqual(self.f.rows()[-2]['argv'],['--unknown'])

    def test_original_operand_parser_does_not_assume_last_argument(self):
        argv=['--print-rpath',str(self.f.other),str(self.f.appdir/c.MAIN)]
        self.assertEqual(g.classify_original_argv(argv)['target'],str(self.f.other))
        self.assertEqual(self.f.call(argv)[0],0)
        self.assertEqual(g.classify_original_argv(['--unknown','--set-rpath','x'])['target'],'--unknown')

    def test_wrong_protected_hash_never_reaches_delegate(self):
        path=next(n for n in c.PROTECTED if n!=c.MAIN)
        write(self.f.appdir/path,b'bad',0o644)
        with patch.object(g,'delegate_original',side_effect=AssertionError('unsafe delegation')):
            self.assertEqual(self.f.call(self.setter(path))[0],125)
        self.assertTrue((self.f.root/'failed.json').exists())

    def test_wrong_rpath_extra_flags_and_new_protected_mutation_reject(self):
        for index, variant in enumerate(('wrong','extra','mutation')):
            with tempfile.TemporaryDirectory() as directory:
                f=Fixture(directory,self.backend); target=str(f.appdir/c.MAIN)
                argv={'wrong':['--set-rpath',':$ORIGIN',target],
                      'extra':['--debug','--set-rpath','$ORIGIN/../lib',target],
                      'mutation':['--remove-needed','x',target]}[variant]
                with self.subTest(variant=variant):
                    self.assertEqual(f.call(argv)[0],125)
                    self.assertEqual((f.appdir/c.MAIN).read_bytes(),f.payload)
                    self.assertEqual(f.rows()[-1]['result'],'rejected')

    def test_outside_root_and_basename_impostors_never_preserve(self):
        host=write(Path(self.directory.name)/'libglib-2.0.so.0',self.f.compiled,0o644)
        self.assertEqual(self.f.call(['--set-rpath','$ORIGIN',str(host)])[0],125)
        self.assertEqual(host.read_bytes(),self.f.compiled)
        self.assertEqual(self.f.rows()[-1]['result'],'rejected')

    def test_protected_symlink_hardlink_and_owner_changes_reject(self):
        path=self.f.appdir/c.MAIN; real=path.with_name('real'); path.rename(real); path.symlink_to(real.name)
        with self.assertRaises((OSError,base.exact.EvidenceError)): c.protected_record(self.f.config,str(path))
        path.unlink(); os.link(real,path)
        with self.assertRaises(base.exact.EvidenceError): c.protected_record(self.f.config,str(path))
        path.unlink(); real.rename(path)
        with patch.object(c.os,'geteuid',return_value=os.geteuid()+1):
            with self.assertRaises(base.exact.EvidenceError): c.protected_record(self.f.config,str(path))
        fifo=Path(self.directory.name)/'fifo'; os.mkfifo(fifo,0o600)
        code="""import os,sys
sys.path.insert(0,sys.argv[1])
import appimage_relro_contract as c, appimage_relro_guard as g
for function,args in ((c.observe,(sys.argv[2],)),(g.owned_fd,(sys.argv[2],os.O_RDONLY))):
 try: function(*args)
 except (OSError,c.base.exact.EvidenceError): pass
 else: raise AssertionError('FIFO accepted')
"""
        started=time.monotonic()
        result=subprocess.run([sys.executable,'-c',code,str(Path(__file__).parent),str(fifo)],capture_output=True,timeout=2)
        self.assertEqual(result.returncode,0,result.stderr.decode()); self.assertLess(time.monotonic()-started,2)


    def test_descriptor_and_named_path_replacement_reject(self):
        path=self.f.appdir/c.MAIN; original=os.read; changed=False
        def replacing(fd,size):
            nonlocal changed
            out=original(fd,size)
            if not changed and out.startswith(b'\x7fELF'):
                changed=True; replacement=write(path.with_name('replacement'),self.f.payload,0o755); replacement.replace(path)
            return out
        with patch.object(c.os,'read',side_effect=replacing):
            with self.assertRaises(base.exact.EvidenceError): c.observe(path)

    def test_original_tool_substitution_rejects_before_exec(self):
        self.f.tool.chmod(0o600); self.f.tool.write_bytes(b'wrong tool'); self.f.tool.chmod(0o500)
        self.assertEqual(self.f.call(['--print-rpath',str(self.f.other)])[0],125)
        self.assertEqual(self.f.other.read_bytes(),b'ordinary owned target')
        for phase in ('before','after'):
            with tempfile.TemporaryDirectory() as directory:
                f=Fixture(directory,self.backend)
                digest=c.digest; child=g.bounded_child; hashed=[]
                def bounded_digest(data):
                    self.assertLessEqual(len(data),c.TOOL_SIZE,'oversized backend was hashed')
                    hashed.append(len(data)); return digest(data)
                def grow():
                    f.tool.chmod(0o600)
                    with f.tool.open('ab') as stream: stream.write(b'x')
                    f.tool.chmod(0o500)
                def after_child(fd,args,**kwargs):
                    kwargs['forward']=False
                    result=child(fd,args,**kwargs); grow(); return result
                if phase=='before': grow()
                with patch.object(c,'digest',side_effect=bounded_digest),patch.object(g,'bounded_child',side_effect=after_child):
                    with self.assertRaisesRegex(base.exact.EvidenceError,'invalid_observed_file'):
                        if phase=='before': g.original_descriptor(f.config)
                        else: g.delegate_original(f.config,['--print-rpath',str(f.other)],None)
                self.assertEqual(hashed,[] if phase=='before' else [c.TOOL_SIZE])

    def test_original_nonzero_and_signal_are_propagated_and_sticky(self):
        with patch.dict(os.environ,{'RELRO_TEST_ACTION':'signal'}):
            self.assertEqual(self.f.call(['--print-rpath',str(self.f.other)])[0],-signal.SIGTERM)
        self.assertEqual(self.f.rows()[-1]['signal'],signal.SIGTERM)
        self.assertEqual(self.f.call(self.setter())[0],125)

    def test_query_failure_is_recorded_even_when_caller_swallows_it(self):
        with patch.dict(os.environ,{'RELRO_TEST_ACTION':'exit'}):
            self.assertEqual(self.f.call(['--print-rpath',str(self.f.other)]),(7,b'bad\0out',b'err'))
        self.assertEqual(self.f.rows()[-1]['exit'],7)
        with self.assertRaises(base.exact.EvidenceError): g.seal_session(self.f.config)

    def test_timeout_and_output_overflow_cleanup_owned_child(self):
        fd=os.open(self.backend,os.O_RDONLY)
        try:
            for action,code in (('timeout','child_timeout'),('overflow','child_stream_limit')):
                with patch.dict(os.environ,{'RELRO_TEST_ACTION':action}):
                    with self.assertRaisesRegex(base.exact.EvidenceError,code):
                        g.bounded_child(fd,[str(self.backend),'--print-rpath',str(self.f.other)],timeout=.2,stdout_limit=1000)
        finally: os.close(fd)

    def test_pending_call_survives_crash_and_blocks_finalization(self):
        self.assertEqual(self.f.call(self.setter())[0],0)
        raw=(self.f.root/'operations.jsonl').read_bytes(); (self.f.root/'operations.jsonl').write_bytes(raw.splitlines(keepends=True)[0])
        with self.assertRaises(base.exact.EvidenceError): g.seal_session(self.f.config)

    def test_journal_write_failure_never_returns_preservation_success(self):
        with patch.object(g,'write_all',side_effect=OSError('disk full')):
            self.assertEqual(self.f.call(self.setter())[0],125)
        self.assertEqual((self.f.appdir/c.MAIN).read_bytes(),self.f.payload)

    def test_serial_calls_keep_complete_sequence_and_resource_totals(self):
        self.assertEqual(self.f.call(self.setter())[0],0)
        self.assertEqual(self.f.call(['--print-rpath',str(self.f.other)])[0],0)
        state=g.seal_session(self.f.config)
        self.assertEqual((state['phase'],state['completed_calls'],state['next_sequence']),('sealed',2,3))
        self.assertEqual(state['journal_bytes'],(self.f.root/'operations.jsonl').stat().st_size)
        self.assertGreaterEqual(state['total_hashed_bytes'],len(self.f.payload)*2)
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(directory,self.backend); children=[]
            for _ in range(3):
                pid=os.fork()
                if pid==0:
                    code=f.call(['--set-rpath','$ORIGIN/../lib',str(f.appdir/c.MAIN)])[0]
                    os._exit(code)
                children.append(pid)
            for pid in children: self.assertEqual(os.waitpid(pid,0)[1],0)
            self.assertEqual([r['sequence'] for r in f.rows()],[1,1,2,2,3,3])
            self.assertEqual(g.seal_session(f.config)['completed_calls'],3)
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(directory,self.backend)
            original_hash=hashlib.sha256; actual=[0]
            class CountingHash:
                def __init__(self,data=b''):
                    actual[0]+=len(data); self.hash=original_hash(data)
                def update(self,data): actual[0]+=len(data); self.hash.update(data)
                def hexdigest(self): return self.hash.hexdigest()
                def digest(self): return self.hash.digest()
            previous=g.BOOT_HASH_BYTES
            for path in (c.MAIN,next(p for p in c.PROTECTED if p!=c.MAIN)):
                actual[0]=0
                with patch.object(hashlib,'sha256',CountingHash),patch.dict(os.environ,{'APPIMAGE_RELRO_CONFIG_SHA256':f.config_hash}):
                    self.assertEqual(f.call(['--set-rpath',c.PROTECTED[path]['rpath'],str(f.appdir/path)],verify_entry=True)[0],0)
                state=base.decode((f.root/'state.json').read_bytes())
                self.assertGreaterEqual(state['total_hashed_bytes']-previous,actual[0])
                previous=state['total_hashed_bytes']
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(directory,self.backend); state=base.decode((f.root/'state.json').read_bytes())
            state['total_hashed_bytes']=c.CAPS['hashed']-g.BOOT_HASH_BYTES-2*c.CAPS['stream']
            (f.root/'state.json').write_bytes(g.encoded(state,c.CAPS['state']))
            with patch.object(c,'protected_record',side_effect=AssertionError('unreserved target hash')):
                self.assertEqual(f.call(['--set-rpath','$ORIGIN/../lib',str(f.appdir/c.MAIN)])[0],125)
            self.assertEqual(base.decode((f.root/'failed.json').read_bytes())['error'],'hash_budget_exhausted')
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(directory,self.backend); before=(f.root/'state.json').read_bytes()
            with patch.dict(os.environ,{'APPIMAGE_RELRO_CONFIG_SHA256':'0'*64}):
                self.assertEqual(f.call(['--version'],verify_entry=True)[0],125)
            self.assertEqual((f.root/'state.json').read_bytes(),before)
            self.assertFalse((f.root/'failed.json').exists())
        for entry in ('python_path','guard_path'):
            with tempfile.TemporaryDirectory() as directory:
                f=Fixture(directory,self.backend); original_stat=os.stat; observe=c.observe; reads=[]
                def oversized(path,*args,**kwargs):
                    info=original_stat(path,*args,**kwargs)
                    if os.fspath(path)!=f.config[entry]: return info
                    fields=list(info); fields[6]=c.CAPS['elf']+1
                    return os.stat_result(fields)
                def track(path,*args,**kwargs):
                    reads.append(os.fspath(path)); return observe(path,*args,**kwargs)
                with patch.dict(os.environ,{'APPIMAGE_RELRO_CONFIG_SHA256':f.config_hash}), \
                     patch.object(g.os,'stat',side_effect=oversized),patch.object(c,'observe',side_effect=track):
                    self.assertEqual(f.call(['--version'],verify_entry=True)[0],125)
                self.assertNotIn(f.config[entry],reads)
                self.assertEqual(base.decode((f.root/'failed.json').read_bytes())['error'],'entry_size_limit')



    def test_existing_patchelf_tmp_and_protected_inode_alias_reject(self):
        write(Path(str(self.f.appdir/c.MAIN)+'_patchelf_tmp'),b'preexisting')
        self.assertEqual(self.f.call(self.setter())[0],125)
        alias=self.f.appdir/'usr/lib/alias'; os.link(self.f.appdir/c.MAIN,alias)
        with self.assertRaises(base.exact.EvidenceError): g.target_observation(self.f.config,g.classify_original_argv(['--set-rpath','x',str(alias)]))


if __name__=='__main__': unittest.main()
