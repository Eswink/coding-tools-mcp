// Managed-only tests for the same predicates used immediately before launch/advance.
using System;

public static partial class BrokerDirectLauncher {
    static PilotCaseReceipt PilotGateTestRow() {
        var row=new PilotCaseReceipt();row.Case="reference";row.Launcher=PilotPolicyTestReceipt(false);
        row.AuthorityObserved=true;row.IndividualResourceCleanupConfirmed=true;row.CaptureIntegrityConfirmed=true;
        row.ProfileDeleteApiConfirmed=true;row.OwnedRootRemoved=true;row.CleanupPreconditionsConfirmed=true;
        row.CaseMarkerResolved=true;row.ScopedLifecycleCleanupConfirmed=true;return row;
    }
    public static int RunPilotGateContractTests() {
        int checks=0;var row=PilotGateTestRow();
        PilotPolicyTest(PilotMayResume(true,true,true,row),"complete resume preconditions",ref checks);
        PilotPolicyTest(!PilotMayResume(false,true,true,row),"missing same-run ordinary witness",ref checks);
        PilotPolicyTest(!PilotMayResume(true,false,true,row),"uncertain handle ownership",ref checks);
        PilotPolicyTest(!PilotMayResume(true,true,false,row),"unowned profile",ref checks);
        foreach(Action<PilotCaseReceipt> change in new Action<PilotCaseReceipt>[] {
            x=>x.Fatal=true,x=>x.AuthorityObserved=false,x=>x.Case="ordinary",x=>x.Policy="fallback",
            x=>x.Launcher.HostStdioClosed=false,x=>x.Launcher.Assigned=true,x=>x.Launcher.Resumed=true,
            x=>x.Launcher.Numbers["token_close_error"]=6,x=>x.Launcher.Numbers["duplicate_close_error"]=6,
            x=>x.Launcher.Numbers["accesscheck_aap_api_success"]=0}) {
            row=PilotGateTestRow();change(row);PilotPolicyTest(!PilotMayResume(true,true,true,row),"resume negative",ref checks);
        }
        row=PilotGateTestRow();PilotPolicyTest(PilotCleanupPreconditions(row) && PilotMayAdvance(row),"confirmed scoped cleanup",ref checks);
        foreach(Action<PilotCaseReceipt> change in new Action<PilotCaseReceipt>[] {
            x=>x.Fatal=true,x=>x.IndividualResourceCleanupConfirmed=false,x=>x.CaptureIntegrityConfirmed=false,
            x=>x.ProfileDeleteApiConfirmed=false,x=>x.OwnedRootRemoved=false,x=>x.CleanupPreconditionsConfirmed=false,
            x=>x.CaseMarkerResolved=false,x=>x.ScopedLifecycleCleanupConfirmed=false}) {
            row=PilotGateTestRow();change(row);PilotPolicyTest(!PilotMayAdvance(row),"cleanup negative",ref checks);
        }
        row=PilotGateTestRow();row.Case="ordinary";row.Launcher=PilotPolicyTestReceipt(true);
        PilotPolicyTest(!row.Launcher.Resumed && PilotMayAdvance(row),"stopped never-resumed control can finish scoped cleanup",ref checks);
        row=PilotGateTestRow();row.PositivePassed=false;row.Launcher.Exit=42;
        PilotPolicyTest(PilotMayAdvance(row),"failed positive observation may advance only after scoped cleanup",ref checks);
        row=new PilotCaseReceipt();row.Status="preparation_failed";row.NoCaseResourcesAllocated=true;
        PilotPolicyTest(PilotMayAdvance(row),"explicit no-allocation preparation failure",ref checks);
        row.Launcher.CreateAttempted=true;PilotPolicyTest(!PilotMayAdvance(row),"creation attempt is not no-allocation",ref checks);
        PilotPolicyTest(!PilotMayAdvance(null) && !PilotCleanupPreconditions(null) && !PilotMayResume(true,true,true,null),"missing row",ref checks);
        string trace="";
        PilotCommitBoundary(false,false,true,()=>trace+="v",()=>trace+="b",()=>trace+="r");
        PilotPolicyTest(trace=="vbr","journal commit order",ref checks);
        for(int broken=0;broken<3;broken++) {
            trace="";bool threw=false;int failureStep=broken;
            try {PilotCommitBoundary(false,false,true,
                delegate {trace+="v";if(failureStep==0) throw new InvalidOperationException("verify/close failure");},
                delegate {trace+="b";if(failureStep==1) throw new InvalidOperationException("binding/read/close failure");},
                delegate {trace+="r";if(failureStep==2) throw new InvalidOperationException("rename failure");});}
            catch(InvalidOperationException) {threw=true;}
            PilotPolicyTest(threw && trace==new string[]{"v","vb","vbr"}[broken],"journal failure stops later operations",ref checks);
        }
        foreach(int broken in new int[]{0,1,2}) {
            trace="";bool threw=false;
            try {PilotCommitBoundary(broken==0,broken==1,broken!=2,()=>trace+="v",()=>trace+="b",()=>trace+="r");}
            catch(InvalidOperationException) {threw=true;}
            PilotPolicyTest(threw && trace=="","failed/resolved/unbound journal never commits",ref checks);
        }
        return checks;
    }
}
