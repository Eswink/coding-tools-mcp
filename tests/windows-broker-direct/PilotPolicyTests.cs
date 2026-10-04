// Managed-only policy contract tests. No Windows/token/process/file APIs are called.
using System;
using System.Globalization;
public static partial class BrokerDirectLauncher {
    static DirectReceipt PilotPolicyTestReceipt(bool ordinary) {
        var r=new DirectReceipt();r.Kind=ordinary?"ordinary":"reference";r.CreateAttempted=true;r.Created=true;r.CreateError=0;
        r.StdioValidated=true;r.HostStdioClosed=true;r.HandleListCount=3;r.ProfileSid="S-1-15-2-1-2-3-4-5-6-7";
        r.ExecutableSha256="45216b87a18180c292ca6f490e0f7163c914958f07155269eabea9db5d807527";
        string numeric=
            "profile_create_hresult=0;stdin_writer_open_error=0;stdin_writer_desired_access=1073741824;stdin_writer_handle_flags=0;"+
            "stdin_writer_file_type=1;stdin_writer_attributes=32;stdin_writer_length=0;stdin_writer_links=1;"+
            "stdin_writer_close_error=0;stdin_open_error=0;stdin_desired_access=2147483648;stdin_handle_flags=1;"+
            "stdin_file_type=1;stdin_attributes=32;stdin_length=0;stdin_links=1;"+
            "stdout_open_error=0;stdout_desired_access=1073741824;stdout_handle_flags=1;stdout_file_type=1;"+
            "stdout_attributes=32;stdout_length=0;stdout_links=1;stderr_open_error=0;"+
            "stderr_desired_access=1073741824;stderr_handle_flags=1;stderr_file_type=1;stderr_attributes=32;"+
            "stderr_length=0;stderr_links=1;configured_lpac_request=1;setup_writer_cleanup_completed=1;"+
            "stdin_close_error=0;setup_stdin_cleanup_completed=1;stdout_close_error=0;setup_stdout_cleanup_completed=1;"+
            "stderr_close_error=0;setup_stderr_cleanup_completed=1;setup_attribute_cleanup_completed=1;setup_heap_0_completed=1;"+
            "setup_heap_1_completed=1;setup_heap_2_completed=1;setup_heap_3_completed=1;setup_heap_4_completed=1;"+
            "source_token_requested_access=10;source_token_open_error=0;source_type_size_error=122;source_type_required_bytes=4;"+
            "source_type_query_error=0;source_type_returned_bytes=4;source_type_value=1;source_type_observation_success=1;"+
            "appcontainer_size_error=122;appcontainer_required_bytes=4;appcontainer_query_error=0;appcontainer_returned_bytes=4;"+
            "appcontainer_value=1;appcontainer_observation_success=1;lpac_size_call_success=0;lpac_size_error=87;"+
            "lpac_required_bytes=0;lpac_sizing_expected_insufficient_buffer=0;lpac_fixed_buffer_bytes=4;lpac_fixed_initial_value=-1515870811;"+
            "lpac_fixed_query_success=0;lpac_fixed_query_error=87;lpac_fixed_returned_bytes=0;lpac_fixed_raw_value=-1515870811;"+
            "lpac_fixed_value_valid=0;lpac_observation_success=0;capabilities_size_error=122;capabilities_required_bytes=8;"+
            "capabilities_query_error=0;capabilities_returned_bytes=8;capabilities_value=0;capabilities_observation_success=1;"+
            "appcontainer_sid_size_error=122;appcontainer_sid_required_bytes=48;appcontainer_sid_query_error=0;appcontainer_sid_returned_bytes=48;"+
            "appcontainer_sid_sid_bytes=40;appcontainer_sid_sid_offset=8;appcontainer_sid_observation_success=1;integrity_sid_size_error=122;"+
            "integrity_sid_required_bytes=28;integrity_sid_query_error=0;integrity_sid_returned_bytes=28;integrity_sid_sid_bytes=12;"+
            "integrity_sid_sid_offset=16;integrity_sid_observation_success=1;source_restricted_properties_verified=1;native_queries_observation_only=1;"+
            "native_appcontainer_call_completed=1;native_appcontainer_class=29;native_appcontainer_buffer_bytes=4;native_appcontainer_initial_value=-1515870811;"+
            "native_appcontainer_initial_returned_bytes=3735928559;native_appcontainer_ntstatus_signed=0;native_appcontainer_ntstatus_unsigned=0;native_appcontainer_returned_bytes=4;"+
            "native_appcontainer_raw_value=1;native_appcontainer_buffer_unchanged=0;native_appcontainer_return_length_unchanged=0;native_appcontainer_complete_dword_observed=1;"+
            "native_lpac_call_completed=1;native_lpac_class=46;native_lpac_buffer_bytes=4;native_lpac_initial_value=-1515870811;"+
            "native_lpac_initial_returned_bytes=3735928559;native_lpac_ntstatus_signed=-1073741821;native_lpac_ntstatus_unsigned=3221225475;native_lpac_returned_bytes=3735928559;"+
            "native_lpac_raw_value=-1515870811;native_lpac_buffer_unchanged=1;native_lpac_return_length_unchanged=1;native_lpac_complete_dword_observed=0;"+
            "duplicate_valid=1;accesscheck_observer_completed=1;duplicate_ownership_confirmed=1;accesscheck_call_attempts=4;"+
            "accesscheck_observer_cleanup_confirmed=1;duplicate_desired_access=8;duplicate_attributes_null=1;duplicate_requested_level=1;"+
            "duplicate_requested_type=2;duplicate_api_success=1;duplicate_error=0;duplicate_handle_flags_success=1;"+
            "duplicate_handle_flags_error=0;duplicate_handle_flags=0;duplicate_type_valid=1;duplicate_type_size_call_success=0;"+
            "duplicate_type_size_error=122;duplicate_type_required_bytes=4;duplicate_type_query_success=1;duplicate_type_query_error=0;"+
            "duplicate_type_returned_bytes=4;duplicate_type_value=2;duplicate_type_free_completed=1;duplicate_level_valid=1;"+
            "duplicate_level_size_call_success=0;duplicate_level_size_error=122;duplicate_level_required_bytes=4;duplicate_level_query_success=1;"+
            "duplicate_level_query_error=0;duplicate_level_returned_bytes=4;duplicate_level_value=1;duplicate_level_free_completed=1;"+
            "duplicate_appcontainer_valid=1;duplicate_appcontainer_size_call_success=0;duplicate_appcontainer_size_error=122;duplicate_appcontainer_required_bytes=4;"+
            "duplicate_appcontainer_query_success=1;duplicate_appcontainer_query_error=0;duplicate_appcontainer_returned_bytes=4;duplicate_appcontainer_value=1;"+
            "duplicate_appcontainer_free_completed=1;duplicate_capabilities_valid=1;duplicate_capabilities_size_call_success=0;duplicate_capabilities_size_error=122;"+
            "duplicate_capabilities_required_bytes=8;duplicate_capabilities_query_success=1;duplicate_capabilities_query_error=0;duplicate_capabilities_returned_bytes=8;"+
            "duplicate_capabilities_value=0;duplicate_capabilities_free_completed=1;duplicate_appcontainer_sid_valid=1;duplicate_appcontainer_sid_size_call_success=0;"+
            "duplicate_appcontainer_sid_size_error=122;duplicate_appcontainer_sid_required_bytes=48;duplicate_appcontainer_sid_query_success=1;duplicate_appcontainer_sid_query_error=0;"+
            "duplicate_appcontainer_sid_returned_bytes=48;duplicate_appcontainer_sid_sid_bytes=40;duplicate_appcontainer_sid_sid_offset=8;duplicate_appcontainer_sid_free_completed=1;"+
            "duplicate_integrity_sid_valid=1;duplicate_integrity_sid_size_call_success=0;duplicate_integrity_sid_size_error=122;duplicate_integrity_sid_required_bytes=28;"+
            "duplicate_integrity_sid_query_success=1;duplicate_integrity_sid_query_error=0;duplicate_integrity_sid_returned_bytes=28;duplicate_integrity_sid_sid_bytes=12;"+
            "duplicate_integrity_sid_sid_offset=16;duplicate_integrity_sid_free_completed=1;accesscheck_mixed_descriptor_valid=1;accesscheck_mixed_decision_valid=1;"+
            "accesscheck_mixed_api_called=1;accesscheck_mixed_api_success=1;accesscheck_mixed_access_status_raw=1;accesscheck_mixed_granted_access_raw=2;"+
            "accesscheck_mixed_privilege_count_raw=0;accesscheck_mixed_privilege_header_valid=1;accesscheck_mixed_error=-1;accesscheck_mixed_error_available=0;"+
            "accesscheck_mixed_sd_revision=1;accesscheck_mixed_sd_control=4;accesscheck_mixed_acl_bytes=76;accesscheck_mixed_ace_count=3;"+
            "accesscheck_mixed_ace_0_type=0;accesscheck_mixed_ace_0_flags=0;accesscheck_mixed_ace_0_bytes=20;accesscheck_mixed_ace_0_mask=3;"+
            "accesscheck_mixed_ace_1_type=0;accesscheck_mixed_ace_1_flags=0;accesscheck_mixed_ace_1_bytes=24;accesscheck_mixed_ace_1_mask=1;"+
            "accesscheck_mixed_ace_2_type=0;accesscheck_mixed_ace_2_flags=0;accesscheck_mixed_ace_2_bytes=24;accesscheck_mixed_ace_2_mask=2;"+
            "accesscheck_mixed_sacl_present=0;accesscheck_mixed_dacl_present=1;accesscheck_mixed_desired_access_before_mapping=33554432;accesscheck_mixed_desired_access_after_mapping=33554432;"+
            "accesscheck_mixed_mapping_read=0;accesscheck_mixed_mapping_write=0;accesscheck_mixed_mapping_execute=0;accesscheck_mixed_mapping_all=0;"+
            "accesscheck_mixed_privilege_allocation_bytes=20;accesscheck_mixed_privilege_initial_count=2779096485;accesscheck_mixed_privilege_returned_bytes=20;accesscheck_mixed_privilege_control_raw=0;"+
            "accesscheck_mixed_privilege_entry_span_bytes=8;accesscheck_mixed_interpreted_granted_access=2;accesscheck_mixed_memory_7_free_completed=1;accesscheck_mixed_memory_6_free_completed=1;"+
            "accesscheck_mixed_memory_5_free_completed=1;accesscheck_mixed_memory_4_free_completed=1;accesscheck_mixed_memory_3_free_completed=1;accesscheck_mixed_memory_2_free_completed=1;"+
            "accesscheck_mixed_memory_1_free_completed=1;accesscheck_mixed_memory_0_free_completed=1;accesscheck_mixed_observation_completed=1;accesscheck_aap_descriptor_valid=1;"+
            "accesscheck_aap_decision_valid=1;accesscheck_aap_api_called=1;accesscheck_aap_api_success=1;accesscheck_aap_access_status_raw=0;"+
            "accesscheck_aap_granted_access_raw=0;accesscheck_aap_privilege_count_raw=0;accesscheck_aap_privilege_header_valid=1;accesscheck_aap_error=5;"+
            "accesscheck_aap_error_available=1;accesscheck_aap_sd_revision=1;accesscheck_aap_sd_control=4;accesscheck_aap_acl_bytes=52;"+
            "accesscheck_aap_ace_count=2;accesscheck_aap_ace_0_type=0;accesscheck_aap_ace_0_flags=0;accesscheck_aap_ace_0_bytes=20;"+
            "accesscheck_aap_ace_0_mask=1;accesscheck_aap_ace_1_type=0;accesscheck_aap_ace_1_flags=0;accesscheck_aap_ace_1_bytes=24;"+
            "accesscheck_aap_ace_1_mask=1;accesscheck_aap_sacl_present=0;accesscheck_aap_dacl_present=1;accesscheck_aap_desired_access_before_mapping=33554432;"+
            "accesscheck_aap_desired_access_after_mapping=33554432;accesscheck_aap_mapping_read=0;accesscheck_aap_mapping_write=0;accesscheck_aap_mapping_execute=0;"+
            "accesscheck_aap_mapping_all=0;accesscheck_aap_privilege_allocation_bytes=20;accesscheck_aap_privilege_initial_count=2779096485;accesscheck_aap_privilege_returned_bytes=20;"+
            "accesscheck_aap_privilege_control_raw=0;accesscheck_aap_privilege_entry_span_bytes=8;accesscheck_aap_interpreted_granted_access=0;accesscheck_aap_memory_7_free_completed=1;"+
            "accesscheck_aap_memory_6_free_completed=1;accesscheck_aap_memory_5_free_completed=1;accesscheck_aap_memory_3_free_completed=1;accesscheck_aap_memory_2_free_completed=1;"+
            "accesscheck_aap_memory_1_free_completed=1;accesscheck_aap_memory_0_free_completed=1;accesscheck_aap_observation_completed=1;accesscheck_arap_descriptor_valid=1;"+
            "accesscheck_arap_decision_valid=1;accesscheck_arap_api_called=1;accesscheck_arap_api_success=1;accesscheck_arap_access_status_raw=1;"+
            "accesscheck_arap_granted_access_raw=2;accesscheck_arap_privilege_count_raw=0;accesscheck_arap_privilege_header_valid=1;accesscheck_arap_error=-1;"+
            "accesscheck_arap_error_available=0;accesscheck_arap_sd_revision=1;accesscheck_arap_sd_control=4;accesscheck_arap_acl_bytes=52;"+
            "accesscheck_arap_ace_count=2;accesscheck_arap_ace_0_type=0;accesscheck_arap_ace_0_flags=0;accesscheck_arap_ace_0_bytes=20;"+
            "accesscheck_arap_ace_0_mask=2;accesscheck_arap_ace_1_type=0;accesscheck_arap_ace_1_flags=0;accesscheck_arap_ace_1_bytes=24;"+
            "accesscheck_arap_ace_1_mask=2;accesscheck_arap_sacl_present=0;accesscheck_arap_dacl_present=1;accesscheck_arap_desired_access_before_mapping=33554432;"+
            "accesscheck_arap_desired_access_after_mapping=33554432;accesscheck_arap_mapping_read=0;accesscheck_arap_mapping_write=0;accesscheck_arap_mapping_execute=0;"+
            "accesscheck_arap_mapping_all=0;accesscheck_arap_privilege_allocation_bytes=20;accesscheck_arap_privilege_initial_count=2779096485;accesscheck_arap_privilege_returned_bytes=20;"+
            "accesscheck_arap_privilege_control_raw=0;accesscheck_arap_privilege_entry_span_bytes=8;accesscheck_arap_interpreted_granted_access=2;accesscheck_arap_memory_7_free_completed=1;"+
            "accesscheck_arap_memory_6_free_completed=1;accesscheck_arap_memory_5_free_completed=1;accesscheck_arap_memory_3_free_completed=1;accesscheck_arap_memory_2_free_completed=1;"+
            "accesscheck_arap_memory_1_free_completed=1;accesscheck_arap_memory_0_free_completed=1;accesscheck_arap_observation_completed=1;accesscheck_world_descriptor_valid=1;"+
            "accesscheck_world_decision_valid=1;accesscheck_world_api_called=1;accesscheck_world_api_success=1;accesscheck_world_access_status_raw=0;"+
            "accesscheck_world_granted_access_raw=0;accesscheck_world_privilege_count_raw=0;accesscheck_world_privilege_header_valid=1;accesscheck_world_error=5;"+
            "accesscheck_world_error_available=1;accesscheck_world_sd_revision=1;accesscheck_world_sd_control=4;accesscheck_world_acl_bytes=28;"+
            "accesscheck_world_ace_count=1;accesscheck_world_ace_0_type=0;accesscheck_world_ace_0_flags=0;accesscheck_world_ace_0_bytes=20;"+
            "accesscheck_world_ace_0_mask=3;accesscheck_world_sacl_present=0;accesscheck_world_dacl_present=1;accesscheck_world_desired_access_before_mapping=33554432;"+
            "accesscheck_world_desired_access_after_mapping=33554432;accesscheck_world_mapping_read=0;accesscheck_world_mapping_write=0;accesscheck_world_mapping_execute=0;"+
            "accesscheck_world_mapping_all=0;accesscheck_world_privilege_allocation_bytes=20;accesscheck_world_privilege_initial_count=2779096485;accesscheck_world_privilege_returned_bytes=20;"+
            "accesscheck_world_privilege_control_raw=0;accesscheck_world_privilege_entry_span_bytes=8;accesscheck_world_interpreted_granted_access=0;accesscheck_world_memory_7_free_completed=1;"+
            "accesscheck_world_memory_6_free_completed=1;accesscheck_world_memory_5_free_completed=1;accesscheck_world_memory_2_free_completed=1;accesscheck_world_memory_1_free_completed=1;"+
            "accesscheck_world_memory_0_free_completed=1;accesscheck_world_observation_completed=1;duplicate_close_error=0;token_close_error=0;"+
            "exact_process_stop_confirmed=1;pilot_process_outputs_owned=1;pilot_copied_bytes_verified=1;";
        foreach(string item in numeric.Split(new char[]{';'},StringSplitOptions.RemoveEmptyEntries)) {
            int separator=item.IndexOf('=');r.Numbers[item.Substring(0,separator)]=Int64.Parse(item.Substring(separator+1),CultureInfo.InvariantCulture);
        }
        r.Identities["fixture_source_sha256"]="45216b87a18180c292ca6f490e0f7163c914958f07155269eabea9db5d807527";
        r.Identities["stdin_writer"]="1:1:1";
        r.Identities["stdin"]="1:1:1";
        r.Identities["stdout"]="1:1:2";
        r.Identities["stderr"]="1:1:3";
        r.Identities["appcontainer_sid"]="S-1-15-2-1-2-3-4-5-6-7";
        r.Identities["integrity_sid"]="S-1-16-4096";
        r.Identities["native_appcontainer_ntstatus_hex"]="00000000";
        r.Identities["native_lpac_ntstatus_hex"]="C0000003";
        r.Identities["duplicate_appcontainer_sid"]="S-1-15-2-1-2-3-4-5-6-7";
        r.Identities["duplicate_integrity_sid"]="S-1-16-4096";
        r.Identities["accesscheck_mixed_interpreted_decision"]="allowed";
        r.Identities["accesscheck_mixed_descriptor_identity"]="absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;mixed";
        r.Identities["accesscheck_mixed_owner_sid"]="S-1-5-18";
        r.Identities["accesscheck_mixed_group_sid"]="S-1-5-18";
        r.Identities["accesscheck_mixed_ace_0_sid"]="S-1-1-0";
        r.Identities["accesscheck_mixed_ace_1_sid"]="S-1-15-2-1";
        r.Identities["accesscheck_mixed_ace_2_sid"]="S-1-15-2-2";
        r.Identities["accesscheck_aap_interpreted_decision"]="denied";
        r.Identities["accesscheck_aap_descriptor_identity"]="absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;aap";
        r.Identities["accesscheck_aap_owner_sid"]="S-1-5-18";
        r.Identities["accesscheck_aap_group_sid"]="S-1-5-18";
        r.Identities["accesscheck_aap_ace_0_sid"]="S-1-1-0";
        r.Identities["accesscheck_aap_ace_1_sid"]="S-1-15-2-1";
        r.Identities["accesscheck_arap_interpreted_decision"]="allowed";
        r.Identities["accesscheck_arap_descriptor_identity"]="absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;arap";
        r.Identities["accesscheck_arap_owner_sid"]="S-1-5-18";
        r.Identities["accesscheck_arap_group_sid"]="S-1-5-18";
        r.Identities["accesscheck_arap_ace_0_sid"]="S-1-1-0";
        r.Identities["accesscheck_arap_ace_1_sid"]="S-1-15-2-2";
        r.Identities["accesscheck_world_interpreted_decision"]="denied";
        r.Identities["accesscheck_world_descriptor_identity"]="absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;world";
        r.Identities["accesscheck_world_owner_sid"]="S-1-5-18";
        r.Identities["accesscheck_world_group_sid"]="S-1-5-18";
        r.Identities["accesscheck_world_ace_0_sid"]="S-1-1-0";
        if(ordinary) {
            r.Numbers["configured_lpac_request"]=0;r.Numbers.Remove("setup_heap_2_completed");
            r.Numbers["accesscheck_mixed_granted_access_raw"]=3;r.Numbers["accesscheck_mixed_interpreted_granted_access"]=3;
            r.Numbers["accesscheck_aap_access_status_raw"]=1;r.Numbers["accesscheck_aap_granted_access_raw"]=1;
            r.Numbers["accesscheck_aap_interpreted_granted_access"]=1;r.Numbers["accesscheck_aap_error_available"]=0;
            r.Numbers["accesscheck_aap_error"]=-1;r.Identities["accesscheck_aap_interpreted_decision"]="allowed";
        }
        return r;
    }
    static void PilotPolicyTest(bool condition,string label,ref int checks) {
        checks++;if(!condition) throw new InvalidOperationException("managed policy contract: "+label);
    }
    public static int RunPilotPolicyContractTests() {
        int checks=0;DirectReceipt r;
        PilotPolicyTest(VerifyPilotSignature(PilotPolicyTestReceipt(false),false),"LPAC receipt",ref checks);
        PilotPolicyTest(VerifyPilotSignature(PilotPolicyTestReceipt(true),true),"ordinary receipt",ref checks);
        PilotPolicyTest(!VerifyPilotSignature(PilotPolicyTestReceipt(true),false),"ordinary rejected as LPAC",ref checks);
        r=PilotPolicyTestReceipt(false);r.Kind="ordinary";
        PilotPolicyTest(VerifyPilotSignature(r,false),"LPAC signature is independent of case label",ref checks);
        PilotPolicyTest(!VerifyPilotSignature(r,true),"LPAC raw masks cannot satisfy ordinary control",ref checks);
        r=PilotPolicyTestReceipt(true);r.Kind="reference";r.Numbers["configured_lpac_request"]=1;r.Numbers["setup_heap_2_completed"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"ordinary raw signature rejected even after relabeling",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["source_token_requested_access"]=8;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"source_token_requested_access",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["source_type_value"]=2;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"source_type_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["appcontainer_value"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"appcontainer_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["capabilities_value"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"capabilities_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["token_close_error"]=6;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"token_close_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_desired_access"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_desired_access",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_attributes_null"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_attributes_null",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_requested_level"]=2;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_requested_level",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_requested_type"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_requested_type",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_handle_flags"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_handle_flags",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_type_value"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_type_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_level_value"]=2;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_level_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_appcontainer_value"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_appcontainer_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_capabilities_value"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_capabilities_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_close_error"]=6;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_close_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["duplicate_ownership_confirmed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"duplicate_ownership_confirmed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["accesscheck_observer_cleanup_confirmed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"accesscheck_observer_cleanup_confirmed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["accesscheck_observer_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"accesscheck_observer_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["accesscheck_call_attempts"]=3;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"accesscheck_call_attempts",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_size_call_success"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_size_call_success",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_size_error"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_size_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_required_bytes"]=4;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_required_bytes",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_fixed_query_success"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_fixed_query_success",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_fixed_returned_bytes"]=4;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_fixed_returned_bytes",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["lpac_fixed_raw_value"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"lpac_fixed_raw_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_lpac_ntstatus_signed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_lpac_ntstatus_signed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_lpac_ntstatus_unsigned"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_lpac_ntstatus_unsigned",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_lpac_returned_bytes"]=4;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_lpac_returned_bytes",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_lpac_raw_value"]=1;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_lpac_raw_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_appcontainer_call_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_appcontainer_call_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["native_appcontainer_raw_value"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"native_appcontainer_raw_value",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["stdin_close_error"]=6;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"stdin_close_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["stdout_close_error"]=6;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"stdout_close_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["stderr_close_error"]=6;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"stderr_close_error",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["setup_heap_0_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"setup_heap_0_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["setup_heap_1_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"setup_heap_1_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["setup_heap_2_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"setup_heap_2_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["setup_heap_3_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"setup_heap_3_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["setup_heap_4_completed"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"setup_heap_4_completed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["profile_create_hresult"]=5;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"profile_create_hresult",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["pilot_process_outputs_owned"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"pilot_process_outputs_owned",ref checks);
        r=PilotPolicyTestReceipt(false);r.Numbers["pilot_copied_bytes_verified"]=0;
        PilotPolicyTest(!VerifyPilotSignature(r,false),"pilot_copied_bytes_verified",ref checks);
        foreach(string name in new string[]{"mixed","aap","arap","world"}) {
            string p="accesscheck_"+name;
            foreach(string suffix in new string[]{"_descriptor_valid","_decision_valid","_api_called","_api_success","_observation_completed","_privilege_header_valid","_memory_0_free_completed","_memory_7_free_completed"}) {
                r=PilotPolicyTestReceipt(false);r.Numbers.Remove(p+suffix);PilotPolicyTest(!VerifyPilotSignature(r,false),p+suffix+" missing",ref checks);
            }
            r=PilotPolicyTestReceipt(false);r.Numbers[p+"_granted_access_raw"]|=4;PilotPolicyTest(!VerifyPilotSignature(r,false),p+" extra grant",ref checks);
            r=PilotPolicyTestReceipt(false);r.Numbers[p+"_api_success"]=0;PilotPolicyTest(!VerifyPilotSignature(r,false),p+" stale outputs after API failure",ref checks);
            r=PilotPolicyTestReceipt(false);r.Numbers[p+"_privilege_count_raw"]=1;PilotPolicyTest(!VerifyPilotSignature(r,false),p+" privilege use",ref checks);
            foreach(long bytes in new long[]{7,21}) {r=PilotPolicyTestReceipt(false);r.Numbers[p+"_privilege_returned_bytes"]=bytes;PilotPolicyTest(!VerifyPilotSignature(r,false),p+" malformed privilege span",ref checks);}
            r=PilotPolicyTestReceipt(false);r.Numbers[p+"_mapping_all"]=1;PilotPolicyTest(!VerifyPilotSignature(r,false),p+" generic mapping changed",ref checks);
            r=PilotPolicyTestReceipt(false);r.Identities[p+"_owner_sid"]="S-1-1-0";PilotPolicyTest(!VerifyPilotSignature(r,false),p+" descriptor owner changed",ref checks);
        }
        foreach(string name in new string[]{"aap","world"}) {r=PilotPolicyTestReceipt(false);r.Numbers["accesscheck_"+name+"_error"]=0;PilotPolicyTest(!VerifyPilotSignature(r,false),name+" denial error",ref checks);}
        foreach(string key in new string[]{"accesscheck_extra_api_success","accesscheck_mixed_extra_api_success","accesscheck_world_ace_1_mask","accesscheck_world_memory_3_free_completed"}) {r=PilotPolicyTestReceipt(false);r.Numbers[key]=1;PilotPolicyTest(!VerifyPilotSignature(r,false),key+" extra receipt data",ref checks);}
        foreach(string key in new string[]{"appcontainer_sid","duplicate_appcontainer_sid","integrity_sid","duplicate_integrity_sid"}) {r=PilotPolicyTestReceipt(false);r.Identities[key]="S-1-1-0";PilotPolicyTest(!VerifyPilotSignature(r,false),key+" mismatch",ref checks);}
        r=PilotPolicyTestReceipt(false);r.CreationFlags^=0x10;PilotPolicyTest(!VerifyPilotSignature(r,false),"creation flags changed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Kind="python";PilotPolicyTest(!VerifyPilotSignature(r,false),"extra runtime kind",ref checks);
        r=PilotPolicyTestReceipt(false);r.Resumed=true;PilotPolicyTest(!VerifyPilotSignature(r,false),"already resumed",ref checks);
        r=PilotPolicyTestReceipt(false);r.Assigned=true;PilotPolicyTest(!VerifyPilotSignature(r,false),"already assigned",ref checks);
        r=PilotPolicyTestReceipt(false);r.TokenVerified=true;PilotPolicyTest(!VerifyPilotSignature(r,false),"old verifier meaning changed",ref checks);
        r=PilotPolicyTestReceipt(false);r.HostStdioClosed=false;PilotPolicyTest(!VerifyPilotSignature(r,false),"broker stdio open",ref checks);
        r=PilotPolicyTestReceipt(false);r.Identities["native_lpac_call_exception"]="test";PilotPolicyTest(!VerifyPilotSignature(r,false),"diagnostic exception",ref checks);
        foreach(string key in "accesscheck_aap_access_status_raw;accesscheck_aap_ace_0_bytes;accesscheck_aap_ace_0_flags;accesscheck_aap_ace_0_mask;accesscheck_aap_ace_0_type;accesscheck_aap_ace_1_bytes;accesscheck_aap_ace_1_flags;accesscheck_aap_ace_1_mask;accesscheck_aap_ace_1_type;accesscheck_aap_ace_count;accesscheck_aap_acl_bytes;accesscheck_aap_api_called;accesscheck_aap_api_success;accesscheck_aap_dacl_present;accesscheck_aap_decision_valid;accesscheck_aap_descriptor_valid;accesscheck_aap_desired_access_after_mapping;accesscheck_aap_desired_access_before_mapping;accesscheck_aap_error;accesscheck_aap_error_available;accesscheck_aap_granted_access_raw;accesscheck_aap_interpreted_granted_access;accesscheck_aap_mapping_all;accesscheck_aap_mapping_execute;accesscheck_aap_mapping_read;accesscheck_aap_mapping_write;accesscheck_aap_memory_0_free_completed;accesscheck_aap_memory_1_free_completed;accesscheck_aap_memory_2_free_completed;accesscheck_aap_memory_3_free_completed;accesscheck_aap_memory_5_free_completed;accesscheck_aap_memory_6_free_completed;accesscheck_aap_memory_7_free_completed;accesscheck_aap_observation_completed;accesscheck_aap_privilege_allocation_bytes;accesscheck_aap_privilege_count_raw;accesscheck_aap_privilege_entry_span_bytes;accesscheck_aap_privilege_header_valid;accesscheck_aap_privilege_initial_count;accesscheck_aap_privilege_returned_bytes;accesscheck_aap_sacl_present;accesscheck_aap_sd_control;accesscheck_aap_sd_revision;accesscheck_arap_access_status_raw;accesscheck_arap_ace_0_bytes;accesscheck_arap_ace_0_flags;accesscheck_arap_ace_0_mask;accesscheck_arap_ace_0_type;accesscheck_arap_ace_1_bytes;accesscheck_arap_ace_1_flags;accesscheck_arap_ace_1_mask;accesscheck_arap_ace_1_type;accesscheck_arap_ace_count;accesscheck_arap_acl_bytes;accesscheck_arap_api_called;accesscheck_arap_api_success;accesscheck_arap_dacl_present;accesscheck_arap_decision_valid;accesscheck_arap_descriptor_valid;accesscheck_arap_desired_access_after_mapping;accesscheck_arap_desired_access_before_mapping;accesscheck_arap_error;accesscheck_arap_error_available;accesscheck_arap_granted_access_raw;accesscheck_arap_interpreted_granted_access;accesscheck_arap_mapping_all;accesscheck_arap_mapping_execute;accesscheck_arap_mapping_read;accesscheck_arap_mapping_write;accesscheck_arap_memory_0_free_completed;accesscheck_arap_memory_1_free_completed;accesscheck_arap_memory_2_free_completed;accesscheck_arap_memory_3_free_completed;accesscheck_arap_memory_5_free_completed;accesscheck_arap_memory_6_free_completed;accesscheck_arap_memory_7_free_completed;accesscheck_arap_observation_completed;accesscheck_arap_privilege_allocation_bytes;accesscheck_arap_privilege_count_raw;accesscheck_arap_privilege_entry_span_bytes;accesscheck_arap_privilege_header_valid;accesscheck_arap_privilege_initial_count;accesscheck_arap_privilege_returned_bytes;accesscheck_arap_sacl_present;accesscheck_arap_sd_control;accesscheck_arap_sd_revision;accesscheck_call_attempts;accesscheck_mixed_access_status_raw;accesscheck_mixed_ace_0_bytes;accesscheck_mixed_ace_0_flags;accesscheck_mixed_ace_0_mask;accesscheck_mixed_ace_0_type;accesscheck_mixed_ace_1_bytes;accesscheck_mixed_ace_1_flags;accesscheck_mixed_ace_1_mask;accesscheck_mixed_ace_1_type;accesscheck_mixed_ace_2_bytes;accesscheck_mixed_ace_2_flags;accesscheck_mixed_ace_2_mask;accesscheck_mixed_ace_2_type;accesscheck_mixed_ace_count;accesscheck_mixed_acl_bytes;accesscheck_mixed_api_called;accesscheck_mixed_api_success;accesscheck_mixed_dacl_present;accesscheck_mixed_decision_valid;accesscheck_mixed_descriptor_valid;accesscheck_mixed_desired_access_after_mapping;accesscheck_mixed_desired_access_before_mapping;accesscheck_mixed_error;accesscheck_mixed_error_available;accesscheck_mixed_granted_access_raw;accesscheck_mixed_interpreted_granted_access;accesscheck_mixed_mapping_all;accesscheck_mixed_mapping_execute;accesscheck_mixed_mapping_read;accesscheck_mixed_mapping_write;accesscheck_mixed_memory_0_free_completed;accesscheck_mixed_memory_1_free_completed;accesscheck_mixed_memory_2_free_completed;accesscheck_mixed_memory_3_free_completed;accesscheck_mixed_memory_4_free_completed;accesscheck_mixed_memory_5_free_completed;accesscheck_mixed_memory_6_free_completed;accesscheck_mixed_memory_7_free_completed;accesscheck_mixed_observation_completed;accesscheck_mixed_privilege_allocation_bytes;accesscheck_mixed_privilege_count_raw;accesscheck_mixed_privilege_entry_span_bytes;accesscheck_mixed_privilege_header_valid;accesscheck_mixed_privilege_initial_count;accesscheck_mixed_privilege_returned_bytes;accesscheck_mixed_sacl_present;accesscheck_mixed_sd_control;accesscheck_mixed_sd_revision;accesscheck_observer_cleanup_confirmed;accesscheck_observer_completed;accesscheck_world_access_status_raw;accesscheck_world_ace_0_bytes;accesscheck_world_ace_0_flags;accesscheck_world_ace_0_mask;accesscheck_world_ace_0_type;accesscheck_world_ace_count;accesscheck_world_acl_bytes;accesscheck_world_api_called;accesscheck_world_api_success;accesscheck_world_dacl_present;accesscheck_world_decision_valid;accesscheck_world_descriptor_valid;accesscheck_world_desired_access_after_mapping;accesscheck_world_desired_access_before_mapping;accesscheck_world_error;accesscheck_world_error_available;accesscheck_world_granted_access_raw;accesscheck_world_interpreted_granted_access;accesscheck_world_mapping_all;accesscheck_world_mapping_execute;accesscheck_world_mapping_read;accesscheck_world_mapping_write;accesscheck_world_memory_0_free_completed;accesscheck_world_memory_1_free_completed;accesscheck_world_memory_2_free_completed;accesscheck_world_memory_5_free_completed;accesscheck_world_memory_6_free_completed;accesscheck_world_memory_7_free_completed;accesscheck_world_observation_completed;accesscheck_world_privilege_allocation_bytes;accesscheck_world_privilege_count_raw;accesscheck_world_privilege_entry_span_bytes;accesscheck_world_privilege_header_valid;accesscheck_world_privilege_initial_count;accesscheck_world_privilege_returned_bytes;accesscheck_world_sacl_present;accesscheck_world_sd_control;accesscheck_world_sd_revision;appcontainer_observation_success;appcontainer_query_error;appcontainer_required_bytes;appcontainer_returned_bytes;appcontainer_sid_observation_success;appcontainer_sid_query_error;appcontainer_sid_required_bytes;appcontainer_sid_returned_bytes;appcontainer_sid_sid_bytes;appcontainer_sid_sid_offset;appcontainer_sid_size_error;appcontainer_size_error;appcontainer_value;capabilities_observation_success;capabilities_query_error;capabilities_required_bytes;capabilities_returned_bytes;capabilities_size_error;capabilities_value;configured_lpac_request;duplicate_api_success;duplicate_appcontainer_free_completed;duplicate_appcontainer_query_error;duplicate_appcontainer_query_success;duplicate_appcontainer_required_bytes;duplicate_appcontainer_returned_bytes;duplicate_appcontainer_sid_free_completed;duplicate_appcontainer_sid_query_error;duplicate_appcontainer_sid_query_success;duplicate_appcontainer_sid_required_bytes;duplicate_appcontainer_sid_returned_bytes;duplicate_appcontainer_sid_sid_bytes;duplicate_appcontainer_sid_sid_offset;duplicate_appcontainer_sid_size_call_success;duplicate_appcontainer_sid_size_error;duplicate_appcontainer_sid_valid;duplicate_appcontainer_size_call_success;duplicate_appcontainer_size_error;duplicate_appcontainer_valid;duplicate_appcontainer_value;duplicate_attributes_null;duplicate_capabilities_free_completed;duplicate_capabilities_query_error;duplicate_capabilities_query_success;duplicate_capabilities_required_bytes;duplicate_capabilities_returned_bytes;duplicate_capabilities_size_call_success;duplicate_capabilities_size_error;duplicate_capabilities_valid;duplicate_capabilities_value;duplicate_close_error;duplicate_desired_access;duplicate_error;duplicate_handle_flags;duplicate_handle_flags_error;duplicate_handle_flags_success;duplicate_integrity_sid_free_completed;duplicate_integrity_sid_query_error;duplicate_integrity_sid_query_success;duplicate_integrity_sid_required_bytes;duplicate_integrity_sid_returned_bytes;duplicate_integrity_sid_sid_bytes;duplicate_integrity_sid_sid_offset;duplicate_integrity_sid_size_call_success;duplicate_integrity_sid_size_error;duplicate_integrity_sid_valid;duplicate_level_free_completed;duplicate_level_query_error;duplicate_level_query_success;duplicate_level_required_bytes;duplicate_level_returned_bytes;duplicate_level_size_call_success;duplicate_level_size_error;duplicate_level_valid;duplicate_level_value;duplicate_ownership_confirmed;duplicate_requested_level;duplicate_requested_type;duplicate_type_free_completed;duplicate_type_query_error;duplicate_type_query_success;duplicate_type_required_bytes;duplicate_type_returned_bytes;duplicate_type_size_call_success;duplicate_type_size_error;duplicate_type_valid;duplicate_type_value;duplicate_valid;integrity_sid_observation_success;integrity_sid_query_error;integrity_sid_required_bytes;integrity_sid_returned_bytes;integrity_sid_sid_bytes;integrity_sid_sid_offset;integrity_sid_size_error;lpac_fixed_buffer_bytes;lpac_fixed_initial_value;lpac_fixed_query_error;lpac_fixed_query_success;lpac_fixed_raw_value;lpac_fixed_returned_bytes;lpac_fixed_value_valid;lpac_observation_success;lpac_required_bytes;lpac_size_call_success;lpac_size_error;lpac_sizing_expected_insufficient_buffer;native_appcontainer_buffer_bytes;native_appcontainer_buffer_unchanged;native_appcontainer_call_completed;native_appcontainer_class;native_appcontainer_complete_dword_observed;native_appcontainer_initial_returned_bytes;native_appcontainer_initial_value;native_appcontainer_ntstatus_signed;native_appcontainer_ntstatus_unsigned;native_appcontainer_raw_value;native_appcontainer_return_length_unchanged;native_appcontainer_returned_bytes;native_lpac_buffer_bytes;native_lpac_buffer_unchanged;native_lpac_call_completed;native_lpac_class;native_lpac_complete_dword_observed;native_lpac_initial_returned_bytes;native_lpac_initial_value;native_lpac_ntstatus_signed;native_lpac_ntstatus_unsigned;native_lpac_raw_value;native_lpac_return_length_unchanged;native_lpac_returned_bytes;native_queries_observation_only;pilot_copied_bytes_verified;pilot_process_outputs_owned;profile_create_hresult;setup_attribute_cleanup_completed;setup_heap_0_completed;setup_heap_1_completed;setup_heap_2_completed;setup_heap_3_completed;setup_heap_4_completed;setup_stderr_cleanup_completed;setup_stdin_cleanup_completed;setup_stdout_cleanup_completed;setup_writer_cleanup_completed;source_restricted_properties_verified;source_token_open_error;source_token_requested_access;source_type_observation_success;source_type_query_error;source_type_required_bytes;source_type_returned_bytes;source_type_size_error;source_type_value;stderr_attributes;stderr_close_error;stderr_desired_access;stderr_file_type;stderr_handle_flags;stderr_length;stderr_links;stderr_open_error;stdin_attributes;stdin_close_error;stdin_desired_access;stdin_file_type;stdin_handle_flags;stdin_length;stdin_links;stdin_open_error;stdin_writer_attributes;stdin_writer_close_error;stdin_writer_desired_access;stdin_writer_file_type;stdin_writer_handle_flags;stdin_writer_length;stdin_writer_links;stdin_writer_open_error;stdout_attributes;stdout_close_error;stdout_desired_access;stdout_file_type;stdout_handle_flags;stdout_length;stdout_links;stdout_open_error;token_close_error".Split(';')) {r=PilotPolicyTestReceipt(false);r.Numbers.Remove(key);PilotPolicyTest(!VerifyPilotSignature(r,false),"required field missing: "+key,ref checks);}
        foreach(string key in "accesscheck_aap_ace_0_sid;accesscheck_aap_ace_1_sid;accesscheck_aap_descriptor_identity;accesscheck_aap_group_sid;accesscheck_aap_interpreted_decision;accesscheck_aap_owner_sid;accesscheck_arap_ace_0_sid;accesscheck_arap_ace_1_sid;accesscheck_arap_descriptor_identity;accesscheck_arap_group_sid;accesscheck_arap_interpreted_decision;accesscheck_arap_owner_sid;accesscheck_mixed_ace_0_sid;accesscheck_mixed_ace_1_sid;accesscheck_mixed_ace_2_sid;accesscheck_mixed_descriptor_identity;accesscheck_mixed_group_sid;accesscheck_mixed_interpreted_decision;accesscheck_mixed_owner_sid;accesscheck_world_ace_0_sid;accesscheck_world_descriptor_identity;accesscheck_world_group_sid;accesscheck_world_interpreted_decision;accesscheck_world_owner_sid;appcontainer_sid;duplicate_appcontainer_sid;duplicate_integrity_sid;integrity_sid;native_appcontainer_ntstatus_hex;native_lpac_ntstatus_hex;stderr;stdin;stdin_writer;stdout".Split(';')) {r=PilotPolicyTestReceipt(false);r.Identities.Remove(key);PilotPolicyTest(!VerifyPilotSignature(r,false),"required field missing: "+key,ref checks);}
        return checks;
    }
}
