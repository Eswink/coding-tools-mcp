// Managed-only candidate classification/adapter tests. Injected operations do no OS I/O.
using System;
using System.ComponentModel;

public static partial class BrokerDirectLauncher {
    sealed class ParentCandidateTestTrace {
        public string Mode;
        public int Opens,Inspections,Checks,Closes;
    }
    static void ParentCandidateAssert(bool value,string label,ref int count) {
        if(!value) throw new InvalidOperationException("parent candidate contract: "+label);
        count++;
    }
    static void ParentCandidateTestReceipt(DirectReceipt r,string label) {
        r.Numbers[label+"_open_error"]=0;r.Numbers[label+"_desired_access"]=0x00020081;r.Numbers[label+"_handle_flags"]=0;
        r.Numbers[label+"_security_size_error"]=122;r.Numbers[label+"_security_read_error"]=0;r.Numbers[label+"_security_free_confirmed"]=1;
        r.Numbers[label+"_broker_owner_query_confirmed"]=1;r.Numbers[label+"_broker_owner_token_desired_access"]=8;
        r.Numbers[label+"_broker_owner_token_open_success"]=1;r.Numbers[label+"_broker_owner_token_open_error"]=0;
        r.Numbers[label+"_broker_owner_token_unowned_output"]=0;r.Numbers[label+"_broker_owner_handle_query_success"]=1;
        r.Numbers[label+"_broker_owner_handle_query_error"]=0;r.Numbers[label+"_broker_owner_handle_flags"]=0;
        r.Numbers[label+"_broker_owner_size_success"]=0;r.Numbers[label+"_broker_owner_size_error"]=122;
        r.Numbers[label+"_broker_owner_required_bytes"]=64;r.Numbers[label+"_broker_owner_read_success"]=1;
        r.Numbers[label+"_broker_owner_read_error"]=0;r.Numbers[label+"_broker_owner_returned_bytes"]=64;
        r.Numbers[label+"_broker_owner_data_free_confirmed"]=1;r.Numbers[label+"_broker_owner_token_close_confirmed"]=1;
        r.Numbers[label+"_broker_owner_token_close_error"]=0;r.Numbers[label+"_broker_owned"]=1;
        r.Identities[label+"_owner_category"]="current_broker";r.Numbers[label+"_security_control_flags"]=32772;
        r.Numbers[label+"_dacl_ace_count"]=2;r.Numbers[label+"_acl_observed_ace_count"]=2;r.Numbers[label+"_acl_observation_completed"]=1;
        r.Numbers[label+"_first_rejected_ace_index"]=-1;r.Identities[label+"_first_rejected_reason"]="none";
        for(int index=0;index<2;index++) {
            string ace=label+"_ace_"+index;
            r.Identities[ace+"_type"]="CommonAce";r.Numbers[ace+"_native_type"]=0;r.Numbers[ace+"_flags"]=3;
            r.Numbers[ace+"_access_mask"]=0x1F01FF;r.Identities[ace+"_sid_category"]=index==0?"current_broker":"system";
            r.Numbers[ace+"_qualifier"]=0;r.Numbers[ace+"_callback"]=0;
        }
    }
    static ParentCandidateBatch ParentCandidateTestBatch() {
        var batch=new ParentCandidateBatch();batch.Rows=new ParentCandidateRow[3];
        string[] labels={"runner_temp_control","local_application_data","local_application_data_temp"};
        for(int index=0;index<3;index++) batch.Rows[index]=new ParentCandidateRow {
            Label=labels[index],PathValidated=true,RequestedPath="C:\\Fixture\\candidate"+index,ValidatedPath="C:\\Fixture\\candidate"+index
        };
        return batch;
    }
    static ParentCandidateOperations ParentCandidateTestOperations(ParentCandidateTestTrace trace) {
        return new ParentCandidateOperations {
            Open=delegate(ref IntPtr handle,string path,string label,DirectReceipt r) {
                trace.Opens++;r.Numbers[label+"_open_error"]=0;
                if(trace.Opens==1 && (trace.Mode=="missing2" || trace.Mode=="missing3" || trace.Mode=="open_denied")) {
                    int error=trace.Mode=="missing2"?2:trace.Mode=="missing3"?3:5;r.Numbers[label+"_open_error"]=error;
                    throw new Win32Exception(error,"injected initial open");
                }
                if(trace.Opens==1 && trace.Mode=="null_open") return;
                handle=new IntPtr(100+trace.Opens);
                if(trace.Opens==1 && trace.Mode=="post_open_error2") throw new Win32Exception(2,"injected handle-information failure");
            },
            Inspect=delegate(IntPtr handle,string path,string identity,uint? volume) {
                trace.Inspections++;var info=new FILE_INFO();info.attributes=0x10;info.volume=7;info.indexLow=19;
                if(trace.Opens==1 && trace.Mode=="object_rejected" && identity==null)
                    throw new InvalidOperationException("pilot link, nonregular object, or volume mismatch");
                if(trace.Opens==1 && trace.Mode=="final_error2" && identity!=null) throw new Win32Exception(2,"injected final identity failure");
                if(trace.Opens==1 && trace.Mode=="identity_changed" && identity!=null) info.indexLow=20;
                return info;
            },
            CheckParent=delegate(IntPtr handle,string path,string identity,string label,DirectReceipt r) {
                trace.Checks++;ParentCandidateTestReceipt(r,label);
                if(trace.Opens!=1) return;
                if(trace.Mode=="missing_free") r.Numbers.Remove(label+"_security_free_confirmed");
                if(trace.Mode=="unknown_output") r.Numbers[label+"_broker_owner_token_unowned_output"]=1;
                if(trace.Mode=="incomplete_acl") r.Numbers.Remove(label+"_ace_1_flags");
                if(trace.Mode=="stale_success") throw new InvalidOperationException("injected checker failure after stale success field");
                if(trace.Mode=="checker_error2") throw new Win32Exception(2,"injected later API failure");
                if(trace.Mode=="trust_rejected" || trace.Mode=="rejection_free_failed" || trace.Mode=="rejection_missing_index") {
                    r.Numbers[label+"_broker_owned"]=0;r.Numbers[label+"_first_rejected_ace_index"]=1;
                    r.Identities[label+"_first_rejected_reason"]="untrusted_write_grant";
                    r.Identities[label+"_ace_1_sid_category"]="creator_owner";r.Numbers[label+"_ace_1_flags"]=0x0B;
                    r.Numbers[label+"_ace_1_access_mask"]=0x10000000;
                    if(trace.Mode=="rejection_free_failed") r.Numbers[label+"_security_free_confirmed"]=0;
                    if(trace.Mode=="rejection_missing_index") r.Numbers.Remove(label+"_first_rejected_ace_index");
                    throw new InvalidOperationException("pilot parent has an untrusted write grant");
                }
            },
            Close=delegate(ref IntPtr handle,string label,DirectReceipt r) {
                trace.Closes++;bool owned=handle!=IntPtr.Zero;handle=IntPtr.Zero;
                if(trace.Opens==1 && trace.Mode=="close_throw") throw new InvalidOperationException("injected close exception");
                bool result=!(trace.Opens==1 && trace.Mode=="close_false");
                r.Numbers[label+"_close_confirmed"]=result?1:0;if(owned) r.Numbers[label+"_close_error"]=result?0:6;
                return result;
            }
        };
    }
    public static int RunParentCandidateContractTests() {
        int count=0;
        foreach(string path in new string[]{null,"","C:","C:\\","relative","\\\\server\\share","\\\\?\\C:\\path","C:/path","C:\\a\\..\\b","C:\\a\\.\\b","C:\\a\\b.","C:\\a\\b ","C:\\a:stream","C:\\a\\\\b","C:\\a\n",
            "C:\\NUL","C:\\temp\\CON.txt","C:\\AUX\\Temp","C:\\COM1.txt","C:\\LPT9","C:\\COM\u00b9","C:\\LPT\u00b2.txt","C:\\CONIN$","C:\\a\ud800","C:\\a\udc00"})
            ParentCandidateAssert(!ParentCandidatePathSyntax(path),"reject path syntax",ref count);
        foreach(string path in new string[]{"C:\\Users\\runner\\AppData\\Local","D:\\a\\_temp","C:\\Data\\Temp"})
            ParentCandidateAssert(ParentCandidatePathSyntax(path),"accept exact local syntax",ref count);
        ParentCandidateBatch plan=PrepareParentCandidateBatch("C:\\Fixture\\Local","C:\\Fixture\\Local",null);
        ParentCandidateAssert(plan.Rows.Length==3 && plan.Rows[0].Label=="runner_temp_control" && plan.Rows[1].Label=="local_application_data" &&
            plan.Rows[2].Label=="local_application_data_temp","exact fixed order",ref count);
        ParentCandidateAssert(plan.Rows[1].PathOption=="DoNotVerify" && plan.Rows[2].PathOption=="literal_child","fixed path sources",ref count);
        ParentCandidateAssert(plan.Rows[2].PathValidated && plan.Rows[2].ValidatedPath=="C:\\Fixture\\Local\\Temp" &&
            System.IO.Path.GetDirectoryName(plan.Rows[2].ValidatedPath)==plan.Rows[1].ValidatedPath,"literal Temp containment",ref count);
        ParentCandidateAssert(plan.Rows[1].AliasOf=="runner_temp_control" && plan.Rows[2].AliasOf==null,"base alias labeled without replacement",ref count);
        plan=PrepareParentCandidateBatch("C:\\Fixture\\Local\\Temp","C:\\Fixture\\Local",null);
        ParentCandidateAssert(plan.Rows[2].AliasOf=="runner_temp_control" && plan.Rows[1].AliasOf==null,"Temp alias labeled without replacement",ref count);
        foreach(string unavailable in new string[]{null,"","\\\\server\\share","C:\\NUL","C:\\Fixture\\CON.txt","C:\\Fixture\\a\ud800"}) {
            var trace=new ParentCandidateTestTrace {Mode="pass"};plan=PrepareParentCandidateBatch("C:\\Fixture\\Runner",unavailable,null);
            RunParentCandidateObservations(plan,ParentCandidateTestOperations(trace));
            ParentCandidateAssert(!plan.Rows[1].PathValidated && !plan.Rows[2].PathValidated && plan.Rows[2].RequestedPath==null,
                "unvalidated base cannot form a child",ref count);
            ParentCandidateAssert(trace.Opens==1 && plan.ObservationCompleted && !plan.Rows[1].InitialOpenMissing && !plan.Rows[2].InitialOpenMissing,
                "unavailable base and child never opened or reported missing",ref count);
        }
        var lookupTrace=new ParentCandidateTestTrace {Mode="pass"};plan=PrepareParentCandidateBatch("C:\\Fixture\\Runner","C:\\Fixture\\Local","injected path lookup failure");
        RunParentCandidateObservations(plan,ParentCandidateTestOperations(lookupTrace));
        ParentCandidateAssert(!plan.ObservationCompleted && lookupTrace.Opens==1 && plan.Rows[1].Outcome=="path_lookup_failed" &&
            plan.Rows[2].Outcome=="not_attempted_prior_uncertainty","lookup exception stops later fixed row",ref count);
        foreach(string mode in new string[]{"pass","trust_rejected","missing2","missing3"}) {
            var trace=new ParentCandidateTestTrace {Mode=mode};var batch=RunParentCandidateObservations(ParentCandidateTestBatch(),ParentCandidateTestOperations(trace));
            ParentCandidateAssert(batch.Rows.Length==3 && trace.Opens==3 && trace.Closes==3,"finite completed sequence "+mode,ref count);
            ParentCandidateAssert(batch.ObservationCompleted && batch.CleanupConfirmed,"completed clean batch "+mode,ref count);
            ParentCandidateAssert(batch.Rows[0].CandidateTrustVerified==(mode=="pass"),"trust separate from completion "+mode,ref count);
            ParentCandidateAssert(!batch.selection_made && !batch.selected_for_execution && !batch.pilot_invoked && batch.observation_only,"observation constants",ref count);
            ParentCandidateAssert(batch.created_directory_count==0 && batch.created_profile_count==0 && batch.created_process_count==0,"zero creation constants",ref count);
            if(mode=="trust_rejected") {
                ParentCandidateAssert(batch.Rows[0].FinalIdentityRechecked && trace.Inspections==6,"rejected parent rechecked",ref count);
                ParentCandidateAssert(batch.Rows[0].Checker.Numbers[batch.Rows[0].Label+"_ace_1_access_mask"]==0x10000000 &&
                    batch.Rows[0].Checker.Numbers[batch.Rows[0].Label+"_ace_1_flags"]==0x0B,"preserve rejected raw ACL",ref count);
            }
            if(mode.StartsWith("missing",StringComparison.Ordinal)) ParentCandidateAssert(batch.Rows[0].InitialOpenMissing && trace.Checks==2,"only missing row skips checker",ref count);
        }
        foreach(string mode in new string[]{"open_denied","null_open","post_open_error2","object_rejected","final_error2","identity_changed","missing_free","unknown_output","incomplete_acl","stale_success","checker_error2","rejection_free_failed","rejection_missing_index","close_throw","close_false"}) {
            var trace=new ParentCandidateTestTrace {Mode=mode};var batch=RunParentCandidateObservations(ParentCandidateTestBatch(),ParentCandidateTestOperations(trace));
            ParentCandidateAssert(!batch.ObservationCompleted && !batch.Rows[0].CandidateTrustVerified,"failure cannot pass "+mode,ref count);
            ParentCandidateAssert(trace.Opens==1 && trace.Closes==1,"no subsequent observation or close retry "+mode,ref count);
            ParentCandidateAssert(batch.Rows[1].Outcome=="not_attempted_prior_uncertainty" && batch.Rows[2].Outcome=="not_attempted_prior_uncertainty","explicit blocked rows "+mode,ref count);
            ParentCandidateAssert(!batch.Rows[0].InitialOpenMissing,"later failure is not absence "+mode,ref count);
        }
        string[] required={"_broker_owned","_acl_observation_completed","_dacl_ace_count","_acl_observed_ace_count","_broker_owner_query_confirmed",
            "_broker_owner_data_free_confirmed","_broker_owner_token_close_confirmed","_broker_owner_token_close_error","_security_free_confirmed",
            "_close_confirmed","_close_error","_ace_0_native_type","_ace_0_flags","_ace_0_access_mask","_ace_0_qualifier","_ace_0_callback",
            "_security_control_flags","_first_rejected_ace_index","_broker_owner_token_open_success","_broker_owner_token_desired_access",
            "_broker_owner_token_unowned_output","_broker_owner_handle_flags","_broker_owner_read_success","_broker_owner_returned_bytes"};
        foreach(string suffix in required) {
            var trace=new ParentCandidateTestTrace {Mode="pass"};ParentCandidateRow row=RunParentCandidateObservations(ParentCandidateTestBatch(),ParentCandidateTestOperations(trace)).Rows[0];
            row.Checker.Numbers.Remove(row.Label+suffix);FinalizeParentCandidateRow(row,true);
            ParentCandidateAssert(!row.CandidateTrustVerified,"missing receipt rejects "+suffix,ref count);
        }
        foreach(string category in new string[]{null,"unresolved_guess"}) {
            var trace=new ParentCandidateTestTrace {Mode="pass"};ParentCandidateRow row=RunParentCandidateObservations(ParentCandidateTestBatch(),ParentCandidateTestOperations(trace)).Rows[0];
            if(category==null) row.Checker.Identities.Remove(row.Label+"_owner_category");
            else row.Checker.Identities[row.Label+"_owner_category"]=category;
            FinalizeParentCandidateRow(row,true);
            ParentCandidateAssert(!row.CandidateTrustVerified && !row.ObservationCompleted,"missing or invalid owner evidence rejected",ref count);
        }
        foreach(string preparation in new string[]{"path_unavailable","path_rejected","parent_path_unavailable","path_lookup_failed","path_validation_uncertain"}) {
            var trace=new ParentCandidateTestTrace {Mode="pass"};var batch=ParentCandidateTestBatch();batch.Rows[0].PathValidated=false;batch.Rows[0].PreparationFailure=preparation;
            RunParentCandidateObservations(batch,ParentCandidateTestOperations(trace));
            bool normal=preparation=="path_unavailable" || preparation=="path_rejected" || preparation=="parent_path_unavailable";
            ParentCandidateAssert(batch.ObservationCompleted==normal && trace.Opens==(normal?2:0),"path failure opens no unvalidated target "+preparation,ref count);
            ParentCandidateAssert(!batch.Rows[0].InitialOpenMissing && !batch.Rows[0].CandidateTrustVerified,"unresolved path is not absence/pass",ref count);
        }
        return count;
    }
}
