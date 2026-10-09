"""Finite ordinary component controls; no sudo/build/CI/Publisher tests.

Controlled projection hashes are schema fixtures, never source provenance.
Real FD controls use only owned temporary files; emergency test cleanup is
reported separately from whether the delegate closed its actual descriptor.
"""
import copy
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import rc_disposable_git_role_install as role
import rc_disposable_public_projection as public


def records():
    profile = dict(status='NOT_RUN', loaded=0, executed=0, success=0, failures=0,
                   errors=0, skips=0, xfails=0, xpasses=0)
    source = dict(schema=public.SCHEMA, repository='Eswink/coding-tools-mcp',
                  management_commit='0' * 40, source_tree='b9cfb8a0b58f8e0863c764e50cf3d38920eefeae',
                  backup_commit='0' * 40, pure_source_count=1878, runner_bytes=6259,
                  runner_sha256='687ec2a408507284b557806569d6f5df0ead625b9c282b9c8bbb74782d633f0a',
                  fixture_sha256='233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5',
                  inventory85_sha256='0' * 64, inventory300_sha256='0' * 64)
    tools = dict(schema=public.SCHEMA, git_version='2.55.0', image_platform='linux/amd64',
                 runtime_kind='HOSTED_VM', image_provenance=dict(kind='HOSTED_VM',
                 image_version='20261009.1', container_manifest_digest=None,
                 container_config_digest=None, provenance_verified=False),
                 archive_bytes=8177180, signature_bytes=566, key_bytes=68820, tar_bytes=51916800,
                 gpg_primary='96E07AF25771955980DAD10020D04E5A713660A7',
                 gpg_subkey='E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB',
                 signature_valid=False, system_git_unchanged=False, prefix_preabsent=False,
                 configs_count=0, gitk_upstream_fallback_observed=None)
    for name in ('archive', 'signature', 'key', 'tar', 'builder_source', 'installed_binary', 'build_log', 'install_log'):
        tools[name + '_sha256'] = '0' * 64
    return dict(zip(public.FILES, [
        dict(schema=public.SCHEMA, scope='compatible-publisher-component-only', setup_status='NOT_RUN',
             profiles=dict(necessary85=profile, original300=copy.deepcopy(profile)),
             phases={name: dict(status='NOT_RUN', exit_code=None, elapsed_ms=None)
                     for name in ('gpg', 'build', 'install', 'probe')},
             release_authorized=False, product_install_runs=0, projection_only=True),
        source, tools, dict(schema=public.SCHEMA, projection_only=True,
             original_raw_available_privately='UNAVAILABLE',
             profiles={name: dict(original_seal_sha256=None, files=[])
                       for name in ('necessary85', 'original300')})]))


class EarlyFailureFirst(unittest.TestCase):
    def test_setup_pass_requires_all_actual_phase_results(self):
        r = records()[public.FILES[0]]
        r['setup_status'] = 'PASS'
        with self.assertRaises(ValueError):
            public.validate_public_projection(public.FILES[0], r)

    def test_current_setup_only_refuses_85_qualification(self):
        r = records()[public.FILES[0]]
        p = r['profiles']['necessary85']
        p.update(status='QUALIFIED', loaded=85, executed=85, success=85)
        with self.assertRaises(ValueError):
            public.validate_public_projection(public.FILES[0], r)

    def test_actual_returned_fd_not_lost_when_holder_constructor_cancels(self):
        leaked, closed_by_control = [], []
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            src = root / 'source'
            payload = b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x3e\0' + b'\0' * 108
            src.write_bytes(payload)
            parent = root / 'parent'
            parent.mkdir()
            sf = os.open(src, os.O_RDONLY)
            pf = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            def broken(fd=None):
                if fd is not None:
                    leaked.append(fd)
                raise SystemExit(17)
            try:
                with patch.object(role, 'HeldFD', broken):
                    with self.assertRaises(SystemExit):
                        role.copy_elf_role_at(sf, pf, role.parent_identity(pf), role.file_identity(sf),
                            len(payload), hashlib.sha256(payload).hexdigest(), os.geteuid())
                for fd in leaked:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
            finally:
                for fd in leaked:
                    try:
                        os.fstat(fd)
                    except OSError:
                        continue
                    os.close(fd)
                    closed_by_control.append(fd)
                os.close(sf)
                os.close(pf)
            # Emergency close above is administrative test cleanup, not delegate proof.


class ProjectionFinite(unittest.TestCase):
    def test_known_component_fixture_fourfiles_native_write(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'public'
            result = public.project_public_evidence(records(), out)
            self.assertEqual(set(result), set(public.FILES))
            self.assertEqual(set(x.name for x in out.iterdir()), set(public.FILES))

    def test_unknown_key_rejected(self):
        r = records()[public.FILES[0]]
        r['raw_proc'] = 'forbidden'
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[0], r)

    def test_boolean_not_count(self):
        r = records()[public.FILES[0]]
        r['profiles']['necessary85']['loaded'] = True
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[0], r)

    def test_wrong_tree_no_relabel(self):
        r = records()[public.FILES[1]]; r['source_tree'] = '0' * 40
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[1], r)

    def test_hash_format_rejected(self):
        r = records()[public.FILES[1]]; r['management_commit'] = 'token'
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[1], r)

    def test_hosted_image_not_container_digest(self):
        r = records()[public.FILES[2]]
        r['image_provenance']['container_manifest_digest'] = '0' * 64
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[2], r)

    def test_hosted_label_not_verified_provenance(self):
        r = records()[public.FILES[2]];r['image_provenance']['provenance_verified'] = True
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[2], r)

    def test_raw_notrun_inventory_cannot_appear(self):
        r = records()[public.FILES[3]]
        r['profiles']['necessary85']['original_seal_sha256'] = '0' * 64
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[3], r)

    def test_private_store_cannot_be_invented(self):
        r = records()[public.FILES[3]];r['original_raw_available_privately'] = 'VERIFIED'
        with self.assertRaises(ValueError): public.validate_public_projection(public.FILES[3], r)

    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError): public.parse_projection(b'{"x":1,"x":2}')

    def test_utf16_and_bom_refused(self):
        for raw in ['{"x":1}'.encode('utf-16'), b'\xef\xbb\xbf{"x":1}', b'\xff']:
            with self.assertRaises((ValueError, UnicodeError)): public.parse_projection(raw)

    def test_nonfinite_and_float_exponent_refused(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"x":1.0}'):
            with self.assertRaises(ValueError): public.parse_projection(raw)

    def test_raw_input_bound_before_decode(self):
        with self.assertRaises(ValueError): public.parse_projection(b' ' * (public.MAX_PUBLIC+1))

    def test_notrun_phase_no_execution_values(self):
        r=records()[public.FILES[0]];r['phases']['build']['exit_code']=0
        with self.assertRaises(ValueError):public.validate_public_projection(public.FILES[0],r)

    def test_missing_phase_elapsed_refuses_pass(self):
        r=records()[public.FILES[0]];r['phases']['build'].update(status='PASS',exit_code=0)
        with self.assertRaises(ValueError):public.validate_public_projection(public.FILES[0],r)

    def test_cross_file_setup_pass_needs_genuine_fields(self):
        r=records();r[public.FILES[0]]['setup_status']='PASS'
        for v in r[public.FILES[0]]['phases'].values():v.update(status='PASS',exit_code=0,elapsed_ms=1)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):public.project_public_evidence(r,Path(root)/'public')

    def test_existing_destination_never_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'public';out.mkdir();identity=out.stat().st_ino
            with self.assertRaises(FileExistsError):public.project_public_evidence(records(),out)
            self.assertEqual(out.stat().st_ino,identity)
            self.assertEqual(list(out.iterdir()),[])

    def test_symlink_destination_never_followed(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'public';original=Path(root)/'original';original.mkdir();out.symlink_to(original)
            with self.assertRaises(FileExistsError):public.project_public_evidence(records(),out)
            self.assertTrue(out.is_symlink());self.assertEqual(list(original.iterdir()),[])

    def test_unknown_output_close_invalidates_and_retains_actual_holder(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'public';real_close=os.close;seen=[];cancel=SystemExit(19)
            def broken(fd):
                if stat.S_ISREG(os.fstat(fd).st_mode) and not seen:
                    seen.append(fd);raise cancel
                return real_close(fd)
            try:
                with patch.object(role.os,'close',broken):
                    with self.assertRaises(BaseExceptionGroup) as got:public.project_public_evidence(records(),out)
                self.assertIn(cancel,got.exception.exceptions)
                self.assertFalse(out.exists())
                self.assertTrue(any(h.unknown_fd==seen[0] for h in role.UNKNOWN))
            finally:
                for h in list(role.UNKNOWN):
                    if h.unknown_fd in seen:
                        real_close(h.unknown_fd);role.UNKNOWN.remove(h)


class RoleFinite(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.payload=b'\x7fELF\x02\x01'+b'\0'*12+b'\x3e\0'+b'\0'*108
        self.source=self.root/'source';self.source.write_bytes(self.payload);self.source.chmod(0o755)
        self.parent=self.root/'parent';self.parent.mkdir()
        self.sf=os.open(self.source,os.O_RDONLY);self.pf=os.open(self.parent,os.O_RDONLY|os.O_DIRECTORY)
        self.digest=hashlib.sha256(self.payload).hexdigest()

    def tearDown(self):
        os.close(self.sf);os.close(self.pf);self.tmp.cleanup()

    def copy(self,**kwargs):
        args=dict(expected_parent=role.parent_identity(self.pf),expected_source=role.file_identity(self.sf),
                  expected_bytes=len(self.payload),expected_sha=self.digest,expected_uid=os.geteuid())
        args.update(kwargs)
        return role.copy_elf_role_at(self.sf,self.pf,**args)

    def test_real_owned_copy_regular_elf_bytes(self):
        old=os.umask(0o022)
        try:r=self.copy()
        finally:os.umask(old)
        self.assertEqual(r['close_state'],'CLOSED');self.assertEqual((self.parent/'git').read_bytes(),self.payload)
        self.assertEqual((self.parent/'git').stat().st_nlink,1)

    def test_existing_role_no_clobber(self):
        target=self.parent/'git';target.write_bytes(b'original');before=target.stat().st_ino
        with self.assertRaises(FileExistsError):self.copy()
        self.assertEqual(target.read_bytes(),b'original');self.assertEqual(target.stat().st_ino,before)

    def test_symlink_role_no_follow(self):
        target=self.parent/'git';target.symlink_to(self.source)
        with self.assertRaises(FileExistsError):self.copy()
        self.assertEqual(self.source.read_bytes(),self.payload)

    def test_source_digest_mismatch(self):
        with self.assertRaises(ValueError):self.copy(expected_sha='0'*64)
        self.assertFalse((self.parent/'git').exists())

    def test_source_identity_mismatch(self):
        source=role.file_identity(self.sf);source[1]+=1
        with self.assertRaises(ValueError):self.copy(expected_source=source)

    def test_parent_identity_mismatch(self):
        parent=role.parent_identity(self.pf);parent[1]+=1
        with self.assertRaises(ValueError):self.copy(expected_parent=parent)

    def test_payload_cap_and_magic(self):
        with self.assertRaises(ValueError):self.copy(expected_bytes=role.MAX_ELF+1)
        with patch.object(role,'digest_fd',side_effect=ValueError('badheader')):
            with self.assertRaises(ValueError):self.copy()

    def test_owned_hardlink_source_policy_preserved(self):
        os.link(self.source,self.root/'source-link')
        old=os.umask(0o022)
        try:self.copy()
        finally:os.umask(old)
        self.assertEqual(self.source.stat().st_nlink,2);self.assertEqual((self.parent/'git').stat().st_nlink,1)

    def test_partial_write_retains_primary_and_does_not_retry_role(self):
        error=OSError('controlledwrite')
        with patch.object(role.os,'write',side_effect=error):
            with self.assertRaises(OSError) as got:self.copy()
        self.assertIs(got.exception,error);self.assertTrue((self.parent/'git').exists())
        with self.assertRaises(FileExistsError):self.copy()

    def test_fsync_primary_same_object_and_real_close(self):
        error=OSError('controlledfsync');closed=[];real_close=os.close
        def close(fd):closed.append(fd);return real_close(fd)
        with patch.object(role.os,'fsync',side_effect=error),patch.object(role.os,'close',close):
            with self.assertRaises(OSError) as got:self.copy()
        self.assertIs(got.exception,error);self.assertEqual(len(closed),1)

    def test_write_primary_and_close_cancel_both_actual_objects(self):
        primary=OSError('controlledprimary');cancel=SystemExit(23);real_close=os.close;held=[]
        def close(fd):held.append(fd);raise cancel
        try:
            with patch.object(role.os,'write',side_effect=primary),patch.object(role.os,'close',close):
                with self.assertRaises(BaseExceptionGroup) as got:self.copy()
            self.assertEqual(got.exception.exceptions,(primary,cancel))
            self.assertTrue(any(h.unknown_fd==held[0] for h in role.UNKNOWN))
        finally:
            for h in list(role.UNKNOWN):
                if h.unknown_fd in held:real_close(h.unknown_fd);role.UNKNOWN.remove(h)

    def test_holder_registration_precedes_native_open(self):
        lease=role.HeldFD();self.assertEqual(lease.state,'UNOPENED');lease.close();self.assertEqual(lease.state,'CLOSED')

    def test_double_close_no_retry(self):
        lease=role.HeldFD();lease.open(self.source,os.O_RDONLY);lease.close()
        with self.assertRaises(ValueError):lease.close()

    def test_request_extra_key_arbitrary_target_rejected(self):
        with self.assertRaises(ValueError):role.validate_role_install_request({'target':'/etc/forbidden'})

    def test_request_typedbool_uid_rejected(self):
        request=dict(schema='rc070-single-git-role-1',runner_temp=str(self.root),
                     source_relative='rc070/actual-build/owned-prefix/bin/git',source_identity=role.file_identity(self.sf),
                     source_bytes=len(self.payload),source_sha256=self.digest,target_parent=role.parent_identity(self.pf),caller_uid=True)
        with self.assertRaises(ValueError):role.validate_role_install_request(request)

    def test_request_path_escape_rejected(self):
        request=dict(schema='rc070-single-git-role-1',runner_temp=str(self.root),
                     source_relative='../owned-prefix/bin/git',source_identity=role.file_identity(self.sf),
                     source_bytes=len(self.payload),source_sha256=self.digest,target_parent=role.parent_identity(self.pf),caller_uid=1001)
        with self.assertRaises(ValueError):role.validate_role_install_request(request)




class CaptureAndSetupFinite(unittest.TestCase):
    def test_real_bounded_collector_native_small_process(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1],Path(root))
            raw=prepare._capture(['/usr/bin/python3','-I','-S','-c','print("ordinary")'],seconds=2)
            self.assertEqual(raw,b'ordinary\n')
            self.assertIsNone(prepare._CAPTURE['phases'][-1]['reason'])

    def test_real_bounded_collector_stops_live_oversized_writer(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1],Path(root))
            with self.assertRaises(ValueError):
                prepare._capture(['/usr/bin/python3','-I','-S','-c',
                                  'import os,time;os.write(1,b"x"*(3*1024*1024));time.sleep(10)'],seconds=2)
            phase=prepare._CAPTURE['phases'][-1]
            self.assertEqual(phase['reason'],'LOG_LIMIT');self.assertLessEqual(phase['log_bytes'],2*1024*1024)

    def test_real_bounded_collector_timeout_keeps_original_bound(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1],Path(root))
            with self.assertRaises(ValueError):prepare._capture(['/usr/bin/python3','-I','-S','-c','import time;time.sleep(10)'],seconds=.05)
            self.assertEqual(prepare._CAPTURE['phases'][-1]['reason'],'TIMEOUT')

    def test_originaltests_durable_channel_missing_always_stop(self):
        import rc_disposable_publisher_probe as probe
        with self.assertRaises(ValueError):probe.run_disposable_publisher_probe()
        self.assertEqual(probe._SUT_RUNS,0)

    def test_preparation_failure_final_roles_all_independent_attempt(self):
        import rc_disposable_git_prepare as prepare
        primary=SystemExit(31);cancel=KeyboardInterrupt();attempts=[]
        class Reader:
            def snapshot_debian_tool(self,path,native=False):
                attempts.append(path)
                if path=='first':raise cancel
                return {'path':path}
        context=dict(dependency=Reader(),roles={'first':{'path':'first'},'second':{'path':'second'}},
                     compiler_roles={'third':{'path':'third'}},rustup_role={'path':'rustup'})
        with patch.object(prepare,'_prepare_genuine_git_delegate',side_effect=primary):
            with self.assertRaises(BaseExceptionGroup) as got:prepare.prepare_genuine_git(None,context,None)
        self.assertEqual(got.exception.exceptions,(primary,cancel))
        self.assertEqual(attempts,['first','second','third','rustup'])

    def test_official_wrong_source_rejected_before_gpg(self):
        import rc_disposable_git_prepare as prepare
        class Reader:
            def owned_debian_file_io(self,*args,**kwargs):return b'wrong'
        with patch.object(prepare,'_capture') as capture:
            with self.assertRaises(ValueError):prepare._verify_signed_source(None,Reader(),'a','b','c','d')
        capture.assert_not_called()

    def test_protected_original_function_bytecode_and_original_ast_fingerprint(self):
        import ast
        import rc_disposable_git_prepare as prepare
        root=Path(__file__).resolve().parents[1]
        vendor=root/'scripts/rc_disposable_vendor/owned_git_prepare_v4.py'
        raw=prepare._read_exact(vendor,prepare.V4_SHA)
        original=prepare._module(raw,'ordinary_original_ast_only',vendor)
        dep_path=root/'scripts/rc_disposable_vendor/owned_debian_msgfmt_prepare.py'
        dependency=prepare._module(prepare._read_exact(dep_path,prepare.DEB_SHA),'ordinary_resource_ast_only',dep_path)
        context=dict(dependency=dependency,toolchain='/ordinary/unused-existing-toolchain',roles={},
                     compiler_roles={},versions={},role_pre=lambda *a:None,role_post=lambda *a:None)
        with tempfile.TemporaryDirectory() as tmp:
            adapted,_=prepare._configure_v4(root,Path(tmp),context)
        for name in ('snapshot_original_git_source','run_owned_git_phase'):
            expected=original.__dict__[name].__code__;actual=adapted.__dict__[name].__code__
            self.assertEqual(actual.co_code,expected.co_code)
            self.assertEqual(actual.co_consts,expected.co_consts)
            self.assertEqual(actual.co_names,expected.co_names)
        node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='prepare_owned_git_v4')
        self.assertEqual(context['prepare_ast_original_sha256'],hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest())
        self.assertNotEqual(context['prepare_ast_original_sha256'],context['prepare_ast_adapted_sha256'])

    def test_role_shared_probe_deadline_expires_before_any_io(self):
        import time
        import rc_disposable_publisher_probe as probe
        context={};probe._role_callbacks(Path(__file__).resolve().parents[1],context)
        with patch.object(probe.prepare,'_capture') as capture:
            with self.assertRaises(TimeoutError):context['role_pre'](None,None,None,time.monotonic()-1)
        capture.assert_not_called()

    def test_workflow_console_capture_and_exact_artifact_names(self):
        path=Path(__file__).resolve().parents[1]/'.github/workflows/rc-disposable-publisher-compat.yml'
        raw=path.read_text()
        self.assertIn('2> "$RUNNER_TEMP/rc070-preparation-private.stderr"',raw)
        self.assertIn("if: success() && steps.preparation.outcome == 'success'",raw)
        self.assertNotIn('/*.json',raw);self.assertNotIn('set -x',raw);self.assertNotIn('cat ',raw)
        for name in public.FILES:self.assertIn('/'+name,raw)


class DualStreamFinite(unittest.TestCase):
    def test_stdout_stderr_separated_not_json_merge(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1], Path(root))
            raw = prepare._capture(['/usr/bin/python3', '-I', '-S', '-c',
                'import os;os.write(1,b"{\\"ok\\":true}\\n");os.write(2,b"private-stderr\\n")'], seconds=2)
            self.assertEqual(raw,b'{"ok":true}\n')
            logs=list(prepare._CAPTURE['directory'].glob('*.stderr.log'))
            self.assertEqual(len(logs),1);self.assertEqual(logs[0].read_bytes(),b'private-stderr\n')

    def test_stderr_alone_live_overflow_rejects(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1], Path(root))
            with self.assertRaises(ValueError):
                prepare._capture(['/usr/bin/python3','-I','-S','-c',
                    'import os,time;os.write(2,b"s"*(3*1024*1024));time.sleep(10)'],seconds=2)
            p=prepare._CAPTURE['phases'][-1]
            self.assertEqual(p['reason'],'LOG_LIMIT');self.assertLessEqual(p['log_bytes'],2*1024*1024)

    def test_combined_stream_bound_not_two_independent_caps(self):
        import rc_disposable_git_prepare as prepare
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1], Path(root))
            with self.assertRaises(ValueError):
                prepare._capture(['/usr/bin/python3','-I','-S','-c',
                    'import os,time;os.write(1,b"s"*(1200*1024));os.write(2,b"e"*(1200*1024));time.sleep(10)'],seconds=2)
            p=prepare._CAPTURE['phases'][-1]
            self.assertEqual(p['reason'],'LOG_LIMIT');self.assertLessEqual(p['log_bytes'],2*1024*1024)

    def test_poll_cancel_still_closes_both_real_returned_pipes(self):
        import rc_disposable_git_prepare as prepare
        import subprocess
        actual_popen = subprocess.Popen
        created = []
        cancel = SystemExit(71)
        def create(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            child.poll = lambda: (_ for _ in ()).throw(cancel)
            created.append(child)
            return child
        with tempfile.TemporaryDirectory() as root:
            prepare._initialize_capture(Path(__file__).resolve().parents[1], Path(root))
            with patch.object(prepare.subprocess, 'Popen', create):
                with self.assertRaises(BaseExceptionGroup) as caught:
                    prepare._capture(['/usr/bin/python3','-I','-S','-c','print("ordinary")'],seconds=2)
            self.assertIn(cancel,caught.exception.exceptions)
            self.assertEqual(len(created),1)
            self.assertTrue(created[0].stdout.closed);self.assertTrue(created[0].stderr.closed)

    def test_final_existing_file_injected_race_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'public';real_mkdir=os.mkdir;original=b'foreign-owned-race'
            def race(path,*args,**kwargs):
                result=real_mkdir(path,*args,**kwargs)
                if path=='public':(out/public.FILES[0]).write_bytes(original)
                return result
            with patch.object(public.os,'mkdir',race):
                with self.assertRaises(ValueError):public.project_public_evidence(records(),out)
            self.assertEqual((out/public.FILES[0]).read_bytes(),original)



if __name__ == '__main__':
    unittest.main(verbosity=2)
