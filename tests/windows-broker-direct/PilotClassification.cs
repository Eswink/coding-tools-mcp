// Pure classification of already verified, bounded capture results.
// A missing filename means the wrapper proved capture ERROR_FILE_NOT_FOUND.
// This code has no filesystem, token, process, or network operations.
using System;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    static string PilotFactText(Dictionary<string,string> files,string name) {
        string value;if(!files.TryGetValue(name,out value)) return "";
        if(value==null) throw new InvalidOperationException("verified capture text cannot be null");
        return value;
    }
    static string[] PilotFactLines(string text) {
        if(text.Length==0) return new string[0];
        string[] lines=text.Replace("\r\n","\n").Replace('\r','\n').Split('\n');
        // ReadAllLines semantics: a terminal newline terminates the last line;
        // an additional newline still represents an additional empty line.
        if(lines[lines.Length-1].Length==0) Array.Resize(ref lines,lines.Length-1);
        return lines;
    }
    static bool PilotFactExactLines(Dictionary<string,string> files,string name,string[] expected) {
        if(!files.ContainsKey(name)) return false;
        string[] lines=PilotFactLines(PilotFactText(files,name));if(lines.Length!=expected.Length) return false;
        foreach(string item in expected) {int count=0;foreach(string line in lines) if(line==item) count++;if(count!=1) return false;}
        return true;
    }
    static bool PilotFactRuntimeCheckSchema(Dictionary<string,string> files) {
        if(!files.ContainsKey("runtime-checks.txt")) return false;
        var keys=new Dictionary<string,bool>(StringComparer.Ordinal);
        foreach(string key in new string[]{"protocol_catalog_open","protocol_catalog_close","namespace_catalog_open","namespace_catalog_close","provider_dll_open","winsock_dll_open"}) keys.Add(key,true);
        string[] lines=PilotFactLines(PilotFactText(files,"runtime-checks.txt"));if(lines.Length!=6) return false;
        foreach(string line in lines) {int split=line.IndexOf('=');int value;if(split<=0 || !keys.Remove(line.Substring(0,split)) || !Int32.TryParse(line.Substring(split+1),out value)) return false;}
        return keys.Count==0;
    }
    static void ClassifyPilotFacts(PilotCaseReceipt row,Dictionary<string,string> files) {
        if(row==null || row.Launcher==null || files==null) throw new ArgumentNullException("verified pilot classification facts");
        DirectReceipt r=row.Launcher;
        // Reclassification cannot retain an earlier positive result or a network-denial claim.
        row.PositivePassed=false;row.OfflineReferenceRouteValid=false;row.NetworkDenialProven=false;
        if(row.Fatal) return; // Keep prior factual escape/entry/exit evidence intact.
        row.NativeFiveAssertionsPassed=false;
        row.OutsideUnchanged=false;row.OutsideWriteAbsent=false;row.OutsideReadObserved=false;row.OutsideWriteObserved=false;
        row.ScriptEntryObserved=false;row.OutputOk=false;row.MutationOk=false;row.ExitHex=null;row.KnownStartupStatus=null;
        row.CanaryClassification="not_measured";
        row.OutsideUnchanged=PilotFactText(files,"canary.txt")=="synthetic-outside-canary";
        row.OutsideWriteAbsent=!files.ContainsKey("probe-write.txt");
        if(!row.OutsideUnchanged || !row.OutsideWriteAbsent) {row.Fatal=true;row.Status="outside_boundary_failed";return;}
        if(row.Case=="ordinary") {row.Status="ordinary_signature_matched_and_lpac_rejected";return;}
        bool executed=row.AuthorityObserved && row.PreResumeReady && r.Assigned && r.Resumed && r.Wait==WAIT_OBJECT_0;
        if(row.Case=="reference") {
            bool pre=PilotFactExactLines(files,"pre-network.txt",new string[]{"token=true","inside=true","outside_read=true","outside_write=true"});
            bool full=PilotFactExactLines(files,"receipt.txt",new string[]{"token=true","inside=true","outside_read=true","outside_write=true","network=true"});
            bool checks=PilotFactRuntimeCheckSchema(files);
            bool noFinal=!files.ContainsKey("receipt.txt");
            row.NativeFiveAssertionsPassed=executed && pre && checks && r.Exit==0 && full;
            row.OfflineReferenceRouteValid=executed && pre && checks && ((r.Exit==15107 && noFinal) || row.NativeFiveAssertionsPassed);
            row.Status=r.Exit==15107?"winsock_initialization_failed_10107":row.NativeFiveAssertionsPassed?"native_five_assertions_completed_connection_failed":"matched_reference_inconclusive_or_failed";
            // connect_timeout.is_ok() cannot prove the precise cause of a failed connection.
            row.NetworkDenialProven=false;
            if(!row.OfflineReferenceRouteValid) row.Fatal=true;
            return;
        }
        row.ScriptEntryObserved=PilotFactText(files,"script-entry.txt").Trim()=="runtime-entered";
        row.OutputOk=PilotFactText(files,"stdout.txt").Trim()=="runtime-ok";
        row.MutationOk=PilotFactText(files,"mutation.txt").Trim()=="runtime-ok";
        row.ExitHex=r.Exit.ToString("X8");
        if(row.ExitHex=="C0000135") row.KnownStartupStatus="STATUS_DLL_NOT_FOUND";
        if(row.ExitHex=="C0000142") row.KnownStartupStatus="STATUS_DLL_INIT_FAILED";
        if(row.ExitHex=="C000007B") row.KnownStartupStatus="STATUS_INVALID_IMAGE_FORMAT";
        bool denied=false;
        if(row.Case=="cmd") {
            row.CanaryClassification="cmd_errorlevel_is_not_raw_denial_evidence";
            row.OutsideReadObserved=PilotFactText(files,"outside-read.txt").Contains("synthetic-outside-canary");
        } else {
            string[] expected=row.Case=="node"?new string[]{"read=EACCES","write=EACCES"}:new string[]{"read_type=System.UnauthorizedAccessException","read_hresult=-2147024891","write_type=System.UnauthorizedAccessException","write_hresult=-2147024891"};
            denied=PilotFactExactLines(files,"runtime-canary.txt",expected);
            row.CanaryClassification=denied?"exact_runtime_access_denied":"missing_or_other_runtime_error";
            string canary=PilotFactText(files,"runtime-canary.txt");
            foreach(string line in PilotFactLines(canary))
                {
                    if(line=="read=unexpected_success" || line=="read_type=success") row.OutsideReadObserved=true;
                    if(line=="write=unexpected_success" || line=="write_type=success") row.OutsideWriteObserved=true;
                }
        }
        row.PositivePassed=executed && r.Exit==0 && row.ScriptEntryObserved && row.OutputOk && row.MutationOk &&
            row.OutsideUnchanged && row.OutsideWriteAbsent && !row.OutsideReadObserved && !row.OutsideWriteObserved && (row.Case=="cmd" || denied);
        if(row.OutsideReadObserved || row.OutsideWriteObserved) {row.Fatal=true;row.PositivePassed=false;row.Status="runtime_outside_access_observed";}
        else if(r.Wait==WAIT_TIMEOUT) row.Status="deadline_exceeded";
        else if(!row.ScriptEntryObserved) row.Status=row.KnownStartupStatus==null?"no_script_entry_evidence_inconclusive":"known_startup_status_without_script_entry";
        else if(!row.OutputOk || !row.MutationOk) row.Status="user_code_positive_operation_failed";
        else if(!row.PositivePassed) row.Status="positive_operation_completed_contract_failed";
        else row.Status="positive_operation_completed";
    }
}
