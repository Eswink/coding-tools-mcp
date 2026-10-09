"""Six ordinary ELF-read controls and bounded readonly tool context; no process creation."""
import hashlib, importlib.util, json, pathlib, struct, sys
SRC=pathlib.Path('/workspace/work/rc070/startup-native-birth-spec-next/external/rc_native_startup_owner')
E=pathlib.Path('/workspace/work/rc070/postpublish-recovery-evidence')
EXPECTED='877d975b2221e24ecf2d86eddd13499c10b70bc8994b1bc0f6d0cea926e78dab'
OUT=pathlib.Path('/workspace/work/rc070/native-stagei-ordinary-runs/dynamic-mapping-once01')
def main():
    assert not OUT.exists()
    spec=importlib.util.spec_from_file_location('finite_current_builder',SRC/'build_source_owner.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.file_identity(SRC/'build_source_owner.py')['sha256']==EXPECTED
    source=m.snapshot(SRC/n for n in m.SOURCE_NAMES)
    runtime=m.snapshot([m.OUTER,m.GCC])
    OUT.mkdir(mode=0o700)
    results=[];frozen={};primary=None;failures=[]
    def mutate(data,offset,value):
        copy=bytearray(data);struct.pack_into('<Q',copy,offset,value);return copy
    def negative(label,data):
        p=OUT/(label+'.input')
        with m.OwnedFile(p,'xb') as stream:stream.write(data)
        try:m.elf_dependencies(p)
        except RuntimeError as error:
            results.append({'case':label,'passed':True,'actual_error':str(error)})
        else:raise AssertionError('malformed ELF admitted: '+label)
    try:
        data=m.read_bytes_owned(m.OUTER)
        info=m.elf_dependencies(m.OUTER)
        assert info['parsed_bytes_sha256']==runtime[str(m.OUTER)]['sha256']
        assert info['type'] in (2,3) and info['runtime_dependency_traversal']=='required_executable'
        results.append({'case':'D01-actual-outer-cross-LOAD-positive','passed':True})
        oldpath=E/'native-stagei23-toolclosure-source-only-backup/source/build_source_owner.py'
        assert m.file_identity(oldpath)['sha256']=='36b2db316848e0e653566522c1a26f2422fc7d9bfafbd7e4b9078857d2384dd6'
        oldspec=importlib.util.spec_from_file_location('finite_previous_builder',oldpath)
        old=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(old)
        try:old.elf_dependencies(m.OUTER)
        except RuntimeError as error:
            assert str(error)=='dynamic_strings_out_of_bounds'
            results.append({'case':'D02-old36b2-actual-outer-failure-first','passed':True,'actual_error':str(error)})
        else:raise AssertionError('old actual parser did not reject actual outer')
        header=struct.unpack_from('<HHIQQQIHHHHHH',data,16)
        phoff,phsize,phnum=header[4],header[8],header[9]
        programs=[struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize) for i in range(phnum)]
        first,second=[(i,p) for i,p in enumerate(programs) if p[0]==1][:2]
        assert first[1][2]==0 and first[1][3]==4190208 and first[1][5]==4096
        assert second[1][2]==4096 and second[1][3]==4194304
        at=phoff+second[0]*phsize
        hole=mutate(data,at+16,second[1][3]+64)
        hole=mutate(hole,at+8,second[1][2]+64)
        negative('D03-gap-with-consistent-offset',hole)
        negative('D04-conflicting-overlap-offset',mutate(data,at+16,second[1][3]-64))
        negative('D05-file-backed-segment-outside-EOF',mutate(data,at+8,len(data)))
        dynamic=next(p for p in programs if p[0]==2)
        size_at=next(offset+8 for offset in range(dynamic[2],dynamic[2]+dynamic[5],16) if struct.unpack_from('<qQ',data,offset)[0]==10)
        negative('D06-string-range-over-file-budget',mutate(data,size_at,m.FILE_LIMIT+1))
        # Readonly startup context for root's future compiler review. This is not
        # another test, a compiler query, a build, or native family qualification.
        frozen=m.snapshot(m.tool_closure() | {SRC/n for n in m.SOURCE_NAMES})
        assert all(str(p.absolute()) in frozen for p in m.TOOLS)
        m.save_json(OUT/'INPUTS-BEFORE.json',frozen)
    except BaseException as error:primary=error
    finally:
        for label,before in [('SOURCE8',source),('RUNTIME',runtime),('INPUTS',frozen)]:
            try:
                after=m.check_unchanged(before)
                m.save_json(OUT/(label+'-AFTER.json'),after)
            except BaseException as error:failures.append(error)
        report={'profile':'finite-dynamic-mapping-six-ordinary-read-controls','results':results,'primary_type':type(primary).__name__ if primary else None,'primary':str(primary) if primary else None,'cleanup_error_types':[type(e).__name__ for e in failures],'actual_compiler_queries_jobs':0,'wholecompiler_native_root_bridge_factory_original_CI_install_release':'NOTRUN','unknown_files':len(m._FILE_HOLDERS),'unknown_compilers':len(m._COMPILER_HOLDERS),'readonly_context_files':len(frozen),'full_context_before_after_established':bool(frozen) and not failures}
        try:m.save_json(OUT/'RESULT.json',report)
        except BaseException as error:failures.append(error)
    errors=([primary] if primary is not None else [])+failures
    if errors:
        if len(errors)==1:raise errors[0]
        raise BaseExceptionGroup('ordinary-read-primary-and-fence-failures',errors)
    print(json.dumps(report,sort_keys=True));return 0
if __name__=='__main__':sys.exit(main())
