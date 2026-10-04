"""Fixed, data-only source guards for the bounded debugger audit."""
NAMES = ('CmdDebugNative.cs', 'CmdDebugSession.cs', 'CmdDebugContractTests.cs', 'CmdDebugContextTests.cs')


# Exact guard fragments are mutation-tested independently of whole-source hashes.
GUARDS = {
    NAMES[0]: (
        'allocation=Marshal.AllocHGlobal(1232+15);', '(allocation.ToInt64()+15)&~15L',
        'new int[]{48,56,66,68,120,128,136,144,152,160,168,176,184,192,200,208,216,224,232,240,248}',
        'if(IntPtr.Size!=8 || !BitConverter.IsLittleEndian)', 'Raw=new byte[1232];Put32(48,0x00100003);',
        'expected.Put64(200,before.U64(128));return SameRequestedState(expected);',
        'CmdRemoteReader.Add(before.U64(248),2)',
        'WriteProcessMemory(process.Value,Pointer(address),new byte[]{value},(UIntPtr)1,out actual)',
        'FlushInstructionCache(process.Value,Pointer(address),(UIntPtr)1)',
        'DuplicateHandle(process.Value,Pointer(target),GetCurrentProcess(),out output,0,false,2)',
        'duplicate=ok?new CmdDuplicate(output):default(CmdDuplicate);',
        'public override bool CloseImage(CmdImageFile file) { return Result(CloseHandle(file.Value)); }',
        'public override bool CloseDuplicate(CmdDuplicate file) { return Result(CloseHandle(file.Value)); }',
        'TerminateProcess(process.Value,91)', 'if(address==0 || delta>UInt64.MaxValue-address)',
        'if(count<=0 || count>1048576-BytesRead)', 'BytesRead+=count;', 'actual!=(ulong)count',
        'sections>=1 && sections<=96', 'CmdU16(header,4)==0x8664', 'CmdU16(optional,0)==0x20b',
        'module.ExportSize<=524288', 'functions<=8192 && names>0 && names<=8192',
        'Require(result[target]==0);', '!(rva>=module.ExportRva && rva-module.ExportRva<module.ExportSize)',
        '''public bool SameRequested(CmdDebugContext other) {
            if(other==null || U32(48)!=0x00100003 || other.U32(48)!=0x00100003 ||
                CmdU16(Raw,56)!=CmdU16(other.Raw,56) || CmdU16(Raw,66)!=CmdU16(other.Raw,66) || U32(68)!=other.U32(68)) return false;
            for(int offset=120;offset<=248;offset+=8) if(U64(offset)!=other.U64(offset)) return false;
            return true;
        }''',
        '''public long RequestedMismatchMask(CmdDebugContext other) {
            if(other==null) return -1;
            long mask=0;
            if(U32(48)!=0x00100003 || other.U32(48)!=0x00100003) mask|=1L;
            if(CmdU16(Raw,56)!=CmdU16(other.Raw,56)) mask|=1L<<1;
            if(CmdU16(Raw,66)!=CmdU16(other.Raw,66)) mask|=1L<<2;
            if(U32(68)!=other.U32(68)) mask|=1L<<3;
            for(int offset=120;offset<=248;offset+=8)
                if(U64(offset)!=other.U64(offset)) mask|=1L<<(4+(offset-120)/8);
            return mask;
        }''',
        '''public CmdDebugContext(byte[] bytes) {
            if(bytes==null || bytes.Length!=1232) throw new CmdDebugFault("context_failed","none",0);
            Raw=(byte[])bytes.Clone();
        }''',
        'public CmdDebugContext Copy() { return new CmdDebugContext(Raw); }',
        '''public CmdDebugContext WithRipTf(ulong rip,bool tf) {
            var result=Copy();result.Put64(248,rip);
            result.Put32(68,tf?U32(68)|0x100U:U32(68)&~0x100U);return result;
        }''',
        '''public bool SameRequestedState(CmdDebugContext other) {
            if(SameRequested(other)) return true;
            return RequestedMismatchMask(other)==8L && (U32(68)^other.U32(68))==0x00000002U;
        }''',
        '''public bool MatchesAfterMov(CmdDebugContext before) {
            var expected=before.WithRipTf(CmdRemoteReader.Add(before.U64(248),2),(U32(68)&0x100)!=0);
            expected.Put64(200,before.U64(128));return SameRequestedState(expected);
        }''',
        '''public override bool GetContext(CmdBorrowedThread thread,out CmdDebugContext context) {
            context=null;var initial=new CmdDebugContext();
            using(var buffer=new CmdContextBuffer()) {
                Marshal.Copy(initial.Raw,0,buffer.Aligned,1232);
                if(!Result(GetThreadContext(thread.Value,buffer.Aligned))) return false;
                Marshal.Copy(buffer.Aligned,initial.Raw,0,1232);context=initial;return true;
            }
        }''',
        '''public override bool SetContext(CmdBorrowedThread thread,CmdDebugContext context) {
            if(context.U32(48)!=0x00100003) throw new CmdDebugFault("context_failed","SetThreadContext",0);
            using(var buffer=new CmdContextBuffer()) {
                Marshal.Copy(context.Raw,0,buffer.Aligned,1232);return Result(SetThreadContext(thread.Value,buffer.Aligned));
            }
        }''',
    ),
    NAMES[1]: (
        'subject.OwnershipCertain && subject.ProfileCreated && receipt.Created && receipt.Assigned && !receipt.Resumed',
        'receipt.CreationFlags==0x08080404 && receipt.Kind=="cmd"', 'machine==0 && native==0x8664',
        'N("attach_attempted",1);MayCallOriginalCleanup=false;attachUnknown=true;',
        'bool ok=api.Attach(subject.Process.pid);attachUnknown=false;',
        'if(pending==null || continueAttempted)', 'continueAttempted=true;',
        'Require(api.Continue(pending,disposition),"native_failed","ContinueDebugEvent");pending=null;',
        'e.Pid!=subject.Process.pid', '(cleanup?512:4096)', 'Math.Min(remaining,100)',
        'threads.Count>=32', 'modules.Count>=128', 'N("entry_hits")>=128', 'N("write_attempts")>=264',
        'if(t.IncrementOwned || t.ReleaseAttempted)', 't.ReleaseAttempted=true;',
        'previous==t.Previous+1', 'peer.Handle.Tid!=owner',
        'N("entries_ready_before_resume",1);ready=true;', 'Require(previous==1,"resume_failed","ResumeThread");',
        'p.Uncertain=true;', 'count==1', 'p.Active=arm;p.Uncertain=false;',
        '!c.MatchesAfterMov(beforeStep)', 'PatchByte(stepping,true);SetContext(t,c.WithRipTf(c.U64(248),false));ReleasePeers();',
        'if((c.U32(68)&0x100)!=0)', 'if(!attachBreak)', 'c.U64(152)!=CmdRemoteReader.Add(entryRsp,8)',
        'length>8192 || length>CmdU16(name,2)', 'new UnicodeEncoding(false,false,true)',
        r'String.Equals(text,@"\??\"+subject.Workspace+@"\direct.cmd",',
        'foreach(Patch p in patches) PatchByte(p,false);',
        'if(status==0x103) {I("result","observed_pending");Fault("pending_io");}',
        'uint status=(uint)(c.U64(120)&UInt32.MaxValue);', '(status&0x80000000)!=0',
        'protectedHandles.ContainsKey(candidate.Value)', 'api.CloseDuplicate(candidate)',
        'Continue(0x10002);N("exit_event_continued",1);', 'Math.Min(started+35000,api.NowMilliseconds+5000)',
        'Require(exit==debugExit,"target_identity","GetExitCodeProcess");BindIdentity(false);',
        '(first || value==creation)', 'identityUncertain=true;', 'identityUncertain=false;',
        'if(pending!=null && pending.Code==5) {Exit(true);return;}',
        'if(terminationAttempted) {Retain();return;}terminationAttempted=true;',
        'if(attachUnknown || identityUncertain || (pending!=null && (pending.Pid!=subject.Process.pid || continueAttempted)))',
        'waitUnknown=true;bool ok=api.Wait(', '!terminated || waitUnknown',
        'retainedCmdDebug=this;', 'r.Exit==1', 'pilot_cmd_observation_raw_complete',
        'pilot_cmd_observation_stdout_matches', 'pilot_cmd_observation_stderr_empty',
        '!session.MayCallOriginalCleanup || session.Failed', '!PilotNumber(r,"cmd_debug_pair_complete",1)',
        'row.Fatal=true;row.PositivePassed=false;', 'throw new InvalidOperationException("cmd_debug_incomplete");',
        'SetContext(t,c.WithRipTf(returnPatch.Address,(c.U32(68)&0x100)!=0));',
        'enum ImageOwnership {None,Owned,Attempted,Closed,Unknown}',
        'if(e==null || e.Pid!=subject.Process.pid) Fault("event_protocol");AdoptImage(e);if(e.Tid==0) Fault("event_protocol");',
        'pendingImage=e.File;pendingImageState=ImageOwnership.Unknown;',
        '(e.Code==3 && (e.File==e.Process || e.File==e.Thread))) Fault("close_uncertain");pendingImageState=ImageOwnership.Owned;',
        'if(value!=pendingImage) Fault("close_uncertain");',
        'if(pendingImageState!=ImageOwnership.Owned) Fault("close_uncertain");',
        'pendingImageState=ImageOwnership.Attempted;Require(api.CloseImage(new CmdImageFile(value)),"close_uncertain","CloseHandle");pendingImageState=ImageOwnership.Closed;',
        'if(pendingImageState!=ImageOwnership.None && pendingImageState!=ImageOwnership.Closed) Fault("close_uncertain");continueAttempted=true;',
        'if(pending!=null) {if(pending.Code==3 || pending.Code==6) CloseImage(pending.File);Continue(pending.Code==1?0x80010001u:0x10002u);}',
        'if(N("exit_event_seen")==1 || pendingImageState==ImageOwnership.Attempted || pendingImageState==ImageOwnership.Unknown) {Retain();return;}',
        'I("protocol","own-child-open-v4");',
        '''void SetContext(ThreadSlot t,CmdDebugContext c) {
            N("context_mismatch_mask",-1);
            N("eflags_difference_mask",-1);
            Require(api.SetContext(t.Handle,c),"context_failed","SetThreadContext");
            CmdDebugContext actual;
            Require(api.GetContext(t.Handle,out actual),"context_get_failed","GetThreadContext");
            if(actual==null) Fault("context_roundtrip_unavailable");
            long fields=actual.RequestedMismatchMask(c);
            uint flags=actual.U32(68)^c.U32(68);
            N("context_mismatch_mask",fields);
            N("eflags_difference_mask",(long)flags);
            if(!actual.SameRequestedState(c)) Fault("context_roundtrip_mismatch");
        }''',
    ),
    NAMES[2]: ('RunCmdDebugContractTests()', 'MOV permits fresh R10=RCX and exact RIP delta',
               'never close original, borrowed or target handles', 'fatal precedes classifier and resolution',
               'pending never reads output or IO_STATUS_BLOCK', 'CmdTestFaultSweep()',
               'return TF preservation is exercised', 'false or exceptional image close is never retried',
               'uncertain early image close retains before any continuation', 'CmdTestContextContracts();',
        'Instrument();var fresh=contexts[thread.Value];var allowed=fresh.WithRipTf(context.U64(248),(context.U32(68)&0x100)!=0);',
        'Require(Pending!=null && context.SameRequested(allowed),"fresh context preserves every other requested register");',
    ),
    NAMES[3]: ('CmdTestContextContracts()', 'all 21 requested fields have distinct mismatch bits',
               'mask zero iff unchanged SameRequested accepts', 'equally invalid flags still set bit zero',
               'stale mask cleared before every Set', 'failed Set has no readback',
               'successful Set has exactly one immediate Get', 'first failure reason API error and mask survive cleanup',
               'context diagnostics add no native calls', 'context diagnostics preserve exact native call order',
               'standalone context failure retains its original reason', 'post MOV mismatch retains existing context_failed route',
               'fixed baseline context call counts remain unchanged',
               'stale EFLAGS XOR cleared before every Set',
               'EFLAGS XOR remains unavailable until immediate comparison',
               'all32 positions are tested; later exact comparison replaces admissible bit1 diagnostics',
               'XOR compares requested TF-set and TF-clear contexts',
               'bit31 is positive rather than sign-extended', 'allbits is the complete uint32 range',
               'field and EFLAGS diagnostics have identical availability',
               'EFLAGS field bit is set iff the XOR is nonzero',
               'all non-EFLAGS mismatches leave XOR zero while still failing closed',
               'both initial and subsequent Set reset the previous available EFLAGS XOR',
               'earlier exact comparison and failed cleanup retain the first XOR diagnosis',
               'long fields=otherFields|(difference==0?0L:8L);',
        'CmdTestRequestedState();CmdTestBit1Routes();CmdTestMovState();CmdTestBit1ResetAndFirstFailure();',
        'state rejects null and accepts raw equality',
        'both directions admit only bit1; all31 other bits alone and with bit1 fail including TF and highbit',
        'state acceptance never weakens raw comparison or diagnostic identity',
        'every other requested field fails alone and with bit1',
        'either invalid ContextFlags operand fails with or without bit1',
        'equally invalid ContextFlags never qualify',
        'request construction changes only RIP and owned TF, preserving bit1',
        'every requested Set buffer is byte-identical to baseline',
        'fresh return preserves both bit1 representations and TF states',
        'actual immediate requests set then clear TF without changing bit1',
        'MOV final comparison admits bit1 and preserves preexisting observed-TF construction only',
        'post-MOV injection exercises the separate final comparison call site',
        'MOV comparison never overwrites latest immediate raw diagnostics',
        'both diagnostics reset after the earlier admissible raw difference',
        'cleanup cannot turn first mismatch into an admitted comparison',
    ),
}
