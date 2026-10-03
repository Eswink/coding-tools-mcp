// Managed-only receipt and injected-operation tests. No filesystem, native, process, or network calls.
using System;
using System.IO;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    static void PilotObservationAssert(bool condition,string label,ref int checks) {
        checks++;if(!condition) throw new InvalidOperationException("managed cmd observation contract: "+label);
    }
    static void PilotObservationThrows(Action action,string label,ref int checks) {
        bool rejected=false;try {action();} catch(Exception) {rejected=true;}
        PilotObservationAssert(rejected,label,ref checks);
    }
    sealed class PilotCmdObservationTrace {
        public readonly QualificationSubject Subject=new QualificationSubject();
        public readonly PilotCmdCaptureOperations Operations=new PilotCmdCaptureOperations();
        public readonly List<string> Events=new List<string>();
        public readonly Dictionary<string,byte[]> Bytes=new Dictionary<string,byte[]>(StringComparer.Ordinal);
        public readonly Dictionary<string,int> Closes=new Dictionary<string,int>(StringComparer.Ordinal);
        readonly Dictionary<int,string> Labels=new Dictionary<int,string>();
        readonly Dictionary<string,int> Validations=new Dictionary<string,int>(StringComparer.Ordinal);
        public string Fault="",Evidence;
        public PilotCmdObservationTrace(string kind,bool unicode) {
            Subject.Parent=unicode?"C:\\synthetic-pil\u00f6t":@"C:\synthetic-pilot";
            Subject.Root=Path.Combine(Subject.Parent,"owned-0123456789abcdef0123456789abcdef");
            Subject.Workspace=Path.Combine(Subject.Root,"workspace");Subject.Code=Path.Combine(Subject.Root,"code");
            Subject.Outside=Path.Combine(Subject.Root,"outside");Evidence=Path.Combine(@"C:\synthetic-evidence",kind);
            Subject.Receipt=PilotPolicyTestReceipt(false);DirectReceipt r=Subject.Receipt;r.Kind="cmd";
            r.CreateAttempted=false;r.Created=false;r.Executable=Path.Combine(Subject.Code,"cmd.exe");
            r.CommandLine=FixedPilotCmdObservationCommand(kind,r.Executable);
            r.Identities["pilot_case_id"]=kind;r.Identities["pilot_cmd_observation_case"]=kind;
            r.Identities["pilot_cmd_observation_protocol"]=PilotCmdObservationProtocol(kind);
            r.Identities["pilot_cmd_observation_command"]=r.CommandLine;r.Identities["pilot_cmd_observation_cwd"]=Subject.Workspace;
            r.Identities["pilot_original_cmd_sha256"]=r.ExecutableSha256;r.Numbers["pilot_cmd_same_binary_verified"]=1;
            byte[] expected=PilotCmdObservationExpectedBytes(kind,Subject.Workspace)??new byte[]{0x3f,0x0d,0x0a};
            Bytes["pilot_cmd_stdout_source"]=expected;Bytes["pilot_cmd_stdout_evidence"]=(byte[])expected.Clone();
            Bytes["pilot_cmd_stderr_source"]=new byte[0];Bytes["pilot_cmd_stderr_evidence"]=new byte[0];
            Bytes["pilot_cmd_batch_source"]=PilotCmdMinimalBatchBytes();Bytes["pilot_cmd_batch_destination"]=new byte[0];
            Bytes["pilot_cmd_batch_readback"]=new byte[0];
            Operations.OpenRead=OpenRead;Operations.OpenWrite=OpenWrite;Operations.Validate=Validate;
            Operations.Read=Read;Operations.Write=Write;Operations.Close=Close;
        }
        string Identity(string label) {
            if(label=="pilot_cmd_stdout_source") return Subject.Receipt.Identities["stdout"];
            if(label=="pilot_cmd_stderr_source") return Subject.Receipt.Identities["stderr"];
            if(label=="pilot_cmd_batch_readback") return "7:0:16";
            return "7:0:"+(label=="pilot_cmd_stdout_evidence"?11:label=="pilot_cmd_stderr_evidence"?13:
                label=="pilot_cmd_batch_source"?15:16);
        }
        bool Broken(string label,string operation) {return Fault==label+":"+operation;}
        void OpenRead(ref IntPtr handle,string path,string label,DirectReceipt r) {
            Events.Add(label+":open");
            if(Broken(label,"missing")) throw new FileNotFoundException("injected missing object");
            if(Broken(label,"open_zero")) return;
            int id=Labels.Count+1;Labels.Add(id,label);handle=new IntPtr(id);
            if(Broken(label,"open_throw")) throw new IOException("injected owned-open failure");
            r.Numbers[label+"_open_error"]=Broken(label,"open_error")?5:0;
            r.Numbers[label+"_desired_access"]=Broken(label,"access")?0x40000000L:0x80000000L;
            r.Numbers[label+"_handle_flags"]=Broken(label,"inherited")?1:0;
            if(Broken(label,"open_result_missing")) r.Numbers.Remove(label+"_open_error");
        }
        void OpenWrite(ref IntPtr handle,string path,string label,DirectReceipt r) {
            OpenRead(ref handle,path,label,r);r.Numbers[label+"_desired_access"]=0x40000000L;r.Identities[label]=Identity(label);
        }
        FILE_INFO Validate(IntPtr handle,string path,string identity) {
            string label=Labels[handle.ToInt32()];int count;Validations.TryGetValue(label,out count);Validations[label]=++count;
            Events.Add(label+":validate"+count);
            if(Broken(label,"validate_throw") || (count==2 && Broken(label,"revalidate_throw"))) throw new IOException("injected validation failure");
            string[] parts=Identity(label).Split(':');var info=new FILE_INFO();info.attributes=0x80;info.links=1;
            info.volume=UInt32.Parse(parts[0]);info.indexHigh=UInt32.Parse(parts[1]);info.indexLow=UInt32.Parse(parts[2]);
            info.sizeLow=(uint)Bytes[label].Length;info.creationLow=17;info.writeLow=19;
            if(Broken(label,"reparse")) info.attributes|=0x400;if(Broken(label,"directory")) info.attributes|=0x10;
            if(Broken(label,"nonregular")) throw new InvalidOperationException("injected non-disk object");
            if(Broken(label,"multilink")) info.links=2;if(Broken(label,"oversize")) info.sizeLow=PilotCmdBatchLimit+1;
            if(Broken(label,"high_size")) info.sizeHigh=1;
            if(Broken(label,"zero_identity")) {info.indexHigh=0;info.indexLow=0;}
            if(Broken(label,"wrong_identity") || (count==2 && Broken(label,"changed_identity"))) info.indexLow=999;
            if(count==2 && Broken(label,"metadata")) info.writeLow++;
            if(count==2 && Broken(label,"length")) info.sizeLow++;
            return info;
        }
        byte[] Read(IntPtr handle,long size) {
            string label=Labels[handle.ToInt32()];Events.Add(label+":read");
            if(Broken(label,"read_throw")) throw new IOException("injected read failure");
            if(Broken(label,"read_null")) return null;
            if(Broken(label,"raw_count")) return new byte[Bytes[label].Length+1];
            string streamFault=Broken(label,"early_eof")?"early_eof":Broken(label,"trailing_byte")?"extra_byte":"";
            using(var stream=new PilotCmdTestStream(Bytes[label],streamFault))
                return ReadPilotCmdRawBytes(stream,Broken(label,"size_mismatch")?size+1:size);
        }
        void Write(IntPtr handle,byte[] bytes) {
            string label=Labels[handle.ToInt32()];Events.Add(label+":write");Bytes[label]=(byte[])bytes.Clone();
            Bytes["pilot_cmd_batch_readback"]=(byte[])bytes.Clone();
        }
        bool Close(ref IntPtr handle,string label,DirectReceipt r) {
            Events.Add(label+":close");int count;Closes.TryGetValue(label,out count);Closes[label]=count+1;
            if(Broken(label,"close_throw")) throw new IOException("injected close failure");
            r.Numbers[label+"_close_error"]=Broken(label,"close_error")?6:0;
            if(Broken(label,"close_result_missing")) r.Numbers.Remove(label+"_close_error");
            if(Broken(label,"close_kept")) return true;
            handle=IntPtr.Zero;return !Broken(label,"close_false");
        }
        public void CaptureBatch() {
            string kind=Path.GetFileName(Evidence);
            if(kind=="cmd-read-direct") CapturePilotCmdReadBatchUsing(Subject,Evidence,Operations);
            else if(kind=="cmd-relative-batch-exit23") CapturePilotCmdRelativeBatchUsing(Subject,Evidence,Operations);
            else throw new InvalidOperationException("finite batch observation capture required");
        }
        public void Terminal() {
            DirectReceipt r=Subject.Receipt;
            if(r.Identities["pilot_case_id"]!="cmd-cwd") CaptureBatch();
            Subject.ProfileCreated=true;Subject.ProcessStopped=true;Subject.JobDrained=true;
            r.CreateAttempted=true;r.Created=true;r.Assigned=true;r.Resumed=true;r.Wait=WAIT_OBJECT_0;r.Drained=true;
            r.Exit=r.Identities["pilot_case_id"]=="cmd-relative-batch-exit23"?23u:0u;
            foreach(string key in new string[]{"pilot_exit_query_success","exact_process_stop_confirmed","individual_stop_drain_close_confirmed"}) r.Numbers[key]=1;
            foreach(string key in new string[]{"job_query_error","job_active_processes","process_close_error","thread_close_error","job_close_error"}) r.Numbers[key]=0;
            foreach(string file in new string[]{"stdout.txt","stderr.txt","canary.txt"}) {
                string label="capture_"+file;string stdio=file=="stdout.txt"?"stdout":"stderr";
                int length=file=="canary.txt"?24:Bytes["pilot_cmd_"+stdio+"_source"].Length;
                r.Numbers[label+"_open_error"]=0;r.Numbers[label+"_close_error"]=0;
                r.Numbers[label+"_advertised_bytes"]=length;r.Numbers[label+"_copied_bytes"]=length;
                r.Identities[label]=file=="canary.txt"?"1:1:4":r.Identities[stdio];
            }
            Events.Clear();Closes.Clear();
        }
        public void Observe() {ReadPilotCmdObservationUsing(Subject,Evidence,Operations);}
        public PilotCaseReceipt Row() {
            var row=new PilotCaseReceipt();row.Case=Subject.Receipt.Identities["pilot_case_id"];row.Launcher=Subject.Receipt;
            row.AuthorityObserved=true;row.PreResumeReady=true;row.IndividualResourceCleanupConfirmed=true;row.CaptureIntegrityConfirmed=true;
            ClassifyPilotFacts(row,PilotCmdTestFacts());return row;
        }
    }
    static PilotCaseReceipt PilotObservationRow(string kind) {
        var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Observe();return trace.Row();
    }
    static void PilotObservationReject(string kind,Action<PilotCaseReceipt> mutate,string label,ref int checks) {
        var row=PilotObservationRow(kind);mutate(row);row.CmdCwdObserved=true;row.CmdReadObserved=true;row.CmdRelativeBatchExit23Observed=true;
        PilotObservationAssert(!PilotCmdObservationEvidenceVerified(row),"predicate rejects "+label,ref checks);
        ClassifyPilotFacts(row,PilotCmdTestFacts());
        PilotObservationAssert(!row.CmdCwdObserved && !row.CmdReadObserved && !row.CmdRelativeBatchExit23Observed,"stale flags cleared: "+label,ref checks);
    }
    static bool PilotObservationNoExtraCredit(PilotCaseReceipt row) {
        return !row.PositivePassed && !row.ScriptEntryObserved && !row.OutputOk && !row.MutationOk &&
            !row.OfflineReferenceRouteValid && !row.NativeFiveAssertionsPassed && !row.NetworkDenialProven &&
            !row.CmdExit23Observed && !row.CmdBatchExit23Observed && !row.Launcher.TokenVerified && !row.Launcher.CleanupConfirmed &&
            (row.Case=="cmd-cwd" || !row.CmdCwdObserved) && (row.Case=="cmd-read-direct" || !row.CmdReadObserved) &&
            (row.Case=="cmd-relative-batch-exit23" || !row.CmdRelativeBatchExit23Observed);
    }
    public static int RunPilotCmdObservationContractTests() {
        int checks=0;var trace=new PilotCmdObservationTrace("cmd-cwd",false);string cwd=trace.Subject.Workspace,exe=trace.Subject.Receipt.Executable;
        PilotObservationAssert(FixedPilotCmdCwdCommand(exe)==Quote(exe)+" /d /q /c cd","fixed cwd command",ref checks);
        PilotObservationAssert(FixedPilotCmdReadCommand(exe)==Quote(exe)+" /d /q /c type direct.cmd","fixed TYPE command",ref checks);
        PilotObservationAssert(FixedPilotCmdRelativeBatchCommand(exe)==Quote(exe)+" /d /q /c .\\direct.cmd","fixed relative batch command",ref checks);
        PilotObservationAssert(PilotCmdObservationKind("cmd-relative-batch-exit23"),"exact new observation kind",ref checks);
        PilotObservationAssert(PilotCmdObservationProtocol("cmd-relative-batch-exit23")=="cmd-relative-batch-raw-v1" &&
            PilotCmdObservationProtocol("cmd-cwd")=="cmd-cwd-read-raw-v1" && PilotCmdObservationProtocol("cmd-read-direct")=="cmd-cwd-read-raw-v1","independent exact protocols",ref checks);
        foreach(string kind in new string[]{"cmd","cmd-exit23","cmd-batch-exit23","CMD-CWD","cmd-read-direct ","cmd-relative-batch-exit23 ","unknown",null}) {
            PilotObservationAssert(!PilotCmdObservationKind(kind),"finite observation case set",ref checks);
            PilotObservationThrows(()=>FixedPilotCmdObservationCommand(kind,exe),"finite command dispatch",ref checks);
            PilotObservationThrows(()=>PilotCmdObservationProtocol(kind),"finite protocol dispatch",ref checks);
        }
        foreach(string path in new string[]{"relative/cmd.exe",exe.Replace("cmd.exe","other.exe"),exe+"&other"}) {
            PilotObservationThrows(()=>FixedPilotCmdCwdCommand(path),"cwd command rejects unsafe executable",ref checks);
            PilotObservationThrows(()=>FixedPilotCmdReadCommand(path),"TYPE command rejects unsafe executable",ref checks);
            PilotObservationThrows(()=>FixedPilotCmdRelativeBatchCommand(path),"relative command rejects unsafe executable",ref checks);
        }
        foreach(string path in new string[]{"workspace",@"C:\",cwd+"\\",cwd+"\\.",cwd+"\\..\\workspace",cwd.Replace("workspace","Workspace"),
            cwd.Replace("owned-0123456789abcdef0123456789abcdef","owned-invalid"),cwd.Replace('\\','/'),cwd+"&tail"})
            foreach(string kind in new string[]{"cmd-cwd","cmd-read-direct","cmd-relative-batch-exit23"})
                PilotObservationThrows(()=>PilotCmdObservationExpectedBytes(kind,path),"exact owned workspace required",ref checks);
        byte[] ascii=System.Text.Encoding.ASCII.GetBytes(cwd+"\r\n"),nine={0x65,0x78,0x69,0x74,0x20,0x32,0x33,0x0d,0x0a};
        PilotObservationAssert(PilotCmdRawEqual(ascii,PilotCmdObservationExpectedBytes("cmd-cwd",cwd)),"exact ASCII cwd plus CRLF",ref checks);
        PilotObservationAssert(PilotCmdRawEqual(nine,PilotCmdObservationExpectedBytes("cmd-read-direct",cwd)),"independent exact nine TYPE bytes",ref checks);
        PilotObservationAssert(PilotCmdRawEqual(new byte[0],PilotCmdObservationExpectedBytes("cmd-relative-batch-exit23",cwd)),"independent empty relative output",ref checks);
        PilotObservationThrows(()=>PilotCmdObservationExpectedBytes("unknown",cwd),"unknown expected-byte case",ref checks);
        RunPilotObservationCaptureTests(ref checks);RunPilotObservationByteTests(ref checks);
        RunPilotObservationReadTests(ref checks);RunPilotObservationPredicateTests(ref checks);RunPilotObservationReducerTests(ref checks);
        return checks;
    }
    static void RunPilotObservationCaptureTests(ref int checks) {
        foreach(string kind in new string[]{"cmd-read-direct","cmd-relative-batch-exit23"}) {
            var trace=new PilotCmdObservationTrace(kind,false);
            trace.CaptureBatch();
            PilotObservationAssert(PilotCmdMinimalCaptureVerified(trace.Subject.Receipt) && !trace.Subject.Receipt.CreateAttempted &&
                !trace.Subject.ProfileCreated,"minimal capture exact and preallocation",ref checks);
            foreach(string part in new string[]{"source","destination","readback"})
                PilotObservationAssert(trace.Closes["pilot_cmd_batch_"+part]==1,"minimal preallocation capture closes once",ref checks);
            foreach(Action<QualificationSubject> change in new Action<QualificationSubject>[]{
                x=>x.Receipt.Kind="node",x=>x.Receipt.Identities.Remove("pilot_case_id"),x=>x.Receipt.Identities["pilot_case_id"]="cmd-cwd",
                x=>x.Receipt.Identities.Remove("pilot_cmd_observation_protocol"),x=>x.Receipt.Identities["pilot_cmd_observation_case"]="cmd-cwd",
                x=>x.Receipt.Identities["pilot_cmd_observation_cwd"]+="changed",x=>x.Receipt.Identities["pilot_cmd_observation_command"]+="changed",
                x=>x.Receipt.Executable+="changed",x=>x.Receipt.CommandLine+="changed",
                x=>x.Receipt.Identities["pilot_case_id"]="cmd",x=>x.ProfileCreated=true,x=>x.OwnershipCertain=false,x=>x.Sid=new IntPtr(1),
                x=>x.Job=new IntPtr(2),x=>x.SourceToken=new IntPtr(3),x=>x.Process.process=new IntPtr(4),x=>x.Process.thread=new IntPtr(5),
                x=>x.Receipt.CreateAttempted=true,x=>x.Receipt.Created=true,x=>x.Receipt.Assigned=true,x=>x.Receipt.Resumed=true}) {
                trace=new PilotCmdObservationTrace(kind,false);change(trace.Subject);
                PilotObservationThrows(()=>trace.CaptureBatch(),"new capture freshness guard",ref checks);
                PilotObservationAssert(trace.Events.Count==0,"rejected before injected operation",ref checks);
            }
            trace=new PilotCmdObservationTrace(kind,false);
            PilotObservationThrows(()=>CapturePilotCmdBatchUsing(trace.Subject,trace.Evidence,trace.Operations),"original adapter still rejects observation",ref checks);
            PilotObservationThrows(()=>CapturePilotMinimalCmdBatchUsing(trace.Subject,trace.Evidence,trace.Operations),"old minimal adapter still rejects observation",ref checks);
            for(int index=0;index<9;index++) {
                trace=new PilotCmdObservationTrace(kind,false);trace.Bytes["pilot_cmd_batch_source"][index]^=1;
                PilotObservationThrows(()=>trace.CaptureBatch(),"each minimal source byte is exact",ref checks);
                PilotObservationAssert(!trace.Events.Contains("pilot_cmd_batch_destination:open"),"invalid payload never copied",ref checks);
            }
            foreach(byte[] payload in new byte[][]{new byte[]{0xef,0xbb,0xbf,0x65,0x78,0x69,0x74,0x20,0x32,0x33,0x0d,0x0a},
                System.Text.Encoding.ASCII.GetBytes("exit 23\n"),new byte[0],System.Text.Encoding.ASCII.GetBytes("exit 23\r"),System.Text.Encoding.ASCII.GetBytes("exit 23\r\nx")}) {
                trace=new PilotCmdObservationTrace(kind,false);trace.Bytes["pilot_cmd_batch_source"]=payload;
                PilotObservationThrows(trace.CaptureBatch,"minimal framing bytes are exact",ref checks);
                PilotObservationAssert(!trace.Events.Contains("pilot_cmd_batch_destination:open"),"invalid framing never copied",ref checks);
            }
        }
    }
    static void RunPilotObservationByteTests(ref int checks) {
        foreach(string kind in new string[]{"cmd-cwd","cmd-read-direct","cmd-relative-batch-exit23"}) {
            string status=kind=="cmd-cwd"?"cmd_cwd":kind=="cmd-read-direct"?"cmd_read_direct":"cmd_relative_batch_exit23";
            var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Observe();var row=trace.Row();
            PilotObservationAssert(PilotCmdObservationEvidenceVerified(row) && row.CmdCwdObserved==(kind=="cmd-cwd") &&
                row.CmdReadObserved==(kind=="cmd-read-direct") && row.CmdRelativeBatchExit23Observed==(kind=="cmd-relative-batch-exit23") &&
                PilotObservationNoExtraCredit(row),"raw positive grants only its own fact",ref checks);
            PilotObservationAssert(row.Status==status+"_raw_observed" &&
                row.CanaryClassification==(kind=="cmd-cwd"?"cwd":kind=="cmd-read-direct"?"read":"relative_batch")+"_observation_did_not_attempt_runtime_canary","exact classification vocabulary",ref checks);
            byte[] expected=(byte[])trace.Bytes["pilot_cmd_stdout_source"].Clone();
            var invalid=new List<byte[]>();
            if(expected.Length==0) invalid.AddRange(new byte[][]{new byte[]{0},new byte[]{0x78},new byte[]{0xef,0xbb,0xbf},
                new byte[]{0x0a},new byte[]{0x0d},new byte[]{0x0d,0x0a},System.Text.Encoding.ASCII.GetBytes("exit 23\r\n")});
            else {
                invalid.Add(new byte[0]);var truncated=new byte[expected.Length-1];
                Array.Copy(expected,truncated,truncated.Length);invalid.Add(truncated);
                foreach(string text in new string[]{"wrong path\r\n",trace.Subject.Workspace.ToUpperInvariant()+"\r\n",trace.Subject.Workspace+"\n",
                    trace.Subject.Workspace+"\r",trace.Subject.Workspace+"\r\n\r\n",trace.Subject.Workspace+"\0\r\n"}) invalid.Add(System.Text.Encoding.ASCII.GetBytes(text));
                var bom=new byte[expected.Length+3];bom[0]=0xef;bom[1]=0xbb;bom[2]=0xbf;Array.Copy(expected,0,bom,3,expected.Length);invalid.Add(bom);
                var extra=new byte[expected.Length+1];Array.Copy(expected,extra,expected.Length);invalid.Add(extra);
                for(int index=0;index<expected.Length;index++) {var changed=(byte[])expected.Clone();changed[index]^=1;invalid.Add(changed);}
            }
            foreach(byte[] output in invalid) {
                trace=new PilotCmdObservationTrace(kind,false);trace.Bytes["pilot_cmd_stdout_source"]=output;trace.Bytes["pilot_cmd_stdout_evidence"]=(byte[])output.Clone();
                trace.Terminal();trace.Observe();row=trace.Row();
                PilotObservationAssert(PilotNumber(row.Launcher,"pilot_cmd_observation_raw_complete",1) && !row.CmdCwdObserved && !row.CmdReadObserved && !row.CmdRelativeBatchExit23Observed &&
                    !row.Fatal && PilotObservationNoExtraCredit(row) && row.Status==status+"_raw_not_observed",
                    "raw output mismatch never normalizes or throws",ref checks);
            }
            trace=new PilotCmdObservationTrace(kind,false);trace.Bytes["pilot_cmd_stderr_source"]=new byte[]{0};trace.Bytes["pilot_cmd_stderr_evidence"]=new byte[]{0};
            trace.Terminal();trace.Observe();row=trace.Row();PilotObservationAssert(!row.CmdCwdObserved && !row.CmdReadObserved && !row.CmdRelativeBatchExit23Observed,"stderr must be empty",ref checks);
            trace=new PilotCmdObservationTrace(kind,true);trace.Terminal();trace.Observe();row=trace.Row();
            PilotObservationAssert(kind=="cmd-cwd"?(!row.CmdCwdObserved && row.Status=="cmd_cwd_expected_encoding_unsupported" &&
                PilotNumber(row.Launcher,"pilot_cmd_observation_expected_supported",0) && PilotNumber(row.Launcher,"pilot_cmd_observation_expected_bytes",-1) &&
                !row.Launcher.Identities.ContainsKey("pilot_cmd_observation_expected_sha256")):(kind=="cmd-read-direct"?row.CmdReadObserved:row.CmdRelativeBatchExit23Observed),"non-ASCII cwd unsupported, other observations independent",ref checks);
        }
    }
    static void RunPilotObservationReadTests(ref int checks) {
        string[] labels={"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"};
        foreach(string kind in new string[]{"cmd-cwd","cmd-relative-batch-exit23"}) {
            foreach(string label in labels) foreach(string fault in new string[]{"missing","open_zero","open_throw","open_error","open_result_missing","access","inherited",
                "validate_throw","revalidate_throw","reparse","directory","nonregular","multilink","oversize","high_size","zero_identity","changed_identity","metadata","length",
                "read_throw","read_null","raw_count","size_mismatch","trailing_byte","close_false","close_throw","close_kept","close_error","close_result_missing"}) {
                var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Fault=label+":"+fault;
                PilotObservationThrows(trace.Observe,"raw read failure: "+trace.Fault,ref checks);
                PilotObservationAssert(!PilotNumber(trace.Subject.Receipt,"pilot_cmd_observation_raw_complete",1),"incomplete never raw complete",ref checks);
                foreach(var close in trace.Closes) PilotObservationAssert(close.Value==1,"one close attempt, never retry: "+trace.Fault,ref checks);
                foreach(string acquired in labels) if(trace.Events.Contains(acquired+":open") && !(acquired==label && (fault=="missing" || fault=="open_zero")))
                    PilotObservationAssert(trace.Closes.ContainsKey(acquired),"every acquired handle receives close attempt",ref checks);
                if(fault=="close_false" || fault=="close_throw" || fault=="close_kept")
                    PilotObservationAssert(!trace.Subject.OwnershipCertain,"ambiguous close revokes ownership",ref checks);
            }
            foreach(string label in new string[]{labels[0],labels[2]}) {
                var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Fault=label+":wrong_identity";
                PilotObservationThrows(trace.Observe,"original stdio identity binding",ref checks);
            }
            foreach(string label in new string[]{labels[0],labels[1]}) {
                var trace=new PilotCmdObservationTrace(kind,false);
                if(kind=="cmd-relative-batch-exit23") trace.Bytes[labels[0]]=trace.Bytes[labels[1]]=new byte[]{1};
                trace.Terminal();trace.Fault=label+":early_eof";
                PilotObservationThrows(trace.Observe,"nonempty raw stream early EOF",ref checks);
            }
            foreach(string label in new string[]{labels[1],labels[3]}) {
                var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Bytes[label]=new byte[]{1};
                PilotObservationThrows(trace.Observe,"source/evidence bytes must agree",ref checks);
            }
            var aliased=new PilotCmdObservationTrace(kind,false);aliased.Terminal();var validate=aliased.Operations.Validate;
            aliased.Operations.Validate=delegate(IntPtr handle,string path,string identity) {
                var info=validate(handle,path,identity);
                if(path==Path.Combine(aliased.Evidence,"stdout.txt")) {info.volume=1;info.indexHigh=1;info.indexLow=2;}
                return info;
            };
            PilotObservationThrows(aliased.Observe,"artifact identity is independently measured and cannot alias source",ref checks);
            foreach(Action<PilotCmdObservationTrace> change in new Action<PilotCmdObservationTrace>[] {
                x=>x.Subject.OwnershipCertain=false,x=>x.Subject.ProfileCreated=false,x=>x.Subject.ProcessStopped=false,x=>x.Subject.JobDrained=false,
                x=>x.Subject.Process.process=new IntPtr(1),x=>x.Subject.Process.thread=new IntPtr(2),x=>x.Subject.Job=new IntPtr(3),
                x=>x.Subject.SourceToken=new IntPtr(4),x=>x.Subject.Sid=new IntPtr(5),x=>x.Subject.Receipt.Created=false,x=>x.Subject.Receipt.Resumed=false,
                x=>x.Operations.OpenRead=null,x=>x.Operations.Read=null,x=>x.Operations.Validate=null,x=>x.Operations.Close=null,
                x=>x.Evidence=x.Subject.Workspace,x=>x.Subject.Receipt.Identities["pilot_cmd_observation_cwd"]+="wrong"}) {
                var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Observe();trace.Events.Clear();change(trace);
                PilotObservationThrows(trace.Observe,"raw precondition fail-closed",ref checks);
                PilotObservationAssert(trace.Events.Count==0 && !PilotNumber(trace.Subject.Receipt,"pilot_cmd_observation_raw_complete",1),"gated retry clears stale raw completion",ref checks);
            }
            foreach(string file in new string[]{"stdout.txt","stderr.txt","canary.txt"}) {
                foreach(string suffix in new string[]{"_open_error","_close_error","_advertised_bytes","_copied_bytes"}) {
                    var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Subject.Receipt.Numbers.Remove("capture_"+file+suffix);
                    PilotObservationThrows(trace.Observe,"mandatory original capture field missing",ref checks);
                    PilotObservationAssert(trace.Events.Count==0,"no new read before mandatory captures finish",ref checks);
                }
                var missing=new PilotCmdObservationTrace(kind,false);missing.Terminal();missing.Subject.Receipt.Identities.Remove("capture_"+file);
                PilotObservationThrows(missing.Observe,"mandatory original capture identity missing",ref checks);
            }
            foreach(string key in new string[]{"individual_stop_drain_close_confirmed","exact_process_stop_confirmed","job_query_error","job_active_processes",
                "process_close_error","thread_close_error","job_close_error"}) {
                var trace=new PilotCmdObservationTrace(kind,false);trace.Terminal();trace.Subject.Receipt.Numbers.Remove(key);
                PilotObservationThrows(trace.Observe,"individual stop/drain/close is mandatory",ref checks);
                PilotObservationAssert(trace.Events.Count==0,"stop/drain/close gate precedes raw open",ref checks);
            }
            var readOnly=new PilotCmdObservationTrace(kind,false);readOnly.Terminal();readOnly.Operations.OpenWrite=null;readOnly.Operations.Write=null;readOnly.Observe();
            PilotObservationAssert((kind=="cmd-cwd"?readOnly.Row().CmdCwdObserved:readOnly.Row().CmdRelativeBatchExit23Observed),"raw reader requires no writable operation",ref checks);
            var complete=new PilotCmdObservationTrace(kind,false);complete.Terminal();complete.Observe();
            for(int index=0;index<labels.Length;index++) {
                PilotObservationAssert(complete.Closes[labels[index]]==1,"all four reads close once",ref checks);
                if(index>0) PilotObservationAssert(complete.Events.IndexOf(labels[index-1]+":close")<complete.Events.IndexOf(labels[index]+":open"),"raw handles are sequential",ref checks);
            }
            complete.Bytes[labels[1]]=new byte[]{1};
            PilotObservationThrows(complete.Observe,"failed reread cannot reuse earlier raw success",ref checks);
            PilotObservationAssert(!PilotNumber(complete.Subject.Receipt,"pilot_cmd_observation_raw_complete",1) &&
                !PilotNumber(complete.Subject.Receipt,"pilot_cmd_observation_stdout_matches",1),"retry clears all prior positive raw flags",ref checks);
        }
    }
    static void RunPilotObservationPredicateTests(ref int checks) {
        foreach(string kind in new string[]{"cmd-cwd","cmd-read-direct","cmd-relative-batch-exit23"}) {
            foreach(Action<PilotCaseReceipt> change in new Action<PilotCaseReceipt>[] {
                x=>x.Case="unknown",x=>x.Case="cmd",x=>x.Launcher.Kind="node",x=>x.Policy="fallback",x=>x.AuthorityObserved=false,x=>x.PreResumeReady=false,
                x=>x.NoCaseResourcesAllocated=true,x=>x.Launcher.CreationFlags^=0x10,x=>x.Launcher.ProfileSid=null,x=>x.Launcher.Drained=false,
                x=>x.Launcher.Executable=null,x=>x.Launcher.Executable+= "x",x=>x.Launcher.CommandLine+=" & echo injected",x=>x.Launcher.ExecutableSha256="invalid",
                x=>x.Launcher.ExecutableSha256=null,x=>x.Launcher.ExecutableSha256=new string('A',64),
                x=>x.Launcher.Identities.Remove("pilot_original_cmd_sha256"),x=>x.Launcher.Identities["pilot_original_cmd_sha256"]=new string('b',64),
                x=>x.Launcher.TokenVerified=true,x=>x.Launcher.CreateAttempted=false,x=>x.Launcher.Created=false,x=>x.Launcher.CreateError=5,
                x=>x.Launcher.Assigned=false,x=>x.Launcher.Resumed=false,x=>x.Launcher.Wait=WAIT_TIMEOUT,x=>x.Launcher.Wait=UInt32.MaxValue,
                x=>x.Launcher.Exit=1,x=>x.Launcher.Exit=kind=="cmd-relative-batch-exit23"?0u:23u,x=>x.Launcher.StdioValidated=false,x=>x.Launcher.HostStdioClosed=false,
                x=>x.Launcher.HandleListCount=4,x=>x.Launcher.Identities["stdin"]=x.Launcher.Identities["stdout"],
                x=>x.Launcher.Numbers["stdout_desired_access"]=0x80000000L,x=>x.Launcher.Numbers["stdout_handle_flags"]=0,
                x=>x.Launcher.Numbers["pilot_exit_query_success"]=0,x=>x.Launcher.Numbers["stdout_close_error"]=6,x=>x.Launcher.Numbers["lpac_fixed_query_success"]=1,
                x=>x.Launcher.Numbers["native_lpac_ntstatus_signed"]=0,x=>x.Launcher.Numbers["accesscheck_extra_api_success"]=1})
                PilotObservationReject(kind,change,"identity or execution evidence",ref checks);
            var baseline=PilotObservationRow(kind);
            foreach(string key in new List<string>(baseline.Launcher.Identities.Keys)) if(key.StartsWith("pilot_cmd_observation_",StringComparison.Ordinal) ||
                key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal) || key=="pilot_case_id") {
                PilotObservationReject(kind,x=>x.Launcher.Identities.Remove(key),"missing "+key,ref checks);
                PilotObservationReject(kind,x=>x.Launcher.Identities[key]="invalid","changed "+key,ref checks);
            }
            foreach(string key in new List<string>(baseline.Launcher.Numbers.Keys)) if(key.StartsWith("pilot_cmd_observation_",StringComparison.Ordinal) ||
                key.StartsWith("pilot_cmd_stdout_",StringComparison.Ordinal) || key.StartsWith("pilot_cmd_stderr_",StringComparison.Ordinal)) {
                PilotObservationReject(kind,x=>x.Launcher.Numbers.Remove(key),"missing "+key,ref checks);
                PilotObservationReject(kind,x=>x.Launcher.Numbers[key]++,"changed "+key,ref checks);
            }
            foreach(string key in new string[]{"pilot_exit_query_success","pilot_cmd_same_binary_verified","source_restricted_properties_verified","appcontainer_value",
                "capabilities_observation_success","duplicate_level_value","accesscheck_observer_completed","accesscheck_mixed_api_success","token_close_error",
                "native_lpac_call_completed","exact_process_stop_confirmed","individual_stop_drain_close_confirmed","job_query_error","job_active_processes"})
                PilotObservationReject(kind,x=>x.Launcher.Numbers.Remove(key),"missing observed policy/terminal fact "+key,ref checks);
            // Privilege-control diagnostics are retained by the old fixture but not required by its immutable predicate.
            foreach(string key in PilotPolicyTestReceipt(false).Numbers.Keys) if(!key.EndsWith("_privilege_control_raw",StringComparison.Ordinal))
                PilotObservationReject(kind,x=>x.Launcher.Numbers.Remove(key),"every original observed-policy number remains mandatory: "+key,ref checks);
            foreach(string key in PilotPolicyTestReceipt(false).Identities.Keys) if(key!="fixture_source_sha256")
                PilotObservationReject(kind,x=>x.Launcher.Identities.Remove(key),"every original observed-policy identity remains mandatory: "+key,ref checks);
            foreach(string key in new string[]{"pilot_cmd_observation_unknown","accesscheck_unknown","pilot_cmd_stdout_unknown","pilot_cmd_stderr_source_unknown"}) {
                PilotObservationReject(kind,x=>x.Launcher.Numbers[key]=1,"unknown schema number",ref checks);
                PilotObservationReject(kind,x=>x.Launcher.Identities[key]="claimed","unknown schema identity",ref checks);
            }
            PilotObservationReject(kind,x=>x.Launcher.Numbers=null,"missing raw number map",ref checks);
            PilotObservationReject(kind,x=>x.Launcher.Identities=null,"missing raw identity map",ref checks);
            foreach(string prefix in new string[]{"source_token","duplicate_token","accesscheck_mixed","native_lpac","setup_heap_0"})
                PilotObservationReject(kind,x=>x.Launcher.Identities[prefix+"_exception"]="IOException","observed policy exception",ref checks);
            string originalCwd=baseline.Launcher.Identities["pilot_cmd_observation_cwd"];
            foreach(string invalid in new string[]{originalCwd.Replace("synthetic-pilot","NUL"),originalCwd.Replace("synthetic-pilot","bad:name"),
                originalCwd.Replace("synthetic-pilot","trailing."),originalCwd.Replace("synthetic-pilot","trailing "),
                originalCwd.Replace("owned-0123456789abcdef0123456789abcdef","owned-invalid"),"relative\\workspace",@"C:\"}) {
                PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_observation_cwd"]=invalid,"unsafe cwd false without throwing",ref checks);
                var malformed=kind=="cmd-relative-batch-exit23"?PilotObservationEleven():PilotObservationTen();malformed[kind=="cmd-cwd"?8:kind=="cmd-read-direct"?9:10].Launcher.Identities["pilot_cmd_observation_cwd"]=invalid;
                PilotObservationAssert(kind=="cmd-cwd"?!PilotCmdCwdRawMatched(malformed):kind=="cmd-read-direct"?!PilotCmdReadRawMatched(malformed):!PilotCmdRelativeBatchRawMatched(malformed),"unsafe cwd reducer false without throwing",ref checks);
            }
            foreach(string label in new string[]{"pilot_cmd_stdout_source","pilot_cmd_stdout_evidence","pilot_cmd_stderr_source","pilot_cmd_stderr_evidence"})
                PilotObservationReject(kind,x=>x.Launcher.Identities[label+"_close_exception"]="IOException","ambiguous raw close",ref checks);
            foreach(string value in new string[]{"1:0:0","1:1:02","1:1:-1","1:1:4294967296",""})
                PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_stdout_evidence"]=value,"canonical measured artifact identity",ref checks);
            PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_stdout_evidence"]=x.Launcher.Identities["stdout"],"artifact/source ID alias",ref checks);
            var fatal=PilotObservationRow(kind);fatal.Fatal=true;fatal.Status="prior_failure";fatal.CmdCwdObserved=true;fatal.CmdReadObserved=true;fatal.CmdRelativeBatchExit23Observed=true;
            ClassifyPilotFacts(fatal,PilotCmdTestFacts());PilotObservationAssert(!fatal.CmdCwdObserved && !fatal.CmdReadObserved && !fatal.CmdRelativeBatchExit23Observed && fatal.Status=="prior_failure","fatal reclassification clears stale flags",ref checks);
            var timeout=PilotObservationRow(kind);timeout.Launcher.Wait=WAIT_TIMEOUT;ClassifyPilotFacts(timeout,PilotCmdTestFacts());
            PilotObservationAssert(timeout.Status=="deadline_exceeded" && !timeout.CmdCwdObserved && !timeout.CmdReadObserved && !timeout.CmdRelativeBatchExit23Observed,"timeout cannot use stale expected exit",ref checks);
            var noisy=PilotCmdTestFacts();noisy["stdout.txt"]="runtime-ok";noisy["script-entry.txt"]="runtime-entered";noisy["mutation.txt"]="runtime-ok";
            var row=PilotObservationRow(kind);ClassifyPilotFacts(row,noisy);PilotObservationAssert(PilotObservationNoExtraCredit(row),"normalized text grants no extra credit",ref checks);
            foreach(string fault in new string[]{"changed","absent","outside_write"}) {
                var files=PilotCmdTestFacts();if(fault=="changed") files["canary.txt"]="changed";if(fault=="absent") files.Remove("canary.txt");
                if(fault=="outside_write") files["probe-write.txt"]="";row=PilotObservationRow(kind);ClassifyPilotFacts(row,files);
                PilotObservationAssert(row.Fatal && !row.CmdCwdObserved && !row.CmdReadObserved && !row.CmdRelativeBatchExit23Observed && row.Status=="outside_boundary_failed","outside boundary precedes raw classification",ref checks);
            }
        }
        foreach(string kind in new string[]{"cmd-read-direct","cmd-relative-batch-exit23"}) {
            foreach(string part in new string[]{"source","destination","readback"}) foreach(string suffix in new string[]{"","_sha256"})
                PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_batch_"+part+suffix]="invalid","minimal capture identity/hash",ref checks);
            foreach(string part in new string[]{"source","destination","readback"})
                PilotObservationReject(kind,x=>x.Launcher.Numbers["pilot_cmd_batch_"+part+"_bytes"]=8,"minimal capture exact count",ref checks);
            foreach(string key in new string[]{"pilot_cmd_minimal_payload_verified","pilot_cmd_batch_capture_confirmed","pilot_cmd_batch_source_read_confirmed",
                "pilot_cmd_batch_destination_write_confirmed","pilot_cmd_batch_readback_read_confirmed","pilot_cmd_batch_source_close_confirmed",
                "pilot_cmd_batch_destination_close_confirmed","pilot_cmd_batch_readback_close_confirmed"})
                PilotObservationReject(kind,x=>x.Launcher.Numbers.Remove(key),"minimal source/write/readback proof mandatory",ref checks);
            PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_batch_stage"]="after_resume","minimal capture stage",ref checks);
            foreach(string part in new string[]{"source","destination","readback"})
                PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_batch_"+part+"_path"]="wrong","minimal capture exact path",ref checks);
            foreach(string value in new string[]{"7:0:0","7:0:015","7:0:-1","7:0:4294967296","","invalid"})
                PilotObservationReject(kind,x=>x.Launcher.Identities["pilot_cmd_batch_source"]=value,"canonical minimal source identity",ref checks);
        }
        var ready=PilotObservationRow("cmd-cwd");ready.Launcher.Assigned=false;ready.Launcher.Resumed=false;
        PilotObservationAssert(PilotMayResume(true,true,true,ready),"synthetic source satisfies unchanged pre-resume policy",ref checks);
        PilotObservationAssert(!PilotMayResume(false,true,true,ready),"ordinary witness is independently mandatory before resume",ref checks);
        ready=PilotObservationRow("cmd-cwd");
        PilotObservationAssert(!VerifyPilotSignature(ready.Launcher,false) && PilotCmdObservationEvidenceVerified(ready),"terminal raw predicate never reuses pre-resume verification",ref checks);
        PilotObservationAssert(!PilotCmdObservationEvidenceVerified(null),"missing raw row",ref checks);
        ready.Launcher=null;PilotObservationAssert(!PilotCmdObservationEvidenceVerified(ready),"missing launcher receipt",ref checks);
        foreach(Type type in new Type[]{typeof(PilotCaseReceipt),typeof(PilotRunReceipt)}) foreach(string name in new string[]{"CmdCwdObservationPassed","CmdReadObservationPassed","CmdRelativeBatchObservationPassed"})
            PilotObservationAssert(type.GetField(name)==null && type.GetProperty(name)==null,"producer has no accepted-result member",ref checks);
    }
    static List<PilotCaseReceipt> PilotObservationTen() {
        var rows=PilotCmdBatchTestEight();rows.Add(PilotObservationRow("cmd-cwd"));rows.Add(PilotObservationRow("cmd-read-direct"));
        PilotCmdBatchTestComplete(rows[8]);PilotCmdBatchTestComplete(rows[9]);return rows;
    }
    static List<PilotCaseReceipt> PilotObservationEleven() {
        var rows=PilotObservationTen();rows.Add(PilotObservationRow("cmd-relative-batch-exit23"));
        PilotCmdBatchTestComplete(rows[10]);return rows;
    }
    static void RunPilotObservationReducerTests(ref int checks) {
        var rows=PilotObservationTen();
        PilotObservationAssert(PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows),"both exact additive slots match",ref checks);
        PilotObservationAssert(PilotOriginalSixPassed(rows) && PilotCmdSentinelPassed(rows) && PilotCmdBatchPassed(rows),"old positive reducer baseline is nonvacuous",ref checks);
        PilotObservationAssert(!PilotCmdCwdRawMatched(null) && !PilotCmdReadRawMatched(null),"missing run rows",ref checks);
        int mutation=0;bool[] expectedCwd={true,true,false,false,false,false,false},expectedRead={false,false,true,false,false,false,false};
        foreach(Action<List<PilotCaseReceipt>> change in new Action<List<PilotCaseReceipt>>[]{
            x=>x.RemoveAt(9),x=>x[9]=null,x=>x[8]=null,x=>x[9]=x[8],x=>x[8]=x[9],
            x=>{var swap=x[8];x[8]=x[9];x[9]=swap;},x=>x.Insert(8,x[8])}) {
            rows=PilotObservationTen();change(rows);
            PilotObservationAssert(PilotCmdCwdRawMatched(rows)==expectedCwd[mutation] && PilotCmdReadRawMatched(rows)==expectedRead[mutation],
                "missing/duplicate/misplaced rows have exact independent outcomes",ref checks);mutation++;
        }
        rows=PilotObservationTen();rows[8].Launcher.Numbers["pilot_cmd_observation_stdout_matches"]=0;ClassifyPilotFacts(rows[8],PilotCmdTestFacts());
        PilotObservationAssert(!PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows),"failed cwd leaves TYPE independent",ref checks);
        rows=PilotObservationTen();rows[9].Launcher.Numbers["pilot_cmd_observation_stdout_matches"]=0;ClassifyPilotFacts(rows[9],PilotCmdTestFacts());
        PilotObservationAssert(PilotCmdCwdRawMatched(rows) && !PilotCmdReadRawMatched(rows),"failed TYPE leaves cwd independent",ref checks);
        rows=PilotObservationTen();rows[8].CmdCwdObserved=false;rows[9].CmdReadObserved=false;
        PilotObservationAssert(!PilotCmdCwdRawMatched(rows) && !PilotCmdReadRawMatched(rows),"unclassified raw facts do not silently gain row credit",ref checks);
        rows=PilotObservationTen();rows[8].CmdReadObserved=true;rows[9].CmdCwdObserved=true;
        PilotObservationAssert(!PilotCmdCwdRawMatched(rows) && !PilotCmdReadRawMatched(rows),"stale cross-case flags reject both reducers",ref checks);
        rows=PilotObservationTen();rows[3].PositivePassed=false;
        PilotObservationAssert(!PilotOriginalSixPassed(rows) && PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows),"both raw matches cannot rescue old runtime failure",ref checks);
        rows=PilotObservationEleven();
        PilotObservationAssert(PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows) && PilotCmdRelativeBatchRawMatched(rows),"all eleven-row raw slots match",ref checks);
        PilotObservationAssert(!PilotCmdRelativeBatchRawMatched(null) && !PilotCmdRelativeBatchRawMatched(PilotObservationTen()),"relative row is independently required",ref checks);
        foreach(Action<List<PilotCaseReceipt>> change in new Action<List<PilotCaseReceipt>>[]{
            x=>x.RemoveAt(10),x=>x[10]=null,x=>x[10].Case="cmd-batch-exit23",x=>x[9]=x[10],
            x=>{var swap=x[9];x[9]=x[10];x[10]=swap;},x=>x.Add(x[10]),
            x=>x[10].CmdCwdObserved=true,x=>x[10].CmdReadObserved=true,x=>x[10].CmdRelativeBatchExit23Observed=false}) {
            rows=PilotObservationEleven();change(rows);
            PilotObservationAssert(!PilotCmdRelativeBatchRawMatched(rows),"relative absent/duplicate/misplaced/stale row rejected",ref checks);
            if(rows.Count==12) PilotObservationAssert(!PilotCmdCwdRawMatched(rows) && !PilotCmdReadRawMatched(rows),"twelfth row rejects old reducers",ref checks);
        }
        foreach(int slot in new int[]{8,9}) {
            rows=PilotObservationEleven();rows[slot].CmdRelativeBatchExit23Observed=true;
            PilotObservationAssert(!(slot==8?PilotCmdCwdRawMatched(rows):PilotCmdReadRawMatched(rows)) && PilotCmdRelativeBatchRawMatched(rows),"old-row cross flag rejects only its own fact",ref checks);
        }
        foreach(uint exit in new uint[]{0,1}) {
            rows=PilotObservationEleven();rows[10].Launcher.Exit=exit;ClassifyPilotFacts(rows[10],PilotCmdTestFacts());
            PilotObservationAssert(!PilotCmdRelativeBatchRawMatched(rows) && PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows),"clean relative wrong exit leaves old facts independent",ref checks);
        }
        rows=PilotObservationEleven();rows[3].PositivePassed=false;
        PilotObservationAssert(!PilotOriginalSixPassed(rows) && PilotCmdCwdRawMatched(rows) && PilotCmdReadRawMatched(rows) && PilotCmdRelativeBatchRawMatched(rows),"all raw matches cannot rescue old cmd failure",ref checks);
        // Synthetic late-failure receipt shapes only, not claims of running persistence or cleanup failpoints.
        foreach(string stage in new string[]{"profile_delete","owned_root_remove","case_bind","case_verify","case_rename","case_serialize","case_create","case_write",
            "case_flush","case_close","matrix_serialize","matrix_create","matrix_write","matrix_flush","matrix_close","runroot_false","runroot_throw",
            "final_guard","final_identity_scan","pin_close_false","pin_close_throw","pin_close_uncertain","final_serialize","final_create","final_write","final_flush",
            "final_close","run_bind","run_verify","binding_content","binding_identity","binding_read","binding_close","run_rename"}) {
            rows=PilotObservationEleven();bool original=PilotOriginalSixPassed(rows),sentinel=PilotCmdSentinelPassed(rows),batch=PilotCmdBatchPassed(rows);
            var run=new PilotRunReceipt();run.Cases=rows;run.Failure="injected "+stage;run.RunRootRemoved=false;run.SelectedParent.CloseConfirmed=false;
            foreach(int slot in new int[]{8,9,10}) {
                var row=rows[slot];row.Fatal=true;row.Status="late_"+stage;row.Failure=stage;row.Launcher.Failure=stage;
                if(stage=="profile_delete") row.ProfileDeleteApiConfirmed=false;
                if(stage=="profile_delete" || stage=="owned_root_remove") {row.OwnedRootRemoved=false;row.CleanupPreconditionsConfirmed=false;}
                if(stage=="profile_delete" || stage=="owned_root_remove" || stage=="case_bind" || stage=="case_verify" || stage=="case_rename") {
                    row.CaseMarkerResolved=false;row.ScopedLifecycleCleanupConfirmed=false;
                }
                if(stage=="case_close") row.Launcher.Numbers["evidence_case_receipt_close_error"]=6;
                row.Launcher.Identities["journal_late_"+stage+"_exception"]="IOException";
            }
            run.CmdCwdRawObservationMatched=PilotCmdCwdRawMatched(rows);run.CmdReadRawObservationMatched=PilotCmdReadRawMatched(rows);
            run.CmdRelativeBatchRawObservationMatched=PilotCmdRelativeBatchRawMatched(rows);
            PilotObservationAssert(run.CmdCwdRawObservationMatched && run.CmdReadRawObservationMatched && rows[8].CmdCwdObserved && rows[9].CmdReadObserved &&
                run.CmdRelativeBatchRawObservationMatched && rows[10].CmdRelativeBatchExit23Observed,
                "late failure preserves already measured raw truth: "+stage,ref checks);
            PilotObservationAssert(PilotOriginalSixPassed(rows)==original && PilotCmdSentinelPassed(rows)==sentinel && PilotCmdBatchPassed(rows)==batch,
                "old reducers unchanged through late failure: "+stage,ref checks);
            PilotObservationAssert(!PilotMayAdvance(rows[8]) && !PilotMayAdvance(rows[9]) && !PilotMayAdvance(rows[10]) && run.Failure!=null,"raw match cannot erase failure",ref checks);
        }
    }
}
