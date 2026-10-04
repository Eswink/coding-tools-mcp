// Pure context-mask, EFLAGS XOR and reason-routing contracts; all operations use the existing fake.
using System;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    static int[] CmdTestContextOffsets() {
        return new int[]{48,56,66,68,120,128,136,144,152,160,168,176,184,192,200,208,216,224,232,240,248};
    }
    static void CmdTestMutateContext(CmdDebugContext context,long mask) {
        int[] offsets=CmdTestContextOffsets();
        for(int bit=0;bit<offsets.Length;bit++) if((mask&(1L<<bit))!=0) context.Raw[offsets[bit]]^=1;
    }
    sealed class CmdContextFake {
        public string Mode="none";
        public int AtSet=1,AtOrdinaryGet=1,ReportedError=87,Error,Sets,Readbacks,OrdinaryGets,FailureCall=-1;
        public long MismatchMask=1;
        public uint EflagsDifference;
        public bool SawPriorZero,SawPriorBit1,PriorBit1;
        public readonly List<int> SetCalls=new List<int>(),ReadbackCalls=new List<int>();
        public readonly List<long> MasksBeforeSet=new List<long>(),EflagsBeforeSet=new List<long>();
        public readonly List<uint> RequestedEflags=new List<uint>();
        public readonly List<byte[]> RequestedBytes=new List<byte[]>(),SourceBytes=new List<byte[]>();
        public readonly List<CmdDebugContext> SourceContexts=new List<CmdDebugContext>();
        bool awaitingReadback;
        public bool Set(CmdFakeApi fake) {
            Sets++;SetCalls.Add(fake.Calls.Count-1);MasksBeforeSet.Add(fake.Number("context_mismatch_mask"));Error=0;
            EflagsBeforeSet.Add(fake.Number("eflags_difference_mask"));
            CmdTestAssert(fake.Number("context_mismatch_mask")==-1,"stale mask cleared before every Set");
            CmdTestAssert(fake.Number("eflags_difference_mask")==-1,"stale EFLAGS XOR cleared before every Set");
            if(Sets==AtSet && (Mode=="set_false" || Mode=="set_throw")) {
                FailureCall=fake.Calls.Count-1;Error=ReportedError;
                if(Mode=="set_throw") throw new InvalidOperationException("secret context setter");
                return false;
            }
            awaitingReadback=true;return true;
        }
        public bool Get(CmdFakeApi fake,ref CmdDebugContext context) {
            Error=0;
            if(!awaitingReadback) {
                OrdinaryGets++;SourceContexts.Add(context);SourceBytes.Add((byte[])context.Raw.Clone());
                if(fake.Number("context_mismatch_mask")==8 && fake.Number("eflags_difference_mask")==2) SawPriorBit1=true;
                if(Sets>0 && fake.Number("context_mismatch_mask")==0) {
                    SawPriorZero=true;CmdTestAssert(fake.Number("eflags_difference_mask")==0,"prior exact roundtrip has both diagnostics zero");
                }
                if(Mode=="ordinary_false" && OrdinaryGets==AtOrdinaryGet) {
                    FailureCall=fake.Calls.Count-1;Error=ReportedError;return false;
                }
                return true;
            }
            awaitingReadback=false;Readbacks++;ReadbackCalls.Add(fake.Calls.Count-1);
            CmdTestAssert(fake.Number("context_mismatch_mask")==-1,"mask remains unavailable until immediate comparison");
            CmdTestAssert(fake.Number("eflags_difference_mask")==-1,"EFLAGS XOR remains unavailable until immediate comparison");
            RequestedEflags.Add(context.U32(68));RequestedBytes.Add((byte[])context.Raw.Clone());
            if(PriorBit1 && Sets<AtSet) {CmdTestPut(context.Raw,68,context.U32(68)^2U,4);return true;}
            if(Sets!=AtSet || Mode=="none" || Mode=="ordinary_false") return true;
            if(Mode=="eflags") {
                CmdTestAssert((MismatchMask&8)==0,"independent field injection excludes the EFLAGS field");
                CmdTestMutateContext(context,MismatchMask);
                CmdTestPut(context.Raw,68,context.U32(68)^EflagsDifference,4);
                if(MismatchMask!=0 || (EflagsDifference!=0 && EflagsDifference!=2U)) FailureCall=fake.Calls.Count-1;
                return true;
            }
            FailureCall=fake.Calls.Count-1;Error=ReportedError;
            if(Mode=="get_false") return false;
            if(Mode=="get_throw") throw new InvalidOperationException("secret context getter",new Exception("secret inner"));
            if(Mode=="null") {context=null;return true;}
            CmdTestAssert(Mode=="mismatch","finite context scenario");
            CmdTestMutateContext(context,MismatchMask);return true;
        }
    }
    static void CmdTestContextMasks() {
        var requested=CmdTestContext(CmdFakeApi.Ntdll+0x1001,CmdFakeApi.Stack);
        var exact=requested.Copy();
        CmdTestAssert(requested.RequestedMismatchMask(null)==-1 && !requested.SameRequested(null),"null context is unavailable rather than a completed comparison");
        CmdTestAssert(requested.RequestedMismatchMask(exact)==0 && requested.SameRequested(exact),"unchanged requested context has zero mismatch mask");
        int[] offsets=CmdTestContextOffsets();long combined=0;
        CmdTestAssert(offsets.Length==21,"all 21 requested fields have distinct mismatch bits");
        for(int bit=0;bit<offsets.Length;bit++) {
            int width=bit==0 || bit==3?4:(bit==1 || bit==2?2:8);
            foreach(int byteIndex in new int[]{0,width-1}) {
                var changed=requested.Copy();changed.Raw[offsets[bit]+byteIndex]^=0x80;
                long expected=1L<<bit;
                CmdTestAssert(requested.RequestedMismatchMask(changed)==expected && changed.RequestedMismatchMask(requested)==expected,
                    "each requested field maps exactly to its documented bit in either direction");
                CmdTestAssert((requested.RequestedMismatchMask(changed)==0)==requested.SameRequested(changed),
                    "mask zero iff unchanged SameRequested accepts");
            }
            combined|=1L<<bit;
        }
        var all=requested.Copy();CmdTestMutateContext(all,combined);
        CmdTestAssert(combined==0x1fffff && requested.RequestedMismatchMask(all)==combined,"all requested mismatch bits accumulate without truncation");
        foreach(long mask in new long[]{(1L<<1)|(1L<<5)|(1L<<20),(1L<<3)|(1L<<14),0}) {
            var changed=requested.Copy();CmdTestMutateContext(changed,mask);
            CmdTestAssert(requested.RequestedMismatchMask(changed)==mask && requested.SameRequested(changed)==(mask==0),
                "multiple independent fields preserve exact equivalence");
        }
        foreach(uint flags in new uint[]{0,0x00100002,0x00100007,UInt32.MaxValue}) {
            var invalid=requested.Copy();CmdTestPut(invalid.Raw,48,flags,4);
            CmdTestAssert(invalid.RequestedMismatchMask(invalid.Copy())==1 && !invalid.SameRequested(invalid.Copy()),
                "equally invalid flags still set bit zero");
            CmdTestAssert(invalid.RequestedMismatchMask(requested)==1 && requested.RequestedMismatchMask(invalid)==1,
                "either invalid flags operand sets bit zero");
        }
        var ignored=requested.Copy();
        foreach(int offset in new int[]{0,47,52,55,58,60,62,64,72,112,119,256,512,1231}) ignored.Raw[offset]^=0xff;
        CmdTestAssert(requested.RequestedMismatchMask(ignored)==0 && requested.SameRequested(ignored),
            "unrequested fields remain outside the existing acceptance predicate");
    }
    static int CmdTestCallCount(CmdFakeApi fake,string name) {
        int count=0;foreach(string call in fake.Calls) if(call==name) count++;return count;
    }
    static void CmdTestContextCallOrder(CmdFakeApi fake,CmdContextFake scenario) {
        CmdTestAssert(CmdTestCallCount(fake,"SetThreadContext")==scenario.Sets,"no untracked context setter calls");
        CmdTestAssert(CmdTestCallCount(fake,"GetThreadContext")==scenario.Readbacks+scenario.OrdinaryGets,"no extra native context getter calls");
        for(int i=0;i<scenario.SetCalls.Count;i++) {
            int call=scenario.SetCalls[i];
            bool setFailed=i+1==scenario.AtSet && (scenario.Mode=="set_false" || scenario.Mode=="set_throw");
            if(setFailed) CmdTestAssert(call+1>=fake.Calls.Count || fake.Calls[call+1]!="GetThreadContext","failed Set has no readback");
            else CmdTestAssert(i<scenario.ReadbackCalls.Count && scenario.ReadbackCalls[i]==call+1 && fake.Calls[call+1]=="GetThreadContext",
                "successful Set has exactly one immediate Get");
        }
        if(scenario.FailureCall<0) return;
        for(int i=scenario.FailureCall+1;i<fake.Calls.Count;i++) {
            string call=fake.Calls[i];
            CmdTestAssert(call!="GetThreadContext" && call!="SetThreadContext" && call!="ReadProcessMemory" &&
                call!="WriteProcessMemory" && call!="FlushInstructionCache" && call!="SuspendThread" && call!="ResumeThread.peer",
                "failed roundtrip never retries or performs later instrumentation");
        }
    }
    static void CmdTestContextOutcome(CmdFakeApi fake,string reason,string api,long error,long mask) {
        CmdTestAssert(fake.Identity("protocol")=="own-child-open-v4","context reason split uses strict v4 protocol");
        CmdTestAssert(fake.Identity("error")==reason && fake.Identity("error_api")==api && fake.Number("native_error")==error &&
            fake.Number("context_mismatch_mask")==mask,"first failure reason API error and mask survive cleanup");
        long difference=mask<0?-1:(mask&8)==0?0:fake.ContextCase.Mode=="eflags"?(long)fake.ContextCase.EflagsDifference:1;
        CmdTestEflagsValue(fake,difference);
        CmdTestAssert(fake.Number("pair_complete")==0,"context failure never accepts a paired operation");
        CmdTestContextCallOrder(fake,fake.ContextCase);
    }
    static CmdFakeApi CmdTestContextFailure(string mode,int error,int atSet,long mismatchMask) {
        var fake=new CmdFakeApi(false,false,false);
        fake.ContextCase=new CmdContextFake {Mode=mode,ReportedError=error,AtSet=atSet,MismatchMask=mismatchMask};
        return fake;
    }
    static void CmdTestContextRoutes() {
        for(int bit=0;bit<21;bit++) {
            long mask=1L<<bit;var fake=CmdTestContextFailure("mismatch",87,1,mask);
            CmdTestRun(fake,true,"each requested field mismatch fails closed through the same session");
            CmdTestContextOutcome(fake,"context_roundtrip_mismatch","none",0,mask);
            CmdTestAssert(fake.ContextCase.Sets==1 && fake.ContextCase.Readbacks==1,"single mismatch has one Set and one readback");
        }
        foreach(long mask in new long[]{(1L<<1)|(1L<<5)|(1L<<20),0x1fffff}) {
            var fake=CmdTestContextFailure("mismatch",87,1,mask);CmdTestRun(fake,true,"multifield mismatch fails closed");
            CmdTestContextOutcome(fake,"context_roundtrip_mismatch","none",0,mask);
        }
        foreach(int error in new int[]{0,5,87}) foreach(string mode in new string[]{"set_false","get_false","null","set_throw","get_throw"}) {
            var fake=CmdTestContextFailure(mode,error,1,0);CmdTestRun(fake,true,"context native result and managed exception routes");
            string reason=mode=="set_false"?"context_failed":mode=="get_false"?"context_get_failed":
                mode=="null"?"context_roundtrip_unavailable":"internal_exception";
            string api=mode=="set_false"?"SetThreadContext":mode=="get_false"?"GetThreadContext":"none";
            long nativeError=mode=="set_false" || mode=="get_false"?error:0;
            CmdTestContextOutcome(fake,reason,api,nativeError,-1);
            CmdTestAssert(fake.ContextCase.Sets==1 && fake.ContextCase.Readbacks==(mode.StartsWith("set_",StringComparison.Ordinal)?0:1),
                "false null and exceptional routes preserve bounded context calls");
        }
        foreach(int atGet in new int[]{1,3}) foreach(int error in new int[]{0,87}) {
            var fake=CmdTestContextFailure("ordinary_false",error,1,0);fake.ContextCase.AtOrdinaryGet=atGet;
            CmdTestRun(fake,true,"standalone context failure retains its original reason");
            CmdTestContextOutcome(fake,"context_failed","GetThreadContext",error,atGet==1?-1:0);
            CmdTestAssert(fake.ContextCase.Sets==(atGet==1?0:1),"standalone Get is never treated as a new Set roundtrip");
        }
        var step=new CmdFakeApi(true,false,false);step.ContextCase=new CmdContextFake();step.WrongStepR10=true;
        CmdTestRun(step,true,"post MOV mismatch retains existing context_failed route");
        CmdTestContextOutcome(step,"context_failed","none",0,0);
        CmdTestAssert(step.ContextCase.Sets==1 && step.ContextCase.Readbacks==1,"post MOV comparison adds no context call");
    }
    static void CmdTestContextResetAndFirstFailure() {
        foreach(string mode in new string[]{"set_false","get_false","null","mismatch","set_throw","get_throw"}) {
            var fake=CmdTestContextFailure(mode,87,2,1L<<20);CmdTestRun(fake,true,"later roundtrip cannot reuse an earlier zero mask");
            string reason=mode=="set_false"?"context_failed":mode=="get_false"?"context_get_failed":
                mode=="null"?"context_roundtrip_unavailable":mode=="mismatch"?"context_roundtrip_mismatch":"internal_exception";
            string api=mode=="set_false"?"SetThreadContext":mode=="get_false"?"GetThreadContext":"none";
            CmdTestContextOutcome(fake,reason,api,api=="none"?0:87,mode=="mismatch"?1L<<20:-1);
            CmdTestAssert(fake.ContextCase.SawPriorZero && fake.ContextCase.Sets==2,"prior successful mask zero is exercised before reset");
            CmdTestAssert(fake.ContextCase.MasksBeforeSet.Count==2 && fake.ContextCase.MasksBeforeSet[0]==-1 &&
                fake.ContextCase.MasksBeforeSet[1]==-1,"both initial and subsequent Set reset unavailable mask");
        }
        foreach(bool cleanupThrows in new bool[]{false,true}) foreach(string mode in new string[]{"get_false","null","mismatch"}) {
            var fake=CmdTestContextFailure(mode,87,1,(1L<<3)|(1L<<14));
            fake.FailName="TerminateProcess";fake.ThrowFault=cleanupThrows;
            var session=CmdTestRun(fake,true,"cleanup failure cannot replace first context failure");
            string reason=mode=="get_false"?"context_get_failed":mode=="null"?"context_roundtrip_unavailable":"context_roundtrip_mismatch";
            CmdTestContextOutcome(fake,reason,mode=="get_false"?"GetThreadContext":"none",mode=="get_false"?87:0,
                mode=="mismatch"?(1L<<3)|(1L<<14):-1);
            CmdTestAssert(fake.TerminateCount==1 && !session.MayCallOriginalCleanup && fake.Identity("cleanup")=="retained_fatal",
                "failed cleanup retains once without rewriting first context diagnostic");
        }
    }
    static void CmdTestContextContracts() {
        CmdTestContextMasks();
        foreach(bool step in new bool[]{false,true}) foreach(bool success in new bool[]{false,true}) foreach(bool open in new bool[]{false,true}) {
            var baseline=new CmdFakeApi(step,success,open);CmdTestRun(baseline,false,"unchanged context route baseline");
            var fake=new CmdFakeApi(step,success,open);fake.ContextCase=new CmdContextFake();
            CmdTestRun(fake,false,"exact requested context remains accepted");
            CmdTestAssert(fake.Number("context_mismatch_mask")==0 && fake.Identity("error")=="none" && fake.Number("pair_complete")==1,
                "zero mask preserves existing acceptance");
            CmdTestEflagsValue(fake,0);
            CmdTestAssert(fake.Calls.Count==baseline.Calls.Count,"context diagnostics add no native calls");
            for(int i=0;i<baseline.Calls.Count;i++) CmdTestAssert(fake.Calls[i]==baseline.Calls[i],"context diagnostics preserve exact native call order");
            CmdTestAssert(fake.ContextCase.Sets==(step?4:2) && fake.ContextCase.Readbacks==fake.ContextCase.Sets,
                "entry step return routes each perform one immediate readback");
            CmdTestAssert(fake.ContextCase.OrdinaryGets==(step?5:3) && CmdTestCallCount(fake,"GetThreadContext")== (step?9:5),
                "fixed baseline context call counts remain unchanged");
            CmdTestContextCallOrder(fake,fake.ContextCase);
        }
        CmdTestContextRoutes();CmdTestContextResetAndFirstFailure();CmdTestEflagsContracts();
    }

    static void CmdTestEflagsValue(CmdFakeApi fake,long expected) {
        long fields=fake.Number("context_mismatch_mask"),difference=fake.Number("eflags_difference_mask");
        CmdTestAssert(difference==expected && difference>=-1 && difference<=UInt32.MaxValue,"EFLAGS XOR is exact unsigned32 widened to long or unavailable");
        CmdTestAssert((fields==-1)==(difference==-1),"field and EFLAGS diagnostics have identical availability");
        if(fields>=0) CmdTestAssert(((fields&8)!=0)==(difference!=0),"EFLAGS field bit is set iff the XOR is nonzero");
    }
    static CmdFakeApi CmdTestEflagsRoute(bool step,int atSet,uint difference,long otherFields,uint initialFlags=0x202U,uint returnTf=0) {
        var fake=new CmdFakeApi(step,false,false);CmdTestEventFlags(fake,initialFlags,returnTf);
        fake.ContextCase=new CmdContextFake {Mode="eflags",AtSet=atSet,MismatchMask=otherFields,EflagsDifference=difference};
        bool failed=(difference!=0 && difference!=2U) || otherFields!=0;
        CmdTestRun(fake,failed,"only sole reserved bit1 difference is admissible");
        long fields=otherFields|(difference==0?0L:8L);
        if(failed) CmdTestContextOutcome(fake,"context_roundtrip_mismatch","none",0,fields);
        else {
            bool last=atSet==(step?4:2);CmdTestEflagsValue(fake,last?difference:0);
            CmdTestAssert(fake.Number("context_mismatch_mask")== (last?fields:0),"diagnostics retain the latest immediate comparison");
            CmdTestAssert(difference!=2U || last || fake.ContextCase.SawPriorBit1,"admissible raw8 XOR2 is visible before a later comparison");
            CmdTestAssert(fake.Identity("error")=="none" && fake.Number("pair_complete")==1,"admissible difference preserves paired baseline");
            CmdTestContextCallOrder(fake,fake.ContextCase);
        }
        CmdTestAssert(fake.ContextCase.Sets==(failed?atSet:step?4:2) && fake.ContextCase.Readbacks==fake.ContextCase.Sets,
            "each reached Set retains exactly one immediate readback");
        return fake;
    }
    static void CmdTestEflagsBitsAndRoutes() {
        foreach(int atSet in new int[]{1,2}) {
            for(int bit=0;bit<32;bit++) {
                uint difference=1U<<bit;var fake=CmdTestEflagsRoute(true,atSet,difference,0);
                CmdTestAssert(fake.Number("eflags_difference_mask")== (bit==1?0:1L<<bit),"all32 positions are tested; later exact comparison replaces admissible bit1 diagnostics");
                uint requested=fake.ContextCase.RequestedEflags[atSet-1];
                CmdTestAssert(requested==(atSet==1?0x302U:0x202U),"XOR compares requested TF-set and TF-clear contexts");
                if(bit==8) CmdTestAssert(((requested^difference)&0x100)==(atSet==1?0U:0x100U),
                    "a missing requested TF and an unexpected retained TF both fail closed");
                if(bit==31) CmdTestAssert(fake.Number("eflags_difference_mask")==2147483648L,"bit31 is positive rather than sign-extended");
            }
            foreach(uint difference in new uint[]{0,0x80000100U,0x80010201U,UInt32.MaxValue}) {
                var fake=CmdTestEflagsRoute(true,atSet,difference,0);
                CmdTestAssert(fake.Number("eflags_difference_mask")==difference,"zero multiple and all EFLAGS bits preserve the exact XOR");
                if(difference==UInt32.MaxValue) CmdTestAssert(fake.Number("eflags_difference_mask")==4294967295L,"allbits is the complete uint32 range");
            }
        }
        CmdTestEflagsRoute(false,1,0x80000100U,(1L<<14)|(1L<<20));
        var nonflags=CmdTestEflagsRoute(false,1,0,0x1fffff&~8L);
        CmdTestAssert(nonflags.Number("context_mismatch_mask")== (0x1fffff&~8L) && nonflags.Number("eflags_difference_mask")==0,
            "all non-EFLAGS mismatches leave XOR zero while still failing closed");
        foreach(uint flags in new uint[]{0x202U,0x302U}) {
            var fake=new CmdFakeApi(false,false,false);fake.ContextCase=new CmdContextFake();
            CmdTestPut(fake.EventContexts[fake.Events[4]].Raw,68,flags,4);
            CmdTestRun(fake,false,"fresh return TF remains independent of XOR diagnostics");
            CmdTestEflagsValue(fake,0);
            CmdTestAssert(fake.ReturnFlags==flags && fake.ContextCase.RequestedEflags[1]==flags,
                "return correction preserves both clear and preexisting set TF");
            CmdTestContextCallOrder(fake,fake.ContextCase);
        }
    }
    static void CmdTestEflagsResetAndFirstFailure() {
        foreach(int error in new int[]{0,5,87}) foreach(string mode in new string[]{"set_false","get_false","null","set_throw","get_throw"}) {
            var fake=CmdTestContextFailure(mode,error,2,0);CmdTestRun(fake,true,"later native null or managed failure cannot reuse prior XOR zero");
            string reason=mode=="set_false"?"context_failed":mode=="get_false"?"context_get_failed":
                mode=="null"?"context_roundtrip_unavailable":"internal_exception";
            string api=mode=="set_false"?"SetThreadContext":mode=="get_false"?"GetThreadContext":"none";
            CmdTestContextOutcome(fake,reason,api,api=="none"?0:error,-1);
            CmdTestAssert(fake.ContextCase.SawPriorZero && fake.ContextCase.Sets==2 &&
                fake.ContextCase.EflagsBeforeSet.Count==2 && fake.ContextCase.EflagsBeforeSet[0]==-1 && fake.ContextCase.EflagsBeforeSet[1]==-1,
                "both initial and subsequent Set reset the previous available EFLAGS XOR");
        }
        foreach(bool cleanupThrows in new bool[]{false,true}) foreach(uint difference in new uint[]{0x100U,0x80000000U,UInt32.MaxValue}) {
            var fake=new CmdFakeApi(true,false,false);
            fake.ContextCase=new CmdContextFake {Mode="eflags",AtSet=2,MismatchMask=1L<<14,EflagsDifference=difference};
            fake.FailName="TerminateProcess";fake.ThrowFault=cleanupThrows;
            var session=CmdTestRun(fake,true,"cleanup cannot overwrite the first EFLAGS mismatch or error");
            CmdTestContextOutcome(fake,"context_roundtrip_mismatch","none",0,(1L<<14)|8);
            CmdTestAssert(fake.ContextCase.SawPriorZero && fake.TerminateCount==1 && !session.MayCallOriginalCleanup &&
                fake.Identity("cleanup")=="retained_fatal","earlier exact comparison and failed cleanup retain the first XOR diagnosis");
        }
    }
    static void CmdTestEflagsContracts() {
        var initial=new CmdFakeApi(false,false,false);var session=new CmdDebugSession(initial.Subject,initial);
        CmdTestEflagsValue(initial,-1);
        CmdTestAssert(initial.Calls.Count==0 && !session.Failed,"both diagnostics initialize unavailable without a native call");
        CmdTestEflagsBitsAndRoutes();CmdTestEflagsResetAndFirstFailure();
        CmdTestRequestedState();CmdTestBit1Routes();CmdTestMovState();CmdTestBit1ResetAndFirstFailure();
    }

    static void CmdTestBytesEqual(byte[] expected,byte[] actual,string label) {
        CmdTestAssert(expected.Length==actual.Length,label);
        for(int i=0;i<expected.Length;i++) CmdTestAssert(expected[i]==actual[i],label);
    }
    static void CmdTestEventFlags(CmdFakeApi fake,uint flags,uint returnTf) {
        foreach(var pair in fake.EventContexts) CmdTestPut(pair.Value.Raw,68,flags,4);
        CmdTestPut(fake.EventContexts[fake.Events[fake.Events.Count-2]].Raw,68,flags|returnTf,4);
    }
    static void CmdTestRequestedState() {
        foreach(uint flags in new uint[]{0x200U,0x202U}) {
            var requested=CmdTestContext(CmdFakeApi.Ntdll+0x1001,CmdFakeApi.Stack);CmdTestPut(requested.Raw,68,flags,4);
            var saved=(byte[])requested.Raw.Clone();
            CmdTestAssert(!requested.SameRequestedState(null) && requested.SameRequestedState(requested.Copy()),"state rejects null and accepts raw equality");
            for(int bit=0;bit<32;bit++) foreach(uint reserved in new uint[]{0,2}) {
                uint difference=(1U<<bit)|reserved;var actual=requested.Copy();CmdTestPut(actual.Raw,68,flags^difference,4);
                var actualSaved=(byte[])actual.Raw.Clone();bool accepted=difference==2U;
                CmdTestAssert(requested.SameRequestedState(actual)==accepted && actual.SameRequestedState(requested)==accepted,
                    "both directions admit only bit1; all31 other bits alone and with bit1 fail including TF and highbit");
                CmdTestAssert(!requested.SameRequested(actual) && requested.RequestedMismatchMask(actual)==8 && (requested.U32(68)^actual.U32(68))==difference,
                    "state acceptance never weakens raw comparison or diagnostic identity");
                CmdTestBytesEqual(saved,requested.Raw,"comparison preserves every requested byte");
                CmdTestBytesEqual(actualSaved,actual.Raw,"comparison preserves every actual byte");
            }
            foreach(bool bit1 in new bool[]{false,true}) for(int bit=0;bit<21;bit++) if(bit!=3) {
                var actual=requested.Copy();CmdTestMutateContext(actual,1L<<bit);if(bit1) actual.Raw[68]^=2;
                CmdTestAssert(!requested.SameRequestedState(actual) && !actual.SameRequestedState(requested),"every other requested field fails alone and with bit1");
            }
            foreach(uint invalid in new uint[]{0,0x00100002,0x00100007,UInt32.MaxValue}) foreach(bool bit1 in new bool[]{false,true}) {
                var actual=requested.Copy();CmdTestPut(actual.Raw,48,invalid,4);if(bit1) actual.Raw[68]^=2;
                CmdTestAssert(!requested.SameRequestedState(actual) && !actual.SameRequestedState(requested),"either invalid ContextFlags operand fails with or without bit1");
                var equallyInvalid=actual.Copy();if(bit1) equallyInvalid.Raw[68]^=2;
                CmdTestAssert(!actual.SameRequestedState(equallyInvalid),"equally invalid ContextFlags never qualify");
            }
            foreach(bool tf in new bool[]{false,true}) {
                var changed=requested.WithRipTf(requested.U64(248)+2,tf);var expected=(byte[])saved.Clone();
                CmdTestPut(expected,248,requested.U64(248)+2,8);CmdTestPut(expected,68,tf?flags|0x100U:flags&~0x100U,4);
                CmdTestBytesEqual(expected,changed.Raw,"request construction changes only RIP and owned TF, preserving bit1");
                CmdTestBytesEqual(saved,requested.Raw,"WithRipTf preserves its complete source buffer");
            }
        }
    }
    static void CmdTestBit1Routes() {
        foreach(uint flags in new uint[]{0x200U,0x202U}) foreach(bool step in new bool[]{false,true}) foreach(uint returnTf in new uint[]{0,0x100}) {
            var baseline=new CmdFakeApi(step,false,false);CmdTestEventFlags(baseline,flags,returnTf);baseline.ContextCase=new CmdContextFake();
            CmdTestRun(baseline,false,"raw request preservation baseline");
            for(int atSet=1;atSet<=(step?4:2);atSet++) {
                var fake=CmdTestEflagsRoute(step,atSet,2,0,flags,returnTf);
                CmdTestAssert(fake.Calls.Count==baseline.Calls.Count,"bit1 admission adds no native calls");
                for(int i=0;i<baseline.Calls.Count;i++) CmdTestAssert(fake.Calls[i]==baseline.Calls[i],"bit1 admission preserves exact native call order");
                for(int i=0;i<baseline.ContextCase.RequestedBytes.Count;i++)
                    CmdTestBytesEqual(baseline.ContextCase.RequestedBytes[i],fake.ContextCase.RequestedBytes[i],"every requested Set buffer is byte-identical to baseline");
                for(int i=0;i<fake.ContextCase.SourceContexts.Count;i++)
                    CmdTestBytesEqual(fake.ContextCase.SourceBytes[i],fake.ContextCase.SourceContexts[i].Raw,"session never rewrites fresh context bytes");
                CmdTestAssert(fake.ReturnFlags==(flags|returnTf),"fresh return preserves both bit1 representations and TF states");
                if(step) CmdTestAssert(fake.ContextCase.RequestedEflags[0]==(flags|0x100U) && fake.ContextCase.RequestedEflags[1]==flags,
                    "actual immediate requests set then clear TF without changing bit1");
            }
            foreach(int atSet in new int[]{1,2}) for(int bit=0;bit<32;bit++) if(bit!=1) {
                var fake=CmdTestEflagsRoute(step,atSet,(1U<<bit)|2U,0,flags,returnTf);
                CmdTestAssert(fake.Number("eflags_difference_mask")==((1L<<bit)|2L),"bit1 cannot mask any controlled flag including TF and bit31");
            }
            for(int bit=0;bit<21;bit++) if(bit!=3) CmdTestEflagsRoute(step,1,2,1L<<bit,flags,returnTf);
        }
    }
    static void CmdTestMovState() {
        foreach(uint flags in new uint[]{0x200U,0x202U}) foreach(bool tf in new bool[]{false,true}) {
            var before=CmdTestContext(CmdFakeApi.Ntdll+0x1001,CmdFakeApi.Stack);CmdTestPut(before.Raw,68,flags,4);
            var after=before.WithRipTf(before.U64(248)+2,tf);CmdTestPut(after.Raw,200,before.U64(128),8);
            var saved=(byte[])before.Raw.Clone();
            for(int bit=0;bit<32;bit++) foreach(uint reserved in new uint[]{0,2}) {
                var actual=after.Copy();CmdTestPut(actual.Raw,68,actual.U32(68)^((1U<<bit)|reserved),4);
                CmdTestAssert(actual.MatchesAfterMov(before)==(bit==1 || bit==8),
                    "MOV final comparison admits bit1 and preserves preexisting observed-TF construction only");
                CmdTestBytesEqual(saved,before.Raw,"MOV comparison never mutates its source snapshot");
            }
            for(int bit=0;bit<21;bit++) if(bit!=3) {
                var actual=after.Copy();CmdTestMutateContext(actual,1L<<bit);actual.Raw[68]^=2;
                CmdTestAssert(!actual.MatchesAfterMov(before),"bit1 cannot excuse an unexpected MOV register selector or ContextFlags delta");
            }
        }
        foreach(uint flags in new uint[]{0x200U,0x202U}) foreach(uint difference in new uint[]{2,0x102,0x80000002}) {
            var fake=new CmdFakeApi(true,false,false);CmdTestEventFlags(fake,flags,0);fake.ContextCase=new CmdContextFake();fake.StepEflagsDifference=difference;
            bool failed=difference==0x80000002;CmdTestRun(fake,failed,"post-MOV injection exercises the separate final comparison call site");
            CmdTestEflagsValue(fake,0);
            CmdTestAssert(fake.Number("context_mismatch_mask")==0,"MOV comparison never overwrites latest immediate raw diagnostics");
            if(failed) CmdTestContextOutcome(fake,"context_failed","none",0,0);
            else CmdTestAssert(fake.ContextCase.RequestedEflags[1]==(flags^2U),"TF clear uses fresh post-MOV bit1 without canonicalization");
            CmdTestContextCallOrder(fake,fake.ContextCase);
        }
    }
    static void CmdTestBit1ResetAndFirstFailure() {
        foreach(string mode in new string[]{"set_false","get_false","null","mismatch","set_throw","get_throw"}) foreach(int error in new int[]{0,87}) {
            var fake=CmdTestContextFailure(mode,error,2,1L<<20);fake.ContextCase.PriorBit1=true;
            CmdTestRun(fake,true,"later failure resets prior admissible raw8 XOR2");
            string reason=mode=="set_false"?"context_failed":mode=="get_false"?"context_get_failed":
                mode=="null"?"context_roundtrip_unavailable":mode=="mismatch"?"context_roundtrip_mismatch":"internal_exception";
            string api=mode=="set_false"?"SetThreadContext":mode=="get_false"?"GetThreadContext":"none";
            CmdTestContextOutcome(fake,reason,api,api=="none"?0:error,mode=="mismatch"?1L<<20:-1);
            CmdTestAssert(fake.ContextCase.SawPriorBit1 && fake.ContextCase.Sets==2 && fake.ContextCase.MasksBeforeSet[1]==-1 &&
                fake.ContextCase.EflagsBeforeSet[1]==-1,"both diagnostics reset after the earlier admissible raw difference");
        }
        foreach(bool stepFailure in new bool[]{false,true}) {
            var fake=new CmdFakeApi(stepFailure,false,false);
            fake.ContextCase=new CmdContextFake {Mode=stepFailure?"eflags":"ordinary_false",AtSet=stepFailure?1:2,
                AtOrdinaryGet=3,PriorBit1=!stepFailure,MismatchMask=0,EflagsDifference=2};
            fake.WrongStepR10=stepFailure;CmdTestRun(fake,true,"later independent failure retains prior admissible immediate diagnostics");
            CmdTestAssert(fake.ContextCase.SawPriorBit1 && fake.Number("context_mismatch_mask")==8 && fake.Number("pair_complete")==0 &&
                fake.Identity("error")=="context_failed" && fake.Identity("error_api")== (stepFailure?"none":"GetThreadContext") &&
                fake.Number("native_error")== (stepFailure?0:87),"ordinary Get and MOV errors retain their own reasons plus raw8 XOR2");
            CmdTestEflagsValue(fake,2);CmdTestContextCallOrder(fake,fake.ContextCase);
        }
        foreach(bool cleanupThrows in new bool[]{false,true}) foreach(uint difference in new uint[]{2,0x102,0x80000002}) {
            var fake=new CmdFakeApi(true,false,false);
            fake.ContextCase=new CmdContextFake {Mode="eflags",AtSet=2,PriorBit1=true,MismatchMask=1L<<14,EflagsDifference=difference};
            fake.FailName="TerminateProcess";fake.ThrowFault=cleanupThrows;
            var session=CmdTestRun(fake,true,"first nonadmissible mismatch survives cleanup after earlier admitted bit1");
            CmdTestContextOutcome(fake,"context_roundtrip_mismatch","none",0,(1L<<14)|8);
            CmdTestAssert(fake.ContextCase.SawPriorBit1 && fake.TerminateCount==1 && !session.MayCallOriginalCleanup &&
                fake.Identity("cleanup")=="retained_fatal","cleanup cannot turn first mismatch into an admitted comparison");
        }
    }
}
