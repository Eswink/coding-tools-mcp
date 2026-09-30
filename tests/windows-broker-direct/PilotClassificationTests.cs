// Managed-only behavior tests for the classifier used by the real coordinator.
// All inputs are synthetic receipts and strings; no OS APIs or real resources.
using System;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    const string PilotTestPre="token=true\ninside=true\noutside_read=true\noutside_write=true\n";
    const string PilotTestFull=PilotTestPre+"network=true\n";
    const string PilotTestChecks="protocol_catalog_open=0\nprotocol_catalog_close=0\nnamespace_catalog_open=0\nnamespace_catalog_close=0\nprovider_dll_open=0\nwinsock_dll_open=0\n";
    static Dictionary<string,string> PilotClassificationTestFiles(string kind) {
        var files=new Dictionary<string,string>(StringComparer.Ordinal);
        files["canary.txt"]="synthetic-outside-canary";
        if(kind=="ordinary") return files;
        if(kind=="reference") {
            files["pre-network.txt"]=PilotTestPre;files["runtime-checks.txt"]=PilotTestChecks;files["receipt.txt"]=PilotTestFull;
            return files;
        }
        files["script-entry.txt"]="runtime-entered\r\n";files["stdout.txt"]="runtime-ok\r\n";files["mutation.txt"]="runtime-ok\r\n";
        files["runtime-canary.txt"]=kind=="node"?"read=EACCES\nwrite=EACCES\n":kind=="cmd"?"read_errorlevel=1\nwrite_errorlevel=1\n":
            "read_type=System.UnauthorizedAccessException\nread_hresult=-2147024891\nwrite_type=System.UnauthorizedAccessException\nwrite_hresult=-2147024891\n";
        return files;
    }
    static PilotCaseReceipt PilotClassificationTestRow(string kind,uint exit) {
        var row=new PilotCaseReceipt();row.Case=kind;row.Launcher.Kind=kind;
        row.AuthorityObserved=kind!="ordinary";row.PreResumeReady=kind!="ordinary";
        row.OrdinarySignatureMatched=kind=="ordinary";row.OrdinaryRejected=kind=="ordinary";
        row.Launcher.CreateAttempted=true;row.Launcher.Created=true;row.Launcher.CreateError=0;
        row.Launcher.Assigned=kind!="ordinary";row.Launcher.Resumed=kind!="ordinary";
        row.Launcher.Wait=WAIT_OBJECT_0;row.Launcher.Exit=exit;
        return row;
    }
    static PilotCaseReceipt PilotClassifyTest(string kind,uint exit,Action<Dictionary<string,string>> mutateFiles,Action<PilotCaseReceipt> mutateRow) {
        var files=PilotClassificationTestFiles(kind);var row=PilotClassificationTestRow(kind,exit);
        if(kind=="reference" && exit==15107) files.Remove("receipt.txt");
        if(mutateFiles!=null) mutateFiles(files);if(mutateRow!=null) mutateRow(row);
        ClassifyPilotFacts(row,files);return row;
    }
    static void PilotClassificationAssert(bool condition,string label,ref int checks) {
        checks++;if(!condition) throw new InvalidOperationException("managed classification contract: "+label);
    }
    public static int RunPilotClassificationContractTests() {
        int checks=0;PilotCaseReceipt row;
        row=PilotClassifyTest("ordinary",0,null,null);
        PilotClassificationAssert(!row.Fatal && !row.Launcher.Resumed && !row.PositivePassed && !row.OfflineReferenceRouteValid &&
            !row.NetworkDenialProven && row.Status=="ordinary_signature_matched_and_lpac_rejected","never-resumed ordinary",ref checks);
        row=PilotClassifyTest("reference",15107,null,null);
        PilotClassificationAssert(!row.Fatal && row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed &&
            !row.NetworkDenialProven && row.Status=="winsock_initialization_failed_10107","reference offline route only",ref checks);
        row=PilotClassifyTest("reference",0,null,null);
        PilotClassificationAssert(!row.Fatal && row.OfflineReferenceRouteValid && row.NativeFiveAssertionsPassed &&
            !row.NetworkDenialProven && row.Status=="native_five_assertions_completed_connection_failed","reference five assertions without denial claim",ref checks);
        foreach(string newline in new string[]{"\n","\r\n","\r"}) {
            string separator=newline;
            row=PilotClassifyTest("reference",0,delegate(Dictionary<string,string> files) {
                foreach(string name in new string[]{"pre-network.txt","runtime-checks.txt","receipt.txt"}) files[name]=files[name].Replace("\n",separator);
            },null);
            PilotClassificationAssert(!row.Fatal && row.NativeFiveAssertionsPassed,"line-ending equivalence",ref checks);
        }
        foreach(uint exit in new uint[]{0,15107}) {
            foreach(Action<Dictionary<string,string>> change in new Action<Dictionary<string,string>>[]{
                x=>x.Remove("pre-network.txt"),x=>x["pre-network.txt"]+="extra=true\n",
                x=>x["pre-network.txt"]=x["pre-network.txt"].Replace("inside=true","token=true"),
                x=>x["pre-network.txt"]=x["pre-network.txt"].Replace("inside=true","inside=false"),
                x=>x.Remove("runtime-checks.txt"),x=>x["runtime-checks.txt"]+="extra=0\n",
                x=>x["runtime-checks.txt"]=x["runtime-checks.txt"].Replace("protocol_catalog_close","protocol_catalog_open"),
                x=>x["runtime-checks.txt"]=x["runtime-checks.txt"].Replace("=0","=not-a-number"),
                x=>x["runtime-checks.txt"]=x["runtime-checks.txt"].Replace("provider_dll_open","unknown_open")}) {
                row=PilotClassifyTest("reference",exit,change,null);
                PilotClassificationAssert(row.Fatal && !row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed && !row.NetworkDenialProven,
                    "native preliminary/schema failure",ref checks);
            }
        }
        foreach(Action<Dictionary<string,string>> change in new Action<Dictionary<string,string>>[]{
            x=>x.Remove("receipt.txt"),x=>x["receipt.txt"]+="extra=true\n",x=>x["receipt.txt"]+="\n",
            x=>x["receipt.txt"]=x["receipt.txt"].Replace("network=true","network=false"),
            x=>x["receipt.txt"]=x["receipt.txt"].Replace("inside=true","token=true")}) {
            row=PilotClassifyTest("reference",0,change,null);
            PilotClassificationAssert(row.Fatal && !row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed,"invalid/missing full receipt",ref checks);
        }
        foreach(string final in new string[]{"",PilotTestFull,"network=true\n"}) {
            string value=final;row=PilotClassifyTest("reference",15107,x=>x["receipt.txt"]=value,null);
            PilotClassificationAssert(row.Fatal && !row.OfflineReferenceRouteValid,"15107 cannot coexist with any final receipt",ref checks);
        }
        foreach(uint exit in new uint[]{1,42,5000,15108}) {
            row=PilotClassifyTest("reference",exit,null,null);
            PilotClassificationAssert(row.Fatal && !row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed && !row.NetworkDenialProven,"wrong native exit",ref checks);
        }
        foreach(Action<PilotCaseReceipt> change in new Action<PilotCaseReceipt>[]{
            x=>x.AuthorityObserved=false,x=>x.PreResumeReady=false,x=>x.Launcher.Assigned=false,
            x=>x.Launcher.Resumed=false,x=>x.Launcher.Wait=WAIT_TIMEOUT,x=>x.Launcher.Exit=UInt32.MaxValue}) {
            row=PilotClassifyTest("reference",0,null,change);
            PilotClassificationAssert(row.Fatal && !row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed,"native lifecycle not established",ref checks);
        }
        foreach(string kind in new string[]{"node","cmd","powershell","pwsh"}) {
            row=PilotClassifyTest(kind,0,null,null);
            PilotClassificationAssert(row.PositivePassed && !row.Fatal && row.ScriptEntryObserved && row.OutputOk && row.MutationOk &&
                !row.OutsideReadObserved && !row.OutsideWriteObserved && !row.NetworkDenialProven && row.Status=="positive_operation_completed" &&
                row.CanaryClassification==(kind=="cmd"?"cmd_errorlevel_is_not_raw_denial_evidence":"exact_runtime_access_denied"),"positive fixed runtime "+kind,ref checks);
            uint[] loaderExits=new uint[]{0xC0000135,0xC0000142,0xC000007B};
            string[] loaderNames=new string[]{"STATUS_DLL_NOT_FOUND","STATUS_DLL_INIT_FAILED","STATUS_INVALID_IMAGE_FORMAT"};
            for(int i=0;i<loaderExits.Length;i++) {
                row=PilotClassifyTest(kind,loaderExits[i],x=>x.Remove("script-entry.txt"),null);
                PilotClassificationAssert(!row.Fatal && !row.PositivePassed && !row.ScriptEntryObserved && row.KnownStartupStatus==loaderNames[i] &&
                    row.Status=="known_startup_status_without_script_entry","loader status without entry",ref checks);
            }
            row=PilotClassifyTest(kind,42,x=>x.Remove("script-entry.txt"),null);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && row.KnownStartupStatus==null && row.Status=="no_script_entry_evidence_inconclusive","unknown no-entry failure",ref checks);
            row=PilotClassifyTest(kind,0,x=>x["stdout.txt"]="wrong",null);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && !row.OutputOk && row.Status=="user_code_positive_operation_failed","stdout failure",ref checks);
            row=PilotClassifyTest(kind,0,x=>x["mutation.txt"]="wrong",null);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && !row.MutationOk && row.Status=="user_code_positive_operation_failed","mutation failure",ref checks);
            row=PilotClassifyTest(kind,42,null,null);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && row.ScriptEntryObserved && row.Status=="positive_operation_completed_contract_failed","nonzero runtime exit",ref checks);
            row=PilotClassifyTest(kind,0,null,x=>x.Launcher.Wait=WAIT_TIMEOUT);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && row.Status=="deadline_exceeded","runtime deadline",ref checks);
            row=PilotClassifyTest(kind,0xC0000135,null,null);
            PilotClassificationAssert(!row.Fatal && !row.PositivePassed && row.ScriptEntryObserved && row.Status=="positive_operation_completed_contract_failed","loader status with entry stays distinct",ref checks);
        }
        foreach(string kind in new string[]{"node","powershell","pwsh"}) {
            foreach(Action<Dictionary<string,string>> change in new Action<Dictionary<string,string>>[]{
                x=>x.Remove("runtime-canary.txt"),x=>x["runtime-canary.txt"]+="extra=unknown\n",x=>x["runtime-canary.txt"]="read=OTHER\nwrite=OTHER\n"}) {
                row=PilotClassifyTest(kind,0,change,null);
                PilotClassificationAssert(!row.Fatal && !row.PositivePassed && row.CanaryClassification=="missing_or_other_runtime_error","missing/extra/wrong denial receipt",ref checks);
            }
            foreach(string direction in new string[]{"read","write"}) {
                string success=kind=="node"?direction+"=unexpected_success\n":direction+"_type=success\n";
                row=PilotClassifyTest(kind,0,x=>x["runtime-canary.txt"]+=success,null);
                PilotClassificationAssert(row.Fatal && !row.PositivePassed && row.OutsideWriteAbsent &&
                    (direction=="read"?row.OutsideReadObserved:row.OutsideWriteObserved) && row.Status=="runtime_outside_access_observed",
                    "explicit "+direction+" success contradicts denial despite absent outside file",ref checks);
                foreach(string newline in new string[]{"\r","\r\n"}) {
                    string separator=newline;
                    row=PilotClassifyTest(kind,0,x=>x["runtime-canary.txt"]=(x["runtime-canary.txt"]+success).Replace("\n",separator),null);
                    PilotClassificationAssert(row.Fatal && !row.PositivePassed && row.OutsideWriteAbsent &&
                        (direction=="read"?row.OutsideReadObserved:row.OutsideWriteObserved),"CR/CRLF escape marker cannot be hidden",ref checks);
                }
            }
        }
        row=PilotClassifyTest("cmd",0,x=>x["outside-read.txt"]="prefix synthetic-outside-canary suffix",null);
        PilotClassificationAssert(row.Fatal && !row.PositivePassed && row.OutsideReadObserved && row.Status=="runtime_outside_access_observed","cmd observed outside read",ref checks);
        foreach(string kind in new string[]{"ordinary","reference","node","cmd","powershell","pwsh"}) {
            foreach(Action<Dictionary<string,string>> change in new Action<Dictionary<string,string>>[]{
                x=>x["probe-write.txt"]="",x=>x["canary.txt"]="changed",x=>x.Remove("canary.txt")}) {
                row=PilotClassifyTest(kind,0,change,null);
                PilotClassificationAssert(row.Fatal && !row.PositivePassed && !row.OfflineReferenceRouteValid && row.Status=="outside_boundary_failed","outside host evidence failure",ref checks);
            }
            row=PilotClassifyTest(kind,0,null,x=>x.NetworkDenialProven=true);
            PilotClassificationAssert(!row.NetworkDenialProven,"classification never proves precise network denial",ref checks);
        }
        row=PilotClassifyTest("node",0,x=>x["probe-write.txt"]="",x=>x.PositivePassed=true);
        PilotClassificationAssert(row.Fatal && !row.PositivePassed,"stale positive cleared before boundary failure",ref checks);
        row=PilotClassifyTest("node",0,null,delegate(PilotCaseReceipt x) {
            x.Fatal=true;x.Status="prior_failed";x.PositivePassed=true;x.OutsideReadObserved=true;x.OutsideWriteObserved=true;
            x.ScriptEntryObserved=true;x.NativeFiveAssertionsPassed=true;
        });
        PilotClassificationAssert(row.Fatal && !row.PositivePassed && row.Status=="prior_failed","classification cannot heal prior fatal failure",ref checks);
        PilotClassificationAssert(row.OutsideReadObserved && row.OutsideWriteObserved && row.ScriptEntryObserved && row.NativeFiveAssertionsPassed,
            "prior fatal factual evidence is preserved",ref checks);
        bool rejected=false;
        try {PilotClassifyTest("node",0,x=>x["stdout.txt"]=null,null);} catch(InvalidOperationException) {rejected=true;}
        PilotClassificationAssert(rejected,"null capture text is not absence",ref checks);
        rejected=false;try {ClassifyPilotFacts(null,new Dictionary<string,string>());} catch(ArgumentNullException) {rejected=true;}
        PilotClassificationAssert(rejected,"missing row rejected",ref checks);
        rejected=false;try {ClassifyPilotFacts(new PilotCaseReceipt(),null);} catch(ArgumentNullException) {rejected=true;}
        PilotClassificationAssert(rejected,"missing capture dictionary rejected",ref checks);
        return checks;
    }
}
