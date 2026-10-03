// CI-only raw observations. These facts never certify committed run acceptance.
using System;
using System.IO;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    static bool PilotCmdObservationKind(string kind) {
        return kind=="cmd-cwd" || kind=="cmd-read-direct" || kind=="cmd-relative-batch-exit23";
    }
    static string FixedPilotCmdCwdCommand(string privateCmdExe) {
        SafePath(privateCmdExe);
        if(Path.GetFileName(privateCmdExe)!="cmd.exe") throw new ArgumentException("fixed private cmd executable required");
        return Quote(privateCmdExe)+" /d /q /c cd";
    }
    static string FixedPilotCmdReadCommand(string privateCmdExe) {
        SafePath(privateCmdExe);
        if(Path.GetFileName(privateCmdExe)!="cmd.exe") throw new ArgumentException("fixed private cmd executable required");
        return Quote(privateCmdExe)+" /d /q /c type direct.cmd";
    }
    static string FixedPilotCmdRelativeBatchCommand(string privateCmdExe) {
        SafePath(privateCmdExe);
        if(Path.GetFileName(privateCmdExe)!="cmd.exe") throw new ArgumentException("fixed private cmd executable required");
        return Quote(privateCmdExe)+" /d /q /c .\\direct.cmd";
    }
    static string FixedPilotCmdObservationCommand(string kind,string privateCmdExe) {
        if(!PilotCmdObservationKind(kind)) throw new ArgumentException("fixed cmd observation case required");
        if(kind=="cmd-cwd") return FixedPilotCmdCwdCommand(privateCmdExe);
        if(kind=="cmd-read-direct") return FixedPilotCmdReadCommand(privateCmdExe);
        return FixedPilotCmdRelativeBatchCommand(privateCmdExe);
    }
    static string PilotCmdObservationProtocol(string kind) {
        if(!PilotCmdObservationKind(kind)) throw new ArgumentException("fixed cmd observation case required");
        return kind=="cmd-relative-batch-exit23"?"cmd-relative-batch-raw-v1":"cmd-cwd-read-raw-v1";
    }
    static void CapturePilotCmdReadBatchUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops) {
        if(s==null || s.Receipt==null || !s.OwnershipCertain || s.ProfileCreated || s.Sid!=IntPtr.Zero ||
            s.Job!=IntPtr.Zero || s.SourceToken!=IntPtr.Zero || s.Process.process!=IntPtr.Zero || s.Process.thread!=IntPtr.Zero ||
            s.Receipt.CreateAttempted || s.Receipt.Created || s.Receipt.Assigned || s.Receipt.Resumed ||
            s.Receipt.Kind!="cmd" || !PilotIdentity(s.Receipt,"pilot_case_id","cmd-read-direct"))
            throw new InvalidOperationException("direct TYPE fixture capture must precede all profile/process allocation");
        PilotCmdObservationExpectedBytes("cmd-read-direct",s.Workspace);
        DirectReceipt r=s.Receipt;
        string exe=Path.Combine(Path.GetDirectoryName(s.Workspace),"code","cmd.exe");
        if(r.Executable!=exe || r.CommandLine!=FixedPilotCmdReadCommand(exe) ||
            !PilotIdentity(r,"pilot_cmd_observation_protocol","cmd-cwd-read-raw-v1") ||
            !PilotIdentity(r,"pilot_cmd_observation_case","cmd-read-direct") ||
            !PilotIdentity(r,"pilot_cmd_observation_command",r.CommandLine) ||
            !PilotIdentity(r,"pilot_cmd_observation_cwd",s.Workspace))
            throw new InvalidOperationException("direct TYPE fixture identity changed");
        CapturePilotCmdBatchCore(s,evidence,ops,true);
    }
    static void CapturePilotCmdReadBatch(QualificationSubject s,string evidence) {
        CapturePilotCmdReadBatchUsing(s,evidence,PilotCmdNativeCaptureOperations());
    }
    static void CapturePilotCmdRelativeBatchUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops) {
        if(s==null || s.Receipt==null || !s.OwnershipCertain || s.ProfileCreated || s.Sid!=IntPtr.Zero ||
            s.Job!=IntPtr.Zero || s.SourceToken!=IntPtr.Zero || s.Process.process!=IntPtr.Zero || s.Process.thread!=IntPtr.Zero ||
            s.Receipt.CreateAttempted || s.Receipt.Created || s.Receipt.Assigned || s.Receipt.Resumed ||
            s.Receipt.Kind!="cmd" || !PilotIdentity(s.Receipt,"pilot_case_id","cmd-relative-batch-exit23"))
            throw new InvalidOperationException("relative batch capture must precede all profile/process allocation");
        PilotCmdObservationExpectedBytes("cmd-relative-batch-exit23",s.Workspace);
        DirectReceipt r=s.Receipt;
        string exe=Path.Combine(Path.GetDirectoryName(s.Workspace),"code","cmd.exe");
        if(r.Executable!=exe || r.CommandLine!=FixedPilotCmdRelativeBatchCommand(exe) ||
            !PilotIdentity(r,"pilot_cmd_observation_protocol","cmd-relative-batch-raw-v1") ||
            !PilotIdentity(r,"pilot_cmd_observation_case","cmd-relative-batch-exit23") ||
            !PilotIdentity(r,"pilot_cmd_observation_command",r.CommandLine) ||
            !PilotIdentity(r,"pilot_cmd_observation_cwd",s.Workspace))
            throw new InvalidOperationException("relative batch fixture identity changed");
        CapturePilotCmdBatchCore(s,evidence,ops,true);
    }
    static void CapturePilotCmdRelativeBatch(QualificationSubject s,string evidence) {
        CapturePilotCmdRelativeBatchUsing(s,evidence,PilotCmdNativeCaptureOperations());
    }
    static byte[] PilotCmdObservationExpectedBytes(string kind,string exactWorkspace) {
        if(!PilotCmdObservationKind(kind) || String.IsNullOrEmpty(exactWorkspace)) throw new ArgumentException("fixed cmd observation and workspace required");
        string full=PilotOwnedPath(exactWorkspace);
        if(full!=exactWorkspace || Path.GetFullPath(exactWorkspace)!=exactWorkspace || Path.GetFileName(full)!="workspace")
            throw new ArgumentException("exact coordinator workspace required");
        string root=Path.GetDirectoryName(full),leaf=Path.GetFileName(root);
        PilotLeafName(leaf,true);
        if(!leaf.StartsWith("owned-",StringComparison.Ordinal)) throw new ArgumentException("owned case workspace required");
        foreach(string part in full.Substring(3).Split('\\')) PilotLeafName(part,false);
        if(kind=="cmd-read-direct") return PilotCmdMinimalBatchBytes();
        if(kind=="cmd-relative-batch-exit23") return new byte[0];
        foreach(char c in exactWorkspace) if(c>127) return null;
        var bytes=new byte[exactWorkspace.Length+2];
        for(int i=0;i<exactWorkspace.Length;i++) bytes[i]=(byte)exactWorkspace[i];
        bytes[bytes.Length-2]=13;bytes[bytes.Length-1]=10;return bytes;
    }
    static void ReadPilotCmdObservationUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops) {
        if(s==null || s.Receipt==null || s.Receipt.Numbers==null || s.Receipt.Identities==null)
            throw new ArgumentNullException("cmd observation subject");
        DirectReceipt r=s.Receipt;
        r.Numbers["pilot_cmd_observation_raw_complete"]=0;
        r.Numbers["pilot_cmd_observation_stdout_matches"]=0;r.Numbers["pilot_cmd_observation_stderr_empty"]=0;
        r.Identities.Remove("pilot_cmd_observation_stage");r.Identities.Remove("pilot_cmd_observation_expected_sha256");
        r.Numbers.Remove("pilot_cmd_observation_expected_supported");r.Numbers.Remove("pilot_cmd_observation_expected_bytes");
        string kind;
        if(!r.Identities.TryGetValue("pilot_case_id",out kind) || !PilotCmdObservationKind(kind) || r.Kind!="cmd" ||
            !s.OwnershipCertain || !s.ProfileCreated || !s.ProcessStopped || !s.JobDrained || !r.Drained ||
            !r.CreateAttempted || !r.Created || r.CreateError!=0 || !r.Assigned || !r.Resumed ||
            s.Process.process!=IntPtr.Zero || s.Process.thread!=IntPtr.Zero || s.Job!=IntPtr.Zero || s.SourceToken!=IntPtr.Zero || s.Sid!=IntPtr.Zero ||
            !PilotStdioClosed(r) || !PilotNumbers(r,"",new string[]{"individual_stop_drain_close_confirmed","exact_process_stop_confirmed",
                "job_query_error","job_active_processes","process_close_error","thread_close_error","job_close_error"},new long[]{1,1,0,0,0,0,0}))
            throw new InvalidOperationException("raw reads require the exact stopped, drained and closed target");
        byte[] expected=PilotCmdObservationExpectedBytes(kind,s.Workspace);
        string exe=Path.Combine(Path.GetDirectoryName(s.Workspace),"code","cmd.exe");
        string command=FixedPilotCmdObservationCommand(kind,exe);
        if(r.Executable!=exe || r.CommandLine!=command || s.Root!=Path.GetDirectoryName(s.Workspace) || s.Code!=Path.GetDirectoryName(exe) ||
            !PilotIdentity(r,"pilot_cmd_observation_protocol",PilotCmdObservationProtocol(kind)) ||
            !PilotIdentity(r,"pilot_cmd_observation_case",kind) || !PilotIdentity(r,"pilot_cmd_observation_command",command) ||
            !PilotIdentity(r,"pilot_cmd_observation_cwd",s.Workspace) ||
            !PilotCmdSha256(r.ExecutableSha256) || !PilotIdentity(r,"pilot_original_cmd_sha256",r.ExecutableSha256) ||
            !PilotNumber(r,"pilot_cmd_same_binary_verified",1) || (kind!="cmd-cwd" && !PilotCmdMinimalCaptureVerified(r)))
            throw new InvalidOperationException("raw command, cwd or provenance identity changed");
        string fullEvidence=PilotOwnedPath(evidence);
        if(fullEvidence!=evidence || Path.GetFullPath(evidence)!=evidence || Path.GetFileName(evidence)!=kind ||
            String.Equals(evidence,s.Workspace,StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("exact separate case evidence directory required");
        if(kind!="cmd-cwd") {
            foreach(string part in new string[]{"source","destination","readback"}) {
                string label="pilot_cmd_batch_"+part,identity=r.Identities[label];
                string path=part=="source"?Path.Combine(s.Workspace,"direct.cmd"):Path.Combine(evidence,"generated-direct.cmd.bin");
                string[] fields=identity.Split(':');uint volume,high,low;
                if(!PilotIdentity(r,label+"_path",path) || fields.Length!=3 || !UInt32.TryParse(fields[0],out volume) ||
                    !UInt32.TryParse(fields[1],out high) || !UInt32.TryParse(fields[2],out low) || (high==0 && low==0) ||
                    identity!=volume+":"+high+":"+low || (part!="source" && identity==r.Identities["pilot_cmd_batch_source"]))
                    throw new InvalidOperationException("minimal TYPE fixture provenance changed");
            }
        }
        foreach(string file in new string[]{"stdout.txt","stderr.txt","canary.txt"}) {
            string label="capture_"+file,identity;long size;
            if(!PilotNumber(r,label+"_open_error",0) || !PilotNumber(r,label+"_close_error",0) ||
                !r.Numbers.TryGetValue(label+"_advertised_bytes",out size) || size<0 || size>PilotCmdBatchLimit ||
                !PilotNumber(r,label+"_copied_bytes",size) || !r.Identities.TryGetValue(label,out identity) || String.IsNullOrEmpty(identity) ||
                (file!="canary.txt" && !PilotIdentity(r,file=="stdout.txt"?"stdout":"stderr",identity)))
                throw new InvalidOperationException("mandatory original capture incomplete");
        }
        if(ops==null || ops.OpenRead==null || ops.Validate==null || ops.Read==null || ops.Close==null)
            throw new ArgumentException("complete read-only cmd observation operations required");
        // A new read attempt cannot inherit success-shaped metadata from an earlier attempt.
        foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"}) {
            foreach(string suffix in new string[]{"_open_error","_desired_access","_handle_flags","_advertised_bytes","_bytes","_read_confirmed","_close_confirmed","_close_error"})
                r.Numbers.Remove(label+suffix);
            foreach(string suffix in new string[]{"","_path","_sha256","_close_exception"}) r.Identities.Remove(label+suffix);
        }
        r.Identities["pilot_cmd_observation_stage"]="after_target_stop_and_job_drain";
        r.Numbers["pilot_cmd_observation_expected_supported"]=expected==null?0:1;
        r.Numbers["pilot_cmd_observation_expected_bytes"]=expected==null?-1:expected.Length;
        if(expected!=null) r.Identities["pilot_cmd_observation_expected_sha256"]=PilotCmdRawHash(expected);
        byte[] output=ReadPilotCmdCapture(s,Path.Combine(s.Workspace,"stdout.txt"),r.Identities["stdout"],"pilot_cmd_stdout_source",ops);
        byte[] outputCopy=ReadPilotCmdCapture(s,Path.Combine(evidence,"stdout.txt"),null,"pilot_cmd_stdout_evidence",ops);
        byte[] error=ReadPilotCmdCapture(s,Path.Combine(s.Workspace,"stderr.txt"),r.Identities["stderr"],"pilot_cmd_stderr_source",ops);
        byte[] errorCopy=ReadPilotCmdCapture(s,Path.Combine(evidence,"stderr.txt"),null,"pilot_cmd_stderr_evidence",ops);
        foreach(string key in r.Numbers.Keys) if(key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal)) {
            bool known=false;
            foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"})
                foreach(string suffix in new string[]{"_open_error","_desired_access","_handle_flags","_advertised_bytes","_bytes","_read_confirmed","_close_confirmed","_close_error"})
                    if(key==label+suffix) known=true;
            if(!known) throw new InvalidOperationException("unknown raw observation receipt field");
        }
        foreach(string key in r.Identities.Keys) if(key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal)) {
            bool known=false;
            foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"})
                foreach(string suffix in new string[]{"","_path","_sha256"}) if(key==label+suffix) known=true;
            if(!known) throw new InvalidOperationException("unknown raw observation receipt field");
        }
        var identities=new Dictionary<string,bool>(StringComparer.Ordinal);
        foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"}) {
            if(!PilotNumbers(r,label,new string[]{"_open_error","_desired_access","_handle_flags","_read_confirmed","_close_confirmed","_close_error"},
                new long[]{0,2147483648,0,1,1,0}) || r.Identities.ContainsKey(label+"_close_exception") || identities.ContainsKey(r.Identities[label]))
                throw new InvalidOperationException("raw observation handle facts incomplete or aliased");
            identities.Add(r.Identities[label],true);
        }
        if(!s.OwnershipCertain || !PilotNumber(r,"capture_stdout.txt_copied_bytes",output.Length) ||
            !PilotNumber(r,"capture_stderr.txt_copied_bytes",error.Length) ||
            !PilotCmdRawEqual(output,outputCopy) || !PilotCmdRawEqual(error,errorCopy) ||
            !PilotIdentity(r,"pilot_cmd_stdout_source_sha256",r.Identities["pilot_cmd_stdout_evidence_sha256"]) ||
            !PilotIdentity(r,"pilot_cmd_stderr_source_sha256",r.Identities["pilot_cmd_stderr_evidence_sha256"]))
            throw new InvalidOperationException("source and evidence raw bytes differ");
        r.Numbers["pilot_cmd_observation_stdout_matches"]=PilotCmdRawEqual(output,expected)?1:0;
        r.Numbers["pilot_cmd_observation_stderr_empty"]=error.Length==0?1:0;
        r.Numbers["pilot_cmd_observation_raw_complete"]=1;
    }
    static void ReadPilotCmdObservation(QualificationSubject s,string evidence) {
        ReadPilotCmdObservationUsing(s,evidence,PilotCmdNativeCaptureOperations());
    }
    static bool PilotCmdObservationEvidenceVerified(PilotCaseReceipt row) {
        if(row==null || row.Launcher==null || !PilotCmdObservationKind(row.Case) || row.Policy!="accesscheck_signature_v1_ci") return false;
        DirectReceipt r=row.Launcher;string cwd,evidence;
        if(r.Numbers==null || r.Identities==null || r.Kind!="cmd" || row.NoCaseResourcesAllocated ||
            !PilotIdentity(r,"pilot_case_id",row.Case) || !PilotIdentity(r,"pilot_cmd_observation_case",row.Case) ||
            !PilotIdentity(r,"pilot_cmd_observation_protocol",PilotCmdObservationProtocol(row.Case)) ||
            !PilotIdentity(r,"pilot_cmd_observation_stage","after_target_stop_and_job_drain") ||
            !r.Identities.TryGetValue("pilot_cmd_observation_cwd",out cwd) ||
            !r.Identities.TryGetValue("pilot_cmd_stdout_evidence_path",out evidence)) return false;
        byte[] expected;
        try {
            expected=PilotCmdObservationExpectedBytes(row.Case,cwd);
            string exe=Path.Combine(Path.GetDirectoryName(cwd),"code","cmd.exe");
            string command=FixedPilotCmdObservationCommand(row.Case,exe);
            evidence=Path.GetDirectoryName(evidence);
            if(expected==null || r.Executable!=exe || r.CommandLine!=command ||
                !PilotIdentity(r,"pilot_cmd_observation_command",command) || evidence!=PilotOwnedPath(evidence) ||
                evidence!=Path.GetFullPath(evidence) || Path.GetFileName(evidence)!=row.Case ||
                String.Equals(cwd,evidence,StringComparison.OrdinalIgnoreCase)) return false;
        } catch(ArgumentException) {return false;} catch(IOException) {return false;} catch(InvalidOperationException) {return false;} catch(NotSupportedException) {return false;}
        if(!PilotCmdSha256(r.ExecutableSha256) || !PilotIdentity(r,"pilot_original_cmd_sha256",r.ExecutableSha256) ||
            !PilotNumber(r,"pilot_cmd_same_binary_verified",1) || !PilotNumber(r,"pilot_cmd_observation_expected_supported",1) ||
            !PilotNumber(r,"pilot_cmd_observation_expected_bytes",expected.Length) ||
            !PilotIdentity(r,"pilot_cmd_observation_expected_sha256",PilotCmdRawHash(expected)) ||
            !PilotNumber(r,"pilot_cmd_observation_raw_complete",1) || !PilotNumber(r,"pilot_cmd_observation_stdout_matches",1) ||
            !PilotNumber(r,"pilot_cmd_observation_stderr_empty",1) || (row.Case!="cmd-cwd" && !PilotCmdMinimalCaptureVerified(r))) return false;
        if(row.Case!="cmd-cwd") {
            foreach(string part in new string[]{"source","destination","readback"}) {
                string label="pilot_cmd_batch_"+part,identity=r.Identities[label];
                string path=part=="source"?Path.Combine(cwd,"direct.cmd"):Path.Combine(evidence,"generated-direct.cmd.bin");
                string[] fields=identity.Split(':');uint volume,high,low;
                if(!PilotIdentity(r,label+"_path",path) || fields.Length!=3 || !UInt32.TryParse(fields[0],out volume) ||
                    !UInt32.TryParse(fields[1],out high) || !UInt32.TryParse(fields[2],out low) || (high==0 && low==0) ||
                    identity!=volume+":"+high+":"+low || (part!="source" && identity==r.Identities["pilot_cmd_batch_source"])) return false;
            }
        }
        foreach(string key in r.Numbers.Keys) if(key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal)) {
            bool known=false;
            foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"})
                foreach(string suffix in new string[]{"_open_error","_desired_access","_handle_flags","_advertised_bytes","_bytes","_read_confirmed","_close_confirmed","_close_error"})
                    if(key==label+suffix) known=true;
            if(!known) return false;
        }
        foreach(string key in r.Identities.Keys) if(key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal)) {
            bool known=false;
            foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"})
                foreach(string suffix in new string[]{"","_path","_sha256"}) if(key==label+suffix) known=true;
            if(!known) return false;
        }
        var identities=new Dictionary<string,bool>(StringComparer.Ordinal);
        foreach(string stream in new string[]{"stdout","stderr"}) {
            long length=stream=="stdout"?expected.Length:0;
            string hash=stream=="stdout"?PilotCmdRawHash(expected):PilotCmdRawHash(new byte[0]);
            foreach(string part in new string[]{"source","evidence"}) {
                string label="pilot_cmd_"+stream+"_"+part,identity;
                if(!r.Identities.TryGetValue(label,out identity) || String.IsNullOrEmpty(identity) || identities.ContainsKey(identity) ||
                    !PilotIdentity(r,label+"_path",Path.Combine(part=="source"?cwd:evidence,stream+".txt")) ||
                    !PilotIdentity(r,label+"_sha256",hash) || !PilotNumbers(r,label,new string[]{"_open_error","_desired_access","_handle_flags",
                        "_advertised_bytes","_bytes","_read_confirmed","_close_confirmed","_close_error"},new long[]{0,2147483648,0,length,length,1,1,0}) ||
                    r.Identities.ContainsKey(label+"_close_exception") || (part=="source" && !PilotIdentity(r,stream,identity))) return false;
                string[] fields=identity.Split(':');uint volume,high,low;
                if(fields.Length!=3 || !UInt32.TryParse(fields[0],out volume) || !UInt32.TryParse(fields[1],out high) ||
                    !UInt32.TryParse(fields[2],out low) || (high==0 && low==0) || identity!=volume+":"+high+":"+low) return false;
                identities.Add(identity,true);
            }
            if(!PilotIdentity(r,"capture_"+stream+".txt",r.Identities[stream]) ||
                !PilotNumbers(r,"capture_"+stream+".txt",new string[]{"_open_error","_close_error","_advertised_bytes","_copied_bytes"},new long[]{0,0,length,length})) return false;
        }
        string canaryIdentity;
        if(!r.Identities.TryGetValue("capture_canary.txt",out canaryIdentity) || String.IsNullOrEmpty(canaryIdentity) ||
            !PilotNumbers(r,"capture_canary.txt",new string[]{"_open_error","_close_error","_advertised_bytes","_copied_bytes"},
                new long[]{0,0,24,24})) return false;
        foreach(string key in r.Numbers.Keys) {
            if(key.StartsWith("pilot_cmd_observation_",StringComparison.Ordinal) &&
                key!="pilot_cmd_observation_expected_supported" && key!="pilot_cmd_observation_expected_bytes" &&
                key!="pilot_cmd_observation_raw_complete" && key!="pilot_cmd_observation_stdout_matches" &&
                key!="pilot_cmd_observation_stderr_empty") return false;
        }
        foreach(string key in r.Identities.Keys) {
            if(key.StartsWith("pilot_cmd_observation_",StringComparison.Ordinal) &&
                key!="pilot_cmd_observation_protocol" && key!="pilot_cmd_observation_case" && key!="pilot_cmd_observation_command" &&
                key!="pilot_cmd_observation_cwd" && key!="pilot_cmd_observation_stage" && key!="pilot_cmd_observation_expected_sha256") return false;
            if(key.EndsWith("_observation_failure",StringComparison.Ordinal)) return false;
            if(key.EndsWith("_exception",StringComparison.Ordinal))
                foreach(string prefix in new string[]{"source_","appcontainer","capabilities","integrity_","duplicate_","accesscheck_","lpac_","native_","setup_","pilot_source_close"})
                    if(key.StartsWith(prefix,StringComparison.Ordinal)) return false;
        }
        // Validate measured policy facts without re-running the pre-resume predicate on a terminal receipt.
        uint expectedExit=row.Case=="cmd-relative-batch-exit23"?23u:0u;
        if(!row.AuthorityObserved || !row.PreResumeReady || !row.OutsideUnchanged || !row.OutsideWriteAbsent ||
            row.OutsideReadObserved || row.OutsideWriteObserved || !r.CreateAttempted || !r.Created || r.CreateError!=0 ||
            !r.Assigned || !r.Resumed || !r.Drained || r.TokenVerified || r.Wait!=WAIT_OBJECT_0 || r.Exit!=expectedExit ||
            !PilotNumber(r,"pilot_exit_query_success",1) || r.CreationFlags!=(CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u) ||
            String.IsNullOrEmpty(r.ProfileSid) || !PilotStdioClosed(r) || !PilotPinnedMethodDiagnostics(r)) return false;
        foreach(string key in r.Numbers.Keys) if(!PilotKnownAccessCheckKey(key)) return false;
        foreach(string key in r.Identities.Keys) if(!PilotKnownAccessCheckKey(key)) return false;
        if(!PilotNumbers(r,"",new string[]{"profile_create_hresult","pilot_process_outputs_owned","pilot_copied_bytes_verified",
            "source_token_requested_access","source_token_open_error","source_restricted_properties_verified","token_close_error",
            "source_type_value","appcontainer_value","capabilities_value","duplicate_ownership_confirmed","duplicate_valid","duplicate_api_success","duplicate_error",
            "duplicate_desired_access","duplicate_attributes_null","duplicate_requested_level","duplicate_requested_type","duplicate_handle_flags_success",
            "duplicate_handle_flags_error","duplicate_handle_flags","duplicate_type_value","duplicate_level_value","duplicate_appcontainer_value","duplicate_capabilities_value",
            "duplicate_close_error","accesscheck_observer_completed","accesscheck_observer_cleanup_confirmed","accesscheck_call_attempts",
            "individual_stop_drain_close_confirmed","exact_process_stop_confirmed","job_query_error","job_active_processes","process_close_error","thread_close_error","job_close_error"},
            new long[]{0,1,1,10,0,1,0,1,1,0,1,1,1,0,8,1,1,2,1,0,0,2,1,1,0,0,1,1,4,1,1,0,0,0,0,0})) return false;
        foreach(string label in new string[]{"source_type","appcontainer","capabilities"})
            if(!PilotTokenQuery(r,label,false,label!="capabilities")) return false;
        foreach(string label in new string[]{"duplicate_type","duplicate_level","duplicate_appcontainer","duplicate_capabilities"})
            if(!PilotTokenQuery(r,label,true,label!="duplicate_capabilities")) return false;
        if(!PilotTokenSid(r,"appcontainer_sid",r.ProfileSid,false,false) || !PilotTokenSid(r,"integrity_sid","S-1-16-4096",true,false) ||
            !PilotTokenSid(r,"duplicate_appcontainer_sid",r.ProfileSid,false,true) || !PilotTokenSid(r,"duplicate_integrity_sid","S-1-16-4096",true,true)) return false;
        return PilotDescriptorDecision(r,"mixed",1,2,new string[]{"S-1-1-0","S-1-15-2-1","S-1-15-2-2"},new long[]{3,1,2}) &&
            PilotDescriptorDecision(r,"aap",0,0,new string[]{"S-1-1-0","S-1-15-2-1"},new long[]{1,1}) &&
            PilotDescriptorDecision(r,"arap",1,2,new string[]{"S-1-1-0","S-1-15-2-2"},new long[]{2,2}) &&
            PilotDescriptorDecision(r,"world",0,0,new string[]{"S-1-1-0"},new long[]{3});
    }
    static void ClassifyPilotCmdObservation(PilotCaseReceipt row) {
        if(row==null || row.Launcher==null) throw new ArgumentNullException("cmd observation facts");
        row.CmdCwdObserved=false;row.CmdReadObserved=false;row.CmdExit23Observed=false;row.CmdBatchExit23Observed=false;
        row.CmdRelativeBatchExit23Observed=false;
        row.PositivePassed=false;row.ScriptEntryObserved=false;row.OutputOk=false;row.MutationOk=false;
        row.OfflineReferenceRouteValid=false;row.NativeFiveAssertionsPassed=false;row.NetworkDenialProven=false;
        if(row.Fatal) return;
        if(!PilotCmdObservationKind(row.Case)) throw new ArgumentException("fixed cmd observation case required");
        DirectReceipt r=row.Launcher;row.ExitHex=r.Exit.ToString("X8");row.KnownStartupStatus=null;
        bool cwd=row.Case=="cmd-cwd",read=row.Case=="cmd-read-direct",matched=PilotCmdObservationEvidenceVerified(row);
        row.CanaryClassification=cwd?"cwd_observation_did_not_attempt_runtime_canary":read?
            "read_observation_did_not_attempt_runtime_canary":"relative_batch_observation_did_not_attempt_runtime_canary";
        row.CmdCwdObserved=cwd && matched;row.CmdReadObserved=read && matched;
        row.CmdRelativeBatchExit23Observed=!cwd && !read && matched;
        bool unsupported=false;string workspace;
        if(cwd && r.Numbers!=null && r.Identities!=null && PilotNumber(r,"pilot_cmd_observation_expected_supported",0) && PilotNumber(r,"pilot_cmd_observation_expected_bytes",-1) &&
            PilotNumber(r,"pilot_cmd_observation_raw_complete",1) && !r.Identities.ContainsKey("pilot_cmd_observation_expected_sha256") &&
            r.Identities.TryGetValue("pilot_cmd_observation_cwd",out workspace)) {
            try {unsupported=PilotCmdObservationExpectedBytes(row.Case,workspace)==null;}
            catch(ArgumentException) {} catch(IOException) {} catch(InvalidOperationException) {} catch(NotSupportedException) {}
        }
        row.Status=r.Wait==WAIT_TIMEOUT?"deadline_exceeded":cwd?
            (matched?"cmd_cwd_raw_observed":unsupported?"cmd_cwd_expected_encoding_unsupported":"cmd_cwd_raw_not_observed"):
            read?(matched?"cmd_read_direct_raw_observed":"cmd_read_direct_raw_not_observed"):
            (matched?"cmd_relative_batch_exit23_raw_observed":"cmd_relative_batch_exit23_raw_not_observed");
    }
    static bool PilotCmdCwdRawMatched(IList<PilotCaseReceipt> rows) {
        if(rows==null || rows.Count<9 || rows.Count>11) return false;
        for(int i=0;i<rows.Count;i++) if(i!=8 && rows[i]!=null && rows[i].Case=="cmd-cwd") return false;
        PilotCaseReceipt row=rows[8];
        return row!=null && row.Case=="cmd-cwd" && row.CmdCwdObserved && !row.CmdReadObserved && !row.CmdRelativeBatchExit23Observed && PilotCmdObservationEvidenceVerified(row);
    }
    static bool PilotCmdReadRawMatched(IList<PilotCaseReceipt> rows) {
        if(rows==null || rows.Count<10 || rows.Count>11) return false;
        for(int i=0;i<rows.Count;i++) if(i!=9 && rows[i]!=null && rows[i].Case=="cmd-read-direct") return false;
        PilotCaseReceipt row=rows[9];
        return row!=null && row.Case=="cmd-read-direct" && row.CmdReadObserved && !row.CmdCwdObserved && !row.CmdRelativeBatchExit23Observed && PilotCmdObservationEvidenceVerified(row);
    }
    static bool PilotCmdRelativeBatchRawMatched(IList<PilotCaseReceipt> rows) {
        if(rows==null || rows.Count!=11) return false;
        for(int i=0;i<rows.Count;i++) if(i!=10 && rows[i]!=null && rows[i].Case=="cmd-relative-batch-exit23") return false;
        PilotCaseReceipt row=rows[10];
        return row!=null && row.Case=="cmd-relative-batch-exit23" && row.CmdRelativeBatchExit23Observed &&
            !row.CmdCwdObserved && !row.CmdReadObserved && PilotCmdObservationEvidenceVerified(row);
    }
}
