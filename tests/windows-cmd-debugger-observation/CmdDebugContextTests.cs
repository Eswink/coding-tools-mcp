// Pure context-mask and reason-routing contracts; all operations use the existing fake.
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
        public bool SawPriorZero;
        public readonly List<int> SetCalls=new List<int>(),ReadbackCalls=new List<int>();
        public readonly List<long> MasksBeforeSet=new List<long>();
        bool awaitingReadback;
        public bool Set(CmdFakeApi fake) {
            Sets++;SetCalls.Add(fake.Calls.Count-1);MasksBeforeSet.Add(fake.Number("context_mismatch_mask"));Error=0;
            CmdTestAssert(fake.Number("context_mismatch_mask")==-1,"stale mask cleared before every Set");
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
                OrdinaryGets++;
                if(Sets>0 && fake.Number("context_mismatch_mask")==0) SawPriorZero=true;
                if(Mode=="ordinary_false" && OrdinaryGets==AtOrdinaryGet) {
                    FailureCall=fake.Calls.Count-1;Error=ReportedError;return false;
                }
                return true;
            }
            awaitingReadback=false;Readbacks++;ReadbackCalls.Add(fake.Calls.Count-1);
            CmdTestAssert(fake.Number("context_mismatch_mask")==-1,"mask remains unavailable until immediate comparison");
            if(Sets!=AtSet || Mode=="none" || Mode=="ordinary_false") return true;
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
        CmdTestAssert(fake.Identity("protocol")=="own-child-open-v2","context reason split uses strict v2 protocol");
        CmdTestAssert(fake.Identity("error")==reason && fake.Identity("error_api")==api && fake.Number("native_error")==error &&
            fake.Number("context_mismatch_mask")==mask,"first failure reason API error and mask survive cleanup");
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
            CmdTestAssert(fake.Calls.Count==baseline.Calls.Count,"context diagnostics add no native calls");
            for(int i=0;i<baseline.Calls.Count;i++) CmdTestAssert(fake.Calls[i]==baseline.Calls[i],"context diagnostics preserve exact native call order");
            CmdTestAssert(fake.ContextCase.Sets==(step?4:2) && fake.ContextCase.Readbacks==fake.ContextCase.Sets,
                "entry step return routes each perform one immediate readback");
            CmdTestAssert(fake.ContextCase.OrdinaryGets==(step?5:3) && CmdTestCallCount(fake,"GetThreadContext")== (step?9:5),
                "fixed baseline context call counts remain unchanged");
            CmdTestContextCallOrder(fake,fake.ContextCase);
        }
        CmdTestContextRoutes();CmdTestContextResetAndFirstFailure();
    }
}
