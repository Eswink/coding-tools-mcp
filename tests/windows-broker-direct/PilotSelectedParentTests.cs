// Managed-only tests inject every operation. No filesystem or native API is used.
using System;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    sealed class SelectedParentTestTrace {
        public string Mode="ok",Trace="";
        public int FailAt=-1,Opens,Inspections,Trusts,Closes,Guards;
        public readonly List<uint> Rights=new List<uint>();
        public readonly List<int> Closed=new List<int>();
    }
    static SelectedParentOperations SelectedParentTestOperations(SelectedParentTestTrace t) {
        return new SelectedParentOperations {
            Resolve=delegate {if(t.Mode=="resolve_throw") throw new InvalidOperationException("lookup failed");return t.Mode=="mismatch"?"C:\\Fixture\\Other\\Temp":"C:\\Fixture\\Local\\Temp";},
            Open=delegate(ref IntPtr h,string p,uint access,string label,DirectReceipt r) {
                int index=t.Opens++;t.Trace+="o"+index+";";t.Rights.Add(access);
                if(index==t.FailAt && t.Mode=="open_before") throw new InvalidOperationException("open failed");
                if(index==t.FailAt && t.Mode=="null_open") return;
                if(index==t.FailAt && t.Mode=="invalid_output") {h=new IntPtr(-1);return;}
                h=new IntPtr(index+100);
                if(index==t.FailAt && t.Mode=="open_after") throw new InvalidOperationException("handle inspection failed");
            },
            Inspect=delegate(IntPtr h,string p,string identity,uint? volume) {
                int index=h.ToInt32()-100;t.Inspections++;t.Trace+="i"+index+";";
                if(index==t.FailAt && t.Mode=="inspect_throw") throw new InvalidOperationException("reparse/type/path/volume rejected");
                var info=new FILE_INFO();info.attributes=0x10;info.volume=7;info.indexLow=(uint)(index+1);
                if(identity!=null && index==t.FailAt && t.Mode=="changed_identity") info.indexLow++;
                if(volume.HasValue && volume.Value!=info.volume) throw new InvalidOperationException("volume mismatch");
                return info;
            },
            Trust=delegate(IntPtr h,string p,string identity,string label,DirectReceipt r) {
                t.Trusts++;t.Trace+="t;";ParentCandidateTestReceipt(r,label);
                if(t.Mode=="trust_throw") throw new InvalidOperationException("strict checker rejected");
                if(t.Mode=="stale_success") {r.Numbers[label+"_broker_owned"]=1;throw new InvalidOperationException("checker failed after value");}
                if(t.Mode=="missing_acl") r.Numbers.Remove(label+"_ace_1_flags");
                if(t.Mode=="unowned_token") r.Numbers[label+"_broker_owner_token_unowned_output"]=1;
                if(t.Mode=="free_unknown") r.Numbers[label+"_security_free_confirmed"]=0;
            },
            Close=delegate(ref IntPtr h,string label,DirectReceipt r) {
                int index=h.ToInt32()-100;t.Closes++;t.Closed.Add(index);t.Trace+="c"+index+";";
                if(index==t.FailAt && t.Mode=="close_throw") throw new InvalidOperationException("uncertain close");
                if(index==t.FailAt && t.Mode=="close_false") return false;
                h=IntPtr.Zero;r.Numbers[label+"_close_confirmed"]=1;return true;
            }
        };
    }
    static void SelectedParentTestAssert(bool passed,string label,ref int count) {
        if(!passed) throw new InvalidOperationException("selected parent contract: "+label);count++;
    }
    static void SelectedParentTestReject(Action action,string label,ref int count) {
        bool rejected=false;try {action();} catch(Exception) {rejected=true;}
        SelectedParentTestAssert(rejected,label,ref count);
    }
    public static int RunSelectedParentContractTests() {
        int count=0;
        SelectedParentTestAssert(SelectedParentFromKnownFolder("C:\\Fixture\\Local")=="C:\\Fixture\\Local\\Temp","literal child",ref count);
        foreach(string bad in new string[]{null,"","C:","C:\\","\\\\host\\share","\\\\?\\C:\\x","C:\\x\\..\\y","C:\\x\\.\\y","C:\\x\\","C:\\NUL","C:\\x\\CON.txt","C:\\x\\COM\u00b9","C:\\x\\a ","C:\\x\\a.","C:/x","C:\\x:y","C:\\x\\\ud800"}) {
            string value=bad;SelectedParentTestReject(()=>SelectedParentFromKnownFolder(value),"invalid fixed known folder",ref count);
        }
        string bounded="C:\\x";for(int i=0;i<30;i++) bounded+="\\x";
        SelectedParentTestAssert(SelectedParentChain(bounded).Length==32,"inclusive 32-handle bound",ref count);
        SelectedParentTestReject(()=>SelectedParentChain(bounded+"\\x"),"overlong ancestor chain",ref count);
        var t=new SelectedParentTestTrace();var receipt=new SelectedParentReceipt();
        var lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));lease.AcquireSelectedParent();
        SelectedParentTestAssert(receipt.Acquired && receipt.AcquiredHandles==4 && t.Trusts==1,"full chain before endpoint trust",ref count);
        SelectedParentTestAssert(t.Rights.Count==4 && t.Rights[0]==0xA0 && t.Rights[1]==0xA0 && t.Rights[2]==0xA0 && t.Rights[3]==0x20081,"exact ancestor and endpoint access",ref count);
        SelectedParentTestAssert(t.Trace.StartsWith("o0;i0;i0;o1;i1;i0;i1;",StringComparison.Ordinal),"root-to-leaf acquisition and prior-pin recheck",ref count);
        lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;t.Trace+="g;";},new string[0]);
        SelectedParentTestAssert(t.Guards==1 && receipt.VerifiedGuards==1 && t.Trusts==3,"guard bracketed by fresh endpoint checks",ref count);
        SelectedParentTestAssert(lease.CloseSelectedParent() && receipt.CloseConfirmed && t.Closes==4,"all pins close",ref count);
        SelectedParentTestAssert(t.Closed[0]==3 && t.Closed[1]==2 && t.Closed[2]==1 && t.Closed[3]==0,"reverse close order",ref count);
        SelectedParentTestAssert(lease.CloseSelectedParent() && t.Closes==4,"confirmed close never repeated",ref count);
        SelectedParentTestReject(()=>lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;},new string[0]),"no scan after closure",ref count);
        SelectedParentTestReject(()=>lease.AcquireSelectedParent(),"no reopen after closure",ref count);
        foreach(string mode in new string[]{"resolve_throw","mismatch"}) {
            t=new SelectedParentTestTrace {Mode=mode};receipt=new SelectedParentReceipt();lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));
            SelectedParentTestReject(()=>lease.AcquireSelectedParent(),"resolution failure",ref count);
            SelectedParentTestAssert(lease.CloseSelectedParent() && t.Opens==0 && t.Closes==0 && !receipt.Acquired,"resolution cannot open",ref count);
        }
        foreach(string mode in new string[]{"open_before","open_after","null_open","invalid_output","inspect_throw","changed_identity"}) for(int failureAt=0;failureAt<4;failureAt++) {
            t=new SelectedParentTestTrace {Mode=mode,FailAt=failureAt};receipt=new SelectedParentReceipt();lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));
            SelectedParentTestReject(()=>lease.AcquireSelectedParent(),"acquisition failure",ref count);
            bool closed=lease.CloseSelectedParent();int expected=failureAt+((mode=="open_before" || mode=="null_open" || mode=="invalid_output")?0:1);
            SelectedParentTestAssert(t.Opens==failureAt+1 && t.Closes==expected && !receipt.Acquired,"partial acquisition stops and releases owned handles",ref count);
            SelectedParentTestAssert(closed==(mode!="invalid_output"),"ambiguous output prevents confirmed cleanup",ref count);
            int previous=t.Closes;lease.CloseSelectedParent();SelectedParentTestAssert(t.Closes==previous,"partial cleanup not retried",ref count);
            SelectedParentTestReject(()=>lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;},new string[0]),"failed acquisition never scans",ref count);
            SelectedParentTestAssert(t.Guards==0,"no guard side effects on failed lease",ref count);
        }
        foreach(string mode in new string[]{"trust_throw","stale_success","missing_acl","unowned_token","free_unknown"}) {
            t=new SelectedParentTestTrace {Mode=mode};receipt=new SelectedParentReceipt();lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));
            SelectedParentTestReject(()=>lease.AcquireSelectedParent(),"strict endpoint failure",ref count);
            bool closed=lease.CloseSelectedParent();
            SelectedParentTestAssert(!receipt.Acquired && receipt.Failure!=null && t.Closes==4,"no stale endpoint acceptance",ref count);
            SelectedParentTestAssert(closed==(mode!="unowned_token" && mode!="free_unknown"),"checker cleanup uncertainty preserved",ref count);
        }
        foreach(string mode in new string[]{"close_false","close_throw"}) for(int failureAt=0;failureAt<4;failureAt++) {
            t=new SelectedParentTestTrace {Mode=mode,FailAt=failureAt};receipt=new SelectedParentReceipt();lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));lease.AcquireSelectedParent();
            SelectedParentTestAssert(!lease.CloseSelectedParent() && !receipt.CloseConfirmed && receipt.Failure!=null && t.Closes==4,"close failure cannot skip other pins",ref count);
            SelectedParentTestAssert(!lease.CloseSelectedParent() && t.Closes==4,"uncertain close cannot retry",ref count);
            SelectedParentTestReject(()=>lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;},new string[0]),"uncertain close blocks subsequent work",ref count);
        }
        t=new SelectedParentTestTrace();receipt=new SelectedParentReceipt();lease=new PilotSelectedParent("C:\\Fixture\\Local\\Temp",receipt,SelectedParentTestOperations(t));lease.AcquireSelectedParent();
        SelectedParentTestReject(()=>lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;throw new InvalidOperationException("hidden/prior/error marker");},new string[0]),"scan failure stops lease",ref count);
        SelectedParentTestReject(()=>lease.GuardSelectedRecovery(delegate(string[] allowed) {t.Guards++;},new string[0]),"failed scan cannot be bypassed",ref count);
        SelectedParentTestAssert(t.Guards==1 && receipt.VerifiedGuards==0 && lease.CloseSelectedParent(),"scan failure still closes pins",ref count);
        return count;
    }
}
