"""Bounded staging negative controls; fixtures never authenticate production origin."""
import contextlib
import base64
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import appimage_relro_contract as c
import appimage_relro_tool as t
import appimage_relro_guard as g
import appimage_relro_guard_tests as fixtures
import appimage_relro_contract_tests as contracts
import desktop_glib_build_contract as base


def listing(size=None):
    size=c.TOOL_SIZE if size is None else size
    return ('drwxr-xr-x 0/0 100 2024-07-27 00:42 squashfs-root\n'
            'drwxr-xr-x 0/0 100 2024-07-27 00:42 squashfs-root/usr\n'
            'drwxr-xr-x 0/0 100 2024-07-27 00:42 squashfs-root/usr/bin\n'
            f'-rwxr-xr-x 0/0 {size} 2024-07-27 00:42 squashfs-root/usr/bin/patchelf\n').encode()


def receipt_fixture():
    root='/work/evidence/compiler/appimage-relro'
    def pinned(path,size,sha,mode):
        return dict(contracts.observation(path,b'',mode),size=size,sha256=sha,uid=0)
    outer=pinned('/work/originals/linuxdeploy-x86_64.AppImage',c.OUTER_SIZE,c.OUTER_SHA256,0o444)
    original=pinned(root+'/original-patchelf',c.TOOL_SIZE,c.TOOL_SHA256,0o500)
    host=contracts.observation('/usr/bin/true',b'original fixture',0o755)
    readonly=dict(host,target=root+'/probe/readonly',mode=0o600)
    mutation=dict(host,target=root+'/probe/mutation',mode=0o600)
    changed=contracts.observation(root+'/probe/mutation',b'changed fixture',0o600,inode=20)
    def call(argv,out,before=None,after=None):
        return dict(argv=argv,exit=0,stdout=base64.b64encode(out).decode(),stderr='',before=before,after=after)
    probes={'host_copy':host,'calls':[
        call(['--version'],b'patchelf 0.8\n'),
        call(['--print-rpath',root+'/probe/readonly'],b'\n',readonly,readonly),
        call(['--set-rpath','$ORIGIN',root+'/probe/mutation'],b'',mutation,changed),
        call(['--print-rpath',root+'/probe/mutation'],b'$ORIGIN\n',changed,changed)]}
    originals,aliases={},{}
    for family in t.FAMILIES:
        pin=next(v for v in c.PROTECTED.values() if v['family']==family)
        destination='lib'+family+'-2.0.so.0.7200.4'
        originals[family]=pinned('/usr/lib/x86_64-linux-gnu/'+destination,pin['size'],pin['sha256'],0o644)
        for suffix in ('.so','.so.0'):
            aliases[family+suffix]=[dict(path='/usr/lib/x86_64-linux-gnu/lib'+family+'-2.0'+suffix,
                target=destination,device=1,inode=2)]
    return dict(schema='appimage-relro-tool-v1',outer=outer,offset=c.OUTER_OFFSET,
        parser=dict(executable=dict(contracts.observation(t.PARSER,b'parser',0o755),uid=0),
            os={'id':'ubuntu','version':'22.04'},package='install ok installed\t1:4.5.1-1ubuntu0.1',
            help_sha256='a'*64,options=list(t.OPTIONS)),listing=t.listing_member(listing()),original=original,
        probes=probes,host_glib={'originals':originals,'aliases':aliases})


class RelroToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def reject(self,fun,*args):
        with self.assertRaises((base.exact.EvidenceError,OSError,ValueError)): fun(*args)

    def test_original_outer_and_inner_byte_pins_are_exact(self):
        self.assertEqual((c.OUTER_SIZE,c.OUTER_OFFSET),(13264064,193728))
        self.assertEqual(c.OUTER_SHA256,'e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef')
        self.assertEqual((c.TOOL_SIZE,c.TOOL_SHA256),(1029016,'c15c1282d9dadcaaf5e492c0ee5f929d34453f8af759cc4aadad03b5b65df879'))
        self.reject(t.exact_bytes,b'claims patchelf 0.8',c.TOOL_SIZE,c.TOOL_SHA256)

    def test_list_requires_unique_regular_member_and_directory_parents(self):
        self.assertEqual(t.listing_member(listing())['member'],'usr/bin/patchelf')
        for removed in (b'squashfs-root/usr\n',b'squashfs-root/usr/bin\n',b'squashfs-root/usr/bin/patchelf\n'):
            raw=b''.join(line for line in listing().splitlines(keepends=True) if not line.endswith(removed))
            self.reject(t.listing_member,raw)
        self.reject(t.listing_member,listing(c.TOOL_SIZE-1))
        unrelated = (b'drwxr-xr-x 0/0 100 2024-07-27 00:42 squashfs-root/share\n'
                     b'drwxr-xr-x 0/0 100 2024-07-27 00:42 squashfs-root/share/doc\n'
                     b'-rw-r--r-- 0/0 1 2024-07-27 00:42 squashfs-root/share/doc/readme\n')
        self.assertEqual(t.listing_member(listing()+unrelated)['entries'],7)
        for path in (b'squashfs-root/share\n', b'squashfs-root/share/doc\n'):
            changed=b''.join(line for line in unrelated.splitlines(keepends=True) if not line.endswith(path))
            self.reject(t.listing_member,listing()+changed)

    def test_list_rejects_link_device_duplicate_and_traversal_entries(self):
        last=listing().splitlines(keepends=True)[-1]
        for raw in (listing()+last,listing().replace(b'squashfs-root/usr/bin/patchelf',b'squashfs-root/usr/../patchelf'),
                    listing().replace(b'-rwxr-xr-x',b'crwxr-xr-x'),
                    listing().replace(last,last.replace(b'-rwxr-xr-x',b'lrwxrwxrwx').rstrip()+b' -> other\n')):
            self.reject(t.listing_member,raw)
        # The pinned archive has unrelated symlinks; they do not authorize linked tool parents.
        self.assertEqual(t.listing_member(listing()+b'lrwxrwxrwx 0/0 9 2024-07-27 00:42 squashfs-root/AppRun -> usr/bin/linuxdeploy\n')['entries'],5)
        child=b'-rw-r--r-- 0/0 1 2024-07-27 00:42 squashfs-root/unrelated/child\n'
        for ancestor in (b'-rw-r--r-- 0/0 1 2024-07-27 00:42 squashfs-root/unrelated\n',
                         b'lrwxrwxrwx 0/0 3 2024-07-27 00:42 squashfs-root/unrelated -> usr\n'):
            self.reject(t.listing_member,listing()+ancestor+child)

    def test_cat_rejects_short_extra_and_wrong_hash_bytes(self):
        data=b'authentic fixture bytes'; sha=hashlib.sha256(data).hexdigest()
        t.exact_bytes(data,len(data),sha)
        for changed in (data[:-1],data+b'x',b'X'+data[1:]): self.reject(t.exact_bytes,changed,len(data),sha)

    def test_original_archive_replacement_during_staging_rejects(self):
        originals=self.root/'originals'; originals.mkdir()
        archive=fixtures.write(originals/'linuxdeploy-x86_64.AppImage',b'outer fixture',0o444)
        parser='/usr/bin/true'; parser_record=c.observe(parser,owned=False)[1]
        calls=[]
        def replaced(fd,archive_fd,mode,output_fd=None):
            calls.append(mode)
            if mode=='-llnumeric': return listing(3)
            substitute=fixtures.write(originals/'replacement',b'outer fixture',0o444); substitute.replace(archive)
            return b'abc'
        config={'original_patchelf_path':str(self.root/'original-patchelf')}
        with patch.object(c,'OUTER_SIZE',len(b'outer fixture')),patch.object(c,'OUTER_SHA256',c.digest(b'outer fixture')),\
             patch.object(c,'TOOL_SIZE',3),patch.object(c,'TOOL_SHA256',c.digest(b'abc')),patch.object(t,'PARSER',parser),\
             patch.object(t,'parser_identity',return_value={'executable':parser_record}),patch.object(t,'parser_call',side_effect=replaced),\
             patch.object(t,'tool_probes',side_effect=AssertionError('must not execute')):
            self.reject(t.stage_original,{'config':config,'originals_dir':str(originals)})
        self.assertEqual(calls,['-llnumeric','-cat']); self.assertEqual((self.root/'original-patchelf').stat().st_mode & 0o777,0o600)

    def test_parser_path_owner_and_capabilities_are_checked(self):
        record=contracts.observation(t.PARSER,b'parser',0o755); record['uid']=0
        # Actual Ubuntu squashfs-tools 1:4.5-3build1 option-line spellings.
        help_lines=[b'\t-cat\tcat the listed files to stdout',
            b'\t-o[ffset] <bytes>\tskip <bytes> at start of <dest>',
            b'\t-lln[umeric]\t-lls but with numeric uids and gids',
            b'\t-st[rict-errors]\ttreat all errors as fatal',
            b'\t-no-wild[cards]\tdo not use wildcard matching in extract names',
            b'\t-p[rocessors] <number>\tuse <number> processors',
            b'\t-da[ta-queue] <size>\tset data queue to <size> Mbytes',
            b'\t-fr[ag-queue] <size>\tset fragment queue to <size> Mbytes']
        @contextlib.contextmanager
        def descriptor(*args,**kwargs): yield 100,None
        def inspect(raw,code=0):
            responses=[(0,b'squashfs-tools: /usr/bin/unsquashfs\n',b''),
                       (0,b'install ok installed\t1:4.5-3build1\n',b''),(code,raw,b'')]
            with patch.object(c,'observe',return_value=(b'parser',record)),patch.object(t.platform,'freedesktop_os_release',return_value={'ID':'ubuntu','VERSION_ID':'22.04'}),\
                 patch.object(base,'regular_descriptor',side_effect=descriptor),patch.object(t,'bounded_child',side_effect=responses):
                return t.parser_identity()
        raw=b'\n'.join(help_lines)+b'\n'
        observed=inspect(raw)
        self.assertEqual(observed['executable']['target'],'/usr/bin/unsquashfs')
        self.assertEqual(observed['help_sha256'],c.digest(raw))
        self.assertEqual(observed['options'],list(t.OPTIONS))
        self.assertEqual(inspect(b'\n'.join(b'\t'+option.encode()+b' option' for option in t.OPTIONS))['options'],list(t.OPTIONS))
        for index in range(len(help_lines)):
            missing=b'\n'.join(help_lines[:index]+help_lines[index+1:])+b'\n\t\tImplies -no-wildcards\n'
            self.reject(inspect,missing)
        for raw in (b'prose '+b' '.join(option.encode() for option in t.OPTIONS),
                    b'\n'.join(help_lines).replace(b'-lln[umeric]',b'-lln[umeric'),
                    b'\n'.join(help_lines).replace(b'-cat\t',b'-cat-extra\t')):
            self.reject(inspect,raw)
        self.reject(inspect,b'\n'.join(help_lines),2)
        wrong=dict(record,uid=55)
        with patch.object(c,'observe',return_value=(b'parser',wrong)): self.reject(t.parser_identity)

    def test_parser_nonzero_timeout_and_stream_overflow_reject(self):
        with patch.object(t,'bounded_child',return_value=(1,b'',b'bad parser')): self.reject(t.parser_call,1,2,'-cat')
        executable=str(Path(sys.executable).resolve()); fd=os.open(executable,os.O_RDONLY)
        try:
            for code,expected in (('import time;time.sleep(10)','child_timeout'),('print("x"*100000)','child_stream_limit')):
                with self.assertRaisesRegex(base.exact.EvidenceError,expected):
                    g.bounded_child(fd,[executable,'-c',code],timeout=.2,stdout_limit=500)
        finally: os.close(fd)
        with patch.object(t,'bounded_child',return_value=(0,b'abc',b'')) as child:
            self.assertEqual(t.parser_call(1,2,'-cat'),b'abc')
            args=child.call_args.args[1]
            self.assertIn('-strict-errors',args); self.assertEqual(args[args.index('-data-queue')+1],'4')
            self.assertEqual(child.call_args.kwargs['extra_fds'],(2,))

    def test_staged_tool_is_nonexecutable_until_hash_passes(self):
        path=self.root/'original-patchelf'; data=b'fixture tool'
        with patch.object(c,'TOOL_SIZE',len(data)),patch.object(c,'TOOL_SHA256',c.digest(data)):
            checked=t.exact_bytes
            def check(raw,size,sha):
                self.assertEqual(path.stat().st_mode & 0o777,0o600); checked(raw,size,sha)
            with patch.object(t,'exact_bytes',side_effect=check): t.stage_file(path,data)
        self.assertEqual(path.stat().st_mode & 0o777,0o500)
        bad=self.root/'failed-tool'
        self.reject(t.stage_file,bad,b'not pinned')
        self.assertEqual(bad.stat().st_mode & 0o777,0o600)

    def test_session_requires_fresh_disjoint_owned_paths(self):
        config=contracts.fixture_config()
        source,target,evidence,originals=[self.root/n for n in ('source','target','evidence','originals')]
        for root in (source,target,evidence,originals): root.mkdir(mode=0o700)
        binding={'source_root':str(source)}
        self.reject(t.prepare_session,binding,source/'target',evidence,{'originals_dir':str(originals)},{})
        (evidence/'appimage-relro').mkdir(mode=0o700)
        self.reject(t.prepare_session,binding,target,evidence,{'originals_dir':str(originals)},{})
        self.assertTrue((evidence/'appimage-relro').is_dir())
        config['target_root']=config['source_root']+'/target'; self.reject(c.validate_config,config)

    def test_symlink_hardlink_and_existing_tool_destinations_reject(self):
        target=fixtures.write(self.root/'existing',b'data')
        alias=self.root/'alias'; alias.symlink_to(target)
        self.reject(t.stage_file,alias,b'data'); self.reject(t.stage_file,target,b'data')
        hard=self.root/'hard'; os.link(target,hard)
        self.reject(c.observe,hard)
        self.assertEqual(target.read_bytes(),b'data')

    def test_compiler_binding_requires_finished_verified_copies(self):
        config=contracts.fixture_config()
        evidence=self.root/'compiler'; evidence.mkdir(mode=0o700)
        config.update(evidence_root=str(evidence),desktop_elf_path=str(evidence/'desktop.elf'),
            original_patchelf_path=str(evidence/'appimage-relro/original-patchelf'),compiler_binding_path=str(evidence/'appimage-relro/compiler-binding.json'))
        (evidence/'appimage-relro').mkdir(mode=0o700)
        event={'root':{'executable':str(self.root/'emitted')}}
        data=b'actual retained fixture'; fixtures.write(self.root/'emitted',data)
        fixtures.write(evidence/'desktop.elf',data)
        records={'events':event,'copies':{'desktop':c.byte_record(data)}}
        base.write_json(evidence/'compiler-copies.json',records)
        base.write_json(evidence/'cargo-exit.json',{'exit':1})
        self.reject(t.bind_compiler,config,records)
        (evidence/'cargo-exit.json').write_text('{"exit":0}')
        for name,body in (('metadata.json',b'{}'),('selected-tree.txt',b'fixture'),('build.jsonl',b'{"reason":"build-finished","success":true}\n')): fixtures.write(evidence/name,body)
        with patch.object(base,'verify_compiler_events',return_value=event):
            result=t.bind_compiler(config,records)
            self.assertEqual(result['prebundle'],c.byte_record(data))
            self.reject(t.bind_compiler,config,records)
        self.assertEqual(base.decode((evidence/'appimage-relro/compiler-binding.json').read_bytes()),result)

    def test_host_glib_versioned_bytes_must_match_signed_originals(self):
        originals={}
        for family in t.FAMILIES:
            pin=next(v for v in c.PROTECTED.values() if v['family']==family)
            self.assertEqual(pin['sha256'],c.FAMILIES[family][1])
            originals[family]=pin
        # Version/package labels cannot substitute for byte identity before any build.
        with patch.object(c,'observe',return_value=(b'wrong host bytes',contracts.observation('/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0.7200.4',b'wrong host bytes'))):
            self.reject(t.host_glib_inputs)
        self.assertEqual(set(originals),{'glib','gio','gobject','gmodule'})
        receipt=receipt_fixture()
        self.assertEqual(t.verify_tool_receipt(contracts.encoded(receipt)),receipt)
        warning=copy.deepcopy(receipt); calls=warning['probes']['calls']; target=calls[2]['argv'][-1]
        for record in (warning['probes']['host_copy'],calls[1]['before'],calls[1]['after'],calls[2]['before']):
            record.update(size=26936,sha256='94f5d1c6ad51bbd532bf2e702b3d28cb57ba8887435b4514a06e4ba0cd7fedba')
        for record in (calls[2]['after'],calls[3]['before'],calls[3]['after']):
            record.update(size=34680,sha256='0368ae5de963c8931adc05c65d4222434321314a4c0e2e1e25053fab2e039b19')
        raw=f"warning: working around a Linux kernel bug by creating a hole of 4096 bytes in ‘{target}’\n".encode()
        calls[2]['stderr']=base64.b64encode(raw).decode()
        self.assertEqual(t.verify_tool_receipt(contracts.encoded(warning)),warning)
        self.assertTrue(t.probe_result(2,target,calls[2],b'',raw))
        for index in (0,1,3): self.assertFalse(t.probe_result(index,target,calls[2],b'',raw))
        for field,value in (('argv',['--print-rpath',target]),('exit',1),('exit',False)):
            changed=copy.deepcopy(warning); changed['probes']['calls'][2][field]=value
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        for changed_raw in (raw+b'x',raw.replace(b'4096',b'8192'),raw.replace(target.encode(),(target+'.other').encode()),b'unknown warning\n'):
            changed=copy.deepcopy(warning); changed['probes']['calls'][2]['stderr']=base64.b64encode(changed_raw).decode()
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        changed=copy.deepcopy(warning); changed['probes']['calls'][2]['stdout']=base64.b64encode(b'unexpected').decode()
        self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        for side in ('before','after'):
            for key,value in (('size',1),('sha256','0'*64)):
                changed=copy.deepcopy(warning); changed['probes']['calls'][2][side][key]=value
                self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        for index in (0,1,3):
            changed=copy.deepcopy(warning); changed['probes']['calls'][index]['stderr']=calls[2]['stderr']
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))

        for section,key in (('original','sha256'),('outer','sha256')):
            changed=copy.deepcopy(receipt); changed[section][key]='0'*64
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        changed=copy.deepcopy(receipt); changed['probes']['calls'][3]['stdout']=base64.b64encode(b'wrong').decode()
        self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        changed=copy.deepcopy(receipt); changed['host_glib']['originals']['gio']['sha256']='0'*64
        self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        changed=copy.deepcopy(receipt); changed['host_glib']['aliases']['glib.so'][0]['target']='foreign'
        self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        changed=copy.deepcopy(receipt); changed['probes']['calls'][2]['exit']=True
        self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        self.reject(t.verify_tool_receipt,b'{"schema":1,"schema":1}')
        alias=receipt['host_glib']['aliases']['glib.so'][0]
        terminal=alias['target']; root='/usr/lib/x86_64-linux-gnu/'
        valid=copy.deepcopy(receipt)
        valid['host_glib']['aliases']['glib.so']=[dict(alias,target='libglib-2.0.so.0'),
            dict(alias,path=root+'libglib-2.0.so.0')]
        self.assertEqual(t.verify_tool_receipt(contracts.encoded(valid)),valid)
        for chain in ([dict(alias,target='libglib-2.0.so'),alias],
                      [alias,dict(alias,path=root+terminal)],
                      [dict(alias,target='libglib-2.0.so.0'),
                       dict(alias,path=root+'libglib-2.0.so.0',target='libglib-2.0.so'),alias]):
            changed=copy.deepcopy(receipt); changed['host_glib']['aliases']['glib.so']=chain
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        for target in ('', '.', '..', '/absolute', 'nested/name', 'bad\\name', 'bad\nname', 'bad\x00name', 'bad\x7fname'):
            changed=copy.deepcopy(receipt)
            changed['host_glib']['aliases']['glib.so']=[dict(alias,target=target),dict(alias,path=root+target)]
            self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        for key,values in (('device',(True,-1,1.5,'1',1<<64)),('inode',(False,0,-1,2.5,'2',1<<64))):
            for value in values:
                changed=copy.deepcopy(receipt); changed['host_glib']['aliases']['glib.so'][0][key]=value
                self.reject(t.verify_tool_receipt,contracts.encoded(changed))
        # Exercise the collector path too; the synthetic host bytes are never claimed as pinned.
        info=SimpleNamespace(st_mode=0o120777,st_uid=0,st_dev=True,st_ino=1,
            st_size=10,st_mtime_ns=1,st_ctime_ns=1,st_nlink=1)
        with patch.object(c,'observe',return_value=(b'fixture',{})),patch.object(t,'exact_bytes'),\
             patch.object(Path,'lstat',return_value=info),patch.object(os,'readlink',return_value=terminal):
            self.reject(t.host_glib_inputs)


if __name__=='__main__': unittest.main()
