// Explicit CI-only policy: accesscheck_signature_v1_ci. Pure receipt validation.
// This never changes TokenVerified, runs a process, or converts a class-46 error to success.
using System;

public static partial class BrokerDirectLauncher {
    static bool PilotNumber(DirectReceipt r,string key,long expected) {
        long actual;return r.Numbers.TryGetValue(key,out actual) && actual==expected;
    }
    static bool PilotIdentity(DirectReceipt r,string key,string expected) {
        string actual;return r.Identities.TryGetValue(key,out actual) && String.Equals(actual,expected,StringComparison.Ordinal);
    }
    static bool PilotNumbers(DirectReceipt r,string prefix,string[] keys,long[] values) {
        if(keys.Length!=values.Length) return false;
        for(int i=0;i<keys.Length;i++) if(!PilotNumber(r,prefix+keys[i],values[i])) return false;
        return true;
    }
    static bool PilotTokenQuery(DirectReceipt r,string label,bool duplicate,bool dword) {
        long required,returned;
        if(!r.Numbers.TryGetValue(label+"_required_bytes",out required) || required<4 || required>65536 ||
            !r.Numbers.TryGetValue(label+"_returned_bytes",out returned) || returned<4 || returned>required ||
            !PilotNumber(r,label+"_size_error",122) || !PilotNumber(r,label+"_query_error",0)) return false;
        if(dword && (required!=4 || returned!=4)) return false;
        if(duplicate) return PilotNumbers(r,label,new string[]{"_valid","_size_call_success","_query_success","_free_completed"},new long[]{1,0,1,1});
        return PilotNumber(r,label+"_observation_success",1);
    }
    static bool PilotTokenSid(DirectReceipt r,string label,string expected,bool integrity,bool duplicate) {
        if(!PilotTokenQuery(r,label,duplicate,false) || !PilotIdentity(r,label,expected)) return false;
        long returned,offset,length;
        if(!r.Numbers.TryGetValue(label+"_returned_bytes",out returned) ||
            !r.Numbers.TryGetValue(label+"_sid_offset",out offset) ||
            !r.Numbers.TryGetValue(label+"_sid_bytes",out length)) return false;
        int header=integrity?(IntPtr.Size==8?16:8):IntPtr.Size;
        return offset>=header && offset<=returned && length>=8 && length<=68 &&
            (length-8)%4==0 && length<=returned-offset && (!integrity || length==12);
    }
    static bool PilotPinnedMethodDiagnostics(DirectReceipt r) {
        // These remain failed method observations. A changed result requires new review.
        if(!PilotNumbers(r,"",new string[]{
            "lpac_size_call_success","lpac_size_error","lpac_required_bytes","lpac_sizing_expected_insufficient_buffer",
            "lpac_fixed_buffer_bytes","lpac_fixed_initial_value","lpac_fixed_query_success","lpac_fixed_query_error",
            "lpac_fixed_returned_bytes","lpac_fixed_raw_value","lpac_fixed_value_valid","lpac_observation_success",
            "native_queries_observation_only"},
            new long[]{0,87,0,0,4,-1515870811,0,87,0,-1515870811,0,0,1})) return false;
        string[] nativeKeys=new string[]{"_call_completed","_class","_buffer_bytes","_initial_value","_initial_returned_bytes",
            "_ntstatus_signed","_ntstatus_unsigned","_returned_bytes","_raw_value","_buffer_unchanged",
            "_return_length_unchanged","_complete_dword_observed"};
        return PilotNumbers(r,"native_appcontainer",nativeKeys,new long[]{1,29,4,-1515870811,3735928559,0,0,4,1,0,0,1}) &&
            PilotNumbers(r,"native_lpac",nativeKeys,new long[]{1,46,4,-1515870811,3735928559,-1073741821,3221225475,3735928559,-1515870811,1,1,0}) &&
            PilotIdentity(r,"native_appcontainer_ntstatus_hex","00000000") && PilotIdentity(r,"native_lpac_ntstatus_hex","C0000003");
    }
    static bool PilotKnownAccessCheckKey(string key) {
        if(!key.StartsWith("accesscheck_",StringComparison.Ordinal)) return true;
        if(key=="accesscheck_observer_completed" || key=="accesscheck_call_attempts" || key=="accesscheck_observer_cleanup_confirmed") return true;
        foreach(string name in new string[]{"mixed","aap","arap","world"}) {
            string prefix="accesscheck_"+name+"_";
            if(!key.StartsWith(prefix,StringComparison.Ordinal)) continue;
            string suffix=key.Substring(prefix.Length);
            foreach(string field in new string[]{"descriptor_valid","decision_valid","api_called","api_success",
                "access_status_raw","granted_access_raw","privilege_count_raw","privilege_header_valid","error","error_available",
                "sd_revision","sd_control","acl_bytes","ace_count","sacl_present","dacl_present","desired_access_before_mapping",
                "desired_access_after_mapping","mapping_read","mapping_write","mapping_execute","mapping_all","privilege_allocation_bytes",
                "privilege_initial_count","privilege_returned_bytes","privilege_control_raw","privilege_entry_span_bytes","interpreted_granted_access",
                "observation_completed","interpreted_decision","descriptor_identity","owner_sid","group_sid"}) if(suffix==field) return true;
            int aceCount=name=="mixed"?3:(name=="world"?1:2);
            for(int i=0;i<aceCount;i++) {
                foreach(string field in new string[]{"type","flags","bytes","mask","sid"}) if(suffix=="ace_"+i+"_"+field) return true;
                if(suffix=="memory_"+(2+i)+"_free_completed") return true;
            }
            foreach(int slot in new int[]{0,1,5,6,7}) if(suffix=="memory_"+slot+"_free_completed") return true;
            return false; // Includes nested pseudo-labels such as mixed_extra and extra ACEs.
        }
        return false;
    }
    static bool PilotDescriptorDecision(DirectReceipt r,string name,long status,long mask,string[] sids,long[] aceMasks) {
        string p="accesscheck_"+name;
        if(!PilotNumbers(r,p,new string[]{"_descriptor_valid","_decision_valid","_api_called","_api_success",
            "_access_status_raw","_granted_access_raw","_interpreted_granted_access","_observation_completed",
            "_privilege_count_raw","_privilege_header_valid","_privilege_allocation_bytes","_privilege_initial_count",
            "_privilege_entry_span_bytes","_sd_revision","_sd_control","_sacl_present","_dacl_present",
            "_desired_access_before_mapping","_desired_access_after_mapping","_mapping_read","_mapping_write","_mapping_execute","_mapping_all"},
            new long[]{1,1,1,1,status,mask,mask,1,0,1,20,2779096485,8,1,4,0,1,33554432,33554432,0,0,0,0})) return false;
        long privilegeBytes;
        if(!r.Numbers.TryGetValue(p+"_privilege_returned_bytes",out privilegeBytes) || privilegeBytes<8 || privilegeBytes>20) return false;
        if(status==0) {
            if(!PilotNumber(r,p+"_error_available",1) || !PilotNumber(r,p+"_error",5) || mask!=0 ||
                !PilotIdentity(r,p+"_interpreted_decision","denied")) return false;
        } else if(status!=1 || !PilotNumber(r,p+"_error_available",0) || !PilotNumber(r,p+"_error",-1) ||
            !PilotIdentity(r,p+"_interpreted_decision","allowed")) return false;
        if(!PilotIdentity(r,p+"_descriptor_identity","absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;"+name) ||
            !PilotIdentity(r,p+"_owner_sid","S-1-5-18") || !PilotIdentity(r,p+"_group_sid","S-1-5-18") ||
            sids.Length!=aceMasks.Length || !PilotNumber(r,p+"_ace_count",sids.Length)) return false;
        int aclBytes=8;
        for(int i=0;i<sids.Length;i++) {
            int aceBytes=i==0?20:24;aclBytes+=aceBytes;
            string ace=p+"_ace_"+i;
            if(!PilotNumbers(r,ace,new string[]{"_type","_flags","_bytes","_mask"},new long[]{0,0,aceBytes,aceMasks[i]}) ||
                !PilotIdentity(r,ace+"_sid",sids[i]) || !PilotNumber(r,p+"_memory_"+(2+i)+"_free_completed",1)) return false;
        }
        if(!PilotNumber(r,p+"_acl_bytes",aclBytes)) return false;
        foreach(int slot in new int[]{0,1,5,6,7}) if(!PilotNumber(r,p+"_memory_"+slot+"_free_completed",1)) return false;
        return true;
    }
    static bool PilotStdioClosed(DirectReceipt r) {
        if(!r.StdioValidated || !r.HostStdioClosed || r.HandleListCount!=3 || r.StdinKind!="broker_fresh_private_empty_regular_file") return false;
        string writer,input,output,error;
        if(!r.Identities.TryGetValue("stdin_writer",out writer) || String.IsNullOrEmpty(writer) ||
            !r.Identities.TryGetValue("stdin",out input) || !r.Identities.TryGetValue("stdout",out output) ||
            !r.Identities.TryGetValue("stderr",out error) || String.IsNullOrEmpty(input) || String.IsNullOrEmpty(output) ||
            String.IsNullOrEmpty(error) || writer!=input || input==output || input==error || output==error) return false;
        foreach(string label in new string[]{"stdin_writer","stdin","stdout","stderr"}) {
            long attributes;
            if(!PilotNumbers(r,label,new string[]{"_open_error","_close_error","_file_type","_length","_links"},new long[]{0,0,1,0,1}) ||
                !r.Numbers.TryGetValue(label+"_attributes",out attributes) || (attributes&0x410)!=0) return false;
            if(!PilotNumber(r,label+"_handle_flags",label=="stdin_writer"?0:1) ||
                !PilotNumber(r,label+"_desired_access",label=="stdin"?0x80000000L:0x40000000L)) return false;
        }
        foreach(string label in new string[]{"setup_writer_cleanup","setup_stdin_cleanup","setup_stdout_cleanup","setup_stderr_cleanup","setup_attribute_cleanup",
            "setup_heap_0","setup_heap_1","setup_heap_3","setup_heap_4"}) if(!PilotNumber(r,label+"_completed",1)) return false;
        long configured;
        if(!r.Numbers.TryGetValue("configured_lpac_request",out configured) || (configured!=0 && configured!=1)) return false;
        return configured==0?!r.Numbers.ContainsKey("setup_heap_2_completed"):PilotNumber(r,"setup_heap_2_completed",1);
    }
    // Called before assignment/resume, after closing the source token. The coordinator
    // additionally requires its own ownership state and a same-invocation ordinary control.
    // ordinary selects a measured comparison signature, never a requested creation flag.
    static bool VerifyPilotSignature(DirectReceipt r,bool ordinary) {
        if(r==null || r.Numbers==null || r.Identities==null || !r.CreateAttempted || !r.Created || r.CreateError!=0 ||
            r.Assigned || r.Resumed || r.TokenVerified || r.Failure!=null || String.IsNullOrEmpty(r.ProfileSid) ||
            r.CreationFlags!=(CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u) ||
            !PilotStdioClosed(r) || !PilotPinnedMethodDiagnostics(r)) return false;
        // Kind is only a finite-scope guard. The measured masks must distinguish
        // the ordinary control from LPAC, even when checking the same receipt twice.
        if(r.Kind!="ordinary" && r.Kind!="reference" && r.Kind!="node" && r.Kind!="cmd" && r.Kind!="powershell" && r.Kind!="pwsh") return false;
        foreach(string key in r.Numbers.Keys) if(!PilotKnownAccessCheckKey(key)) return false;
        foreach(string key in r.Identities.Keys) if(!PilotKnownAccessCheckKey(key) ||
            key.EndsWith("_exception",StringComparison.Ordinal) || key.EndsWith("_observation_failure",StringComparison.Ordinal)) return false;
        if(!PilotNumbers(r,"",new string[]{"profile_create_hresult","pilot_process_outputs_owned","pilot_copied_bytes_verified",
            "source_token_requested_access","source_token_open_error","source_restricted_properties_verified","token_close_error",
            "source_type_value","appcontainer_value","capabilities_value","duplicate_ownership_confirmed","duplicate_valid","duplicate_api_success","duplicate_error",
            "duplicate_desired_access","duplicate_attributes_null","duplicate_requested_level","duplicate_requested_type","duplicate_handle_flags_success",
            "duplicate_handle_flags_error","duplicate_handle_flags","duplicate_type_value","duplicate_level_value","duplicate_appcontainer_value","duplicate_capabilities_value",
            "duplicate_close_error","accesscheck_observer_completed","accesscheck_observer_cleanup_confirmed","accesscheck_call_attempts"},
            new long[]{0,1,1,10,0,1,0,1,1,0,1,1,1,0,8,1,1,2,1,0,0,2,1,1,0,0,1,1,4})) return false;
        foreach(string label in new string[]{"source_type","appcontainer","capabilities"})
            if(!PilotTokenQuery(r,label,false,label!="capabilities")) return false;
        foreach(string label in new string[]{"duplicate_type","duplicate_level","duplicate_appcontainer","duplicate_capabilities"})
            if(!PilotTokenQuery(r,label,true,label!="duplicate_capabilities")) return false;
        if(!PilotTokenSid(r,"appcontainer_sid",r.ProfileSid,false,false) || !PilotTokenSid(r,"integrity_sid","S-1-16-4096",true,false) ||
            !PilotTokenSid(r,"duplicate_appcontainer_sid",r.ProfileSid,false,true) || !PilotTokenSid(r,"duplicate_integrity_sid","S-1-16-4096",true,true)) return false;
        return PilotDescriptorDecision(r,"mixed",1,ordinary?3:2,new string[]{"S-1-1-0","S-1-15-2-1","S-1-15-2-2"},new long[]{3,1,2}) &&
            PilotDescriptorDecision(r,"aap",ordinary?1:0,ordinary?1:0,new string[]{"S-1-1-0","S-1-15-2-1"},new long[]{1,1}) &&
            PilotDescriptorDecision(r,"arap",1,2,new string[]{"S-1-1-0","S-1-15-2-2"},new long[]{2,2}) &&
            PilotDescriptorDecision(r,"world",0,0,new string[]{"S-1-1-0"},new long[]{3});
    }
}
