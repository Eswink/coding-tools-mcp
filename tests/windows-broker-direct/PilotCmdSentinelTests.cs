// Managed-only tests: synthetic receipts/streams and injected file operations, never native calls.
using System;
using System.IO;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    static void PilotCmdTestAssert(bool condition,string label,ref int checks) {
        checks++;if(!condition) throw new InvalidOperationException("managed cmd sentinel contract: "+label);
    }
    sealed class PilotCmdTestStream : MemoryStream {
        public string Fault;
        public PilotCmdTestStream(byte[] bytes,string fault) : base(bytes,false) {Fault=fault;}
        public override int Read(byte[] buffer,int offset,int count) {
            if(Fault=="read_error") throw new IOException("synthetic raw read error");
            if(Fault=="early_eof") return 0;
            return base.Read(buffer,offset,Fault=="fragmented"?Math.Min(1,count):count);
        }
        public override int ReadByte() {return Fault=="extra_byte"?0:base.ReadByte();}
        public override long Length {get {return base.Length+(Fault=="length_change" && Position>0?1:0);}}
    }
    sealed class PilotCmdTestCapture {
        public string Fault;
        public byte[] Source,Written;
        public QualificationSubject Subject;
        public PilotCmdCaptureOperations Operations;
        public List<string> Events;
        public int SourceCloses,DestinationCloses,ReadbackCloses,SourceValidations,DestinationValidations,ReadbackValidations;
        public PilotCmdTestCapture(string fault) {
            Fault=fault;Source=new byte[]{0x40,0x65,0x63,0x68,0x6f,0x20,0xff,0x00,0x0d,0x0a,0x1a};
            Events=new List<string>();Subject=new QualificationSubject();Subject.Receipt.Kind="cmd";
            Subject.Receipt.Identities["pilot_case_id"]="cmd";
            Subject.Workspace=Path.Combine(Path.GetPathRoot(Environment.CurrentDirectory),"synthetic-workspace");
            Operations=new PilotCmdCaptureOperations();Operations.OpenRead=OpenRead;Operations.OpenWrite=OpenWrite;
            Operations.Validate=Validate;Operations.Read=Read;Operations.Write=Write;Operations.Close=Close;
        }
        void OpenRead(ref IntPtr handle,string path,string label,DirectReceipt receipt) {
            bool source=label=="pilot_cmd_batch_source";string prefix=source?"source":"readback";Events.Add(prefix+"_open");
            if(Fault==prefix+"_missing") throw new FileNotFoundException("synthetic missing capture");
            handle=new IntPtr(source?1:3);
            if(Fault==prefix+"_open_error") throw new IOException("synthetic failure after owned read open");
            receipt.Numbers[label+"_open_error"]=0;receipt.Numbers[label+"_handle_flags"]=0;
        }
        void OpenWrite(ref IntPtr handle,string path,string label,DirectReceipt receipt) {
            Events.Add("destination_open");
            if(Fault=="destination_exists") throw new IOException("synthetic CREATE_NEW collision");
            handle=new IntPtr(2);receipt.Identities[label]="7:0:22";
            if(Fault=="destination_open_error") throw new IOException("synthetic failure after owned write open");
        }
        FILE_INFO Validate(IntPtr handle,string path,string identity) {
            int id=handle.ToInt32();string prefix=id==1?"source":id==2?"destination":"readback";
            int calls=id==1?++SourceValidations:id==2?++DestinationValidations:++ReadbackValidations;
            Events.Add(prefix+"_validate");
            if(Fault==prefix+"_nonregular") throw new InvalidOperationException("synthetic nondisk object");
            FILE_INFO info=new FILE_INFO();info.attributes=0x80;info.links=1;info.volume=7;info.indexLow=id==1?11u:22u;
            info.sizeLow=(uint)(id==1?Source.Length:Written==null?0:Written.Length);info.creationLow=17;info.writeLow=19;
            if(Fault==prefix+"_reparse") info.attributes|=0x400;
            if(Fault==prefix+"_directory") info.attributes|=0x10;
            if(Fault==prefix+"_multilink") info.links=2;
            if(Fault==prefix+"_oversize") info.sizeLow=PilotCmdBatchLimit+1;
            if(Fault==prefix+"_high_size") info.sizeHigh=1;
            if(Fault==prefix+"_zero_identity") info.indexLow=0;
            if(Fault==prefix+"_identity" && (calls==2 || id==3)) info.indexLow=999;
            if(Fault==prefix+"_metadata" && calls==2) info.writeLow++;
            if(Fault==prefix+"_length" && calls==2) info.sizeLow++;
            if(Fault=="destination_nonempty" && id==2 && calls==1) info.sizeLow=1;
            if(Fault=="destination_creation" && id==2 && calls==2) info.creationLow++;
            return info;
        }
        byte[] Read(IntPtr handle,long size) {
            string prefix=handle.ToInt32()==1?"source":"readback";Events.Add(prefix+"_read");
            if(Fault==prefix+"_read_error") throw new IOException("synthetic read error");
            byte[] value=handle.ToInt32()==1?Source:Written;
            if(Fault==prefix+"_raw_count") return new byte[value.Length+1];
            byte[] result=(byte[])value.Clone();
            if(Fault=="readback_bytes" && handle.ToInt32()==3) result[0]^=1;
            using(var stream=new MemoryStream(result,false)) return ReadPilotCmdRawBytes(stream,size);
        }
        void Write(IntPtr handle,byte[] bytes) {
            Events.Add("destination_write");
            if(Fault=="destination_write_error") throw new IOException("synthetic write error");
            Written=(byte[])bytes.Clone();
            if(Fault=="destination_flush_error") throw new IOException("synthetic flush error");
        }
        bool Close(ref IntPtr handle,string label,DirectReceipt receipt) {
            int id=handle.ToInt32();string prefix=id==1?"source":id==2?"destination":"readback";
            Events.Add(prefix+"_close");
            if(id==1) SourceCloses++;else if(id==2) DestinationCloses++;else ReadbackCloses++;
            // A throwing adapter intentionally leaves its argument set; the caller must already have transferred ownership.
            if(Fault==prefix+"_close_throw") throw new IOException("synthetic close throw");
            if(Fault==prefix+"_close_kept") return true;
            handle=IntPtr.Zero;return Fault!=prefix+"_close_false";
        }
        public void Capture() {
            CapturePilotCmdBatchUsing(Subject,Path.Combine(Path.GetPathRoot(Environment.CurrentDirectory),"synthetic-evidence"),Operations);
        }
    }
    static PilotCaseReceipt PilotCmdTestRow() {
        var row=new PilotCaseReceipt();row.Case="cmd-exit23";row.Launcher.Kind="cmd";
        row.Launcher.Identities["pilot_case_id"]="cmd-exit23";row.Launcher.ExecutableSha256=new string('a',64);
        row.Launcher.Identities["pilot_original_cmd_sha256"]=row.Launcher.ExecutableSha256;
        row.Launcher.Numbers["pilot_cmd_same_binary_verified"]=1;row.Launcher.Numbers["pilot_exit_query_success"]=1;
        row.AuthorityObserved=true;row.PreResumeReady=true;row.Launcher.CreateAttempted=true;row.Launcher.Created=true;
        row.Launcher.CreateError=0;row.Launcher.Assigned=true;row.Launcher.Resumed=true;row.Launcher.Wait=WAIT_OBJECT_0;row.Launcher.Exit=23;
        return row;
    }
    static Dictionary<string,string> PilotCmdTestFacts() {
        var facts=new Dictionary<string,string>(StringComparer.Ordinal);facts.Add("canary.txt","synthetic-outside-canary");
        facts.Add("stdout.txt","");facts.Add("stderr.txt","");return facts;
    }
    static List<PilotCaseReceipt> PilotCmdTestOriginalSix() {
        var rows=new List<PilotCaseReceipt>();
        foreach(string kind in new string[]{"ordinary","reference","node","cmd","powershell","pwsh"}) {
            var row=new PilotCaseReceipt();row.Case=kind;row.Launcher.Kind=kind;
            row.IndividualResourceCleanupConfirmed=true;row.CaptureIntegrityConfirmed=true;row.ProfileDeleteApiConfirmed=true;
            row.OwnedRootRemoved=true;row.CleanupPreconditionsConfirmed=true;row.CaseMarkerResolved=true;row.ScopedLifecycleCleanupConfirmed=true;
            row.OrdinarySignatureMatched=kind=="ordinary";row.OrdinaryRejected=kind=="ordinary";
            row.OfflineReferenceRouteValid=kind=="reference";row.PositivePassed=kind!="ordinary" && kind!="reference";rows.Add(row);
        }
        return rows;
    }
    public static int RunPilotCmdSentinelContractTests() {
        int checks=0;string exe=Path.Combine(Path.GetPathRoot(Environment.CurrentDirectory),"private code","cmd.exe");
        PilotCmdTestAssert(FixedPilotCmdSentinelCommand(exe)==Quote(exe)+" /d /q /c exit 23","exact builtin command",ref checks);
        foreach(string path in new string[]{"relative/cmd.exe",exe.Replace("cmd.exe","other.exe"),exe+"&other"}) {
            bool rejected=false;try {FixedPilotCmdSentinelCommand(path);} catch(ArgumentException) {rejected=true;}
            PilotCmdTestAssert(rejected,"command path rejection",ref checks);
        }
        var row=PilotCmdTestRow();ClassifyPilotFacts(row,PilotCmdTestFacts());
        PilotCmdTestAssert(row.CmdExit23Observed && row.Status=="cmd_exit23_observed" && !row.PositivePassed && !row.ScriptEntryObserved &&
            !row.OutputOk && !row.MutationOk && !row.OfflineReferenceRouteValid && !row.NetworkDenialProven &&
            row.CanaryClassification=="sentinel_did_not_attempt_runtime_canary","only builtin exit observed",ref checks);
        foreach(uint exit in new uint[]{0,1,UInt32.MaxValue,259,0xC0000135}) {
            row=PilotCmdTestRow();row.Launcher.Exit=exit;row.CmdExit23Observed=true;ClassifyPilotFacts(row,PilotCmdTestFacts());
            PilotCmdTestAssert(!row.CmdExit23Observed && !row.PositivePassed && row.Status=="cmd_exit23_not_observed","non23 never passes",ref checks);
        }
        foreach(Action<PilotCaseReceipt> mutate in new Action<PilotCaseReceipt>[]{
            x=>x.Launcher.Kind="node",x=>x.Launcher.Identities.Remove("pilot_case_id"),x=>x.Launcher.Identities["pilot_case_id"]="cmd",
            x=>x.Launcher.Numbers.Remove("pilot_cmd_same_binary_verified"),x=>x.Launcher.Numbers["pilot_cmd_same_binary_verified"]=0,
            x=>x.Launcher.Numbers.Remove("pilot_exit_query_success"),x=>x.Launcher.Numbers["pilot_exit_query_success"]=0,
            x=>x.Launcher.Identities.Remove("pilot_original_cmd_sha256"),x=>x.Launcher.Identities["pilot_original_cmd_sha256"]=new string('b',64),
            x=>x.Launcher.ExecutableSha256=null,x=>x.Launcher.ExecutableSha256="invalid",x=>x.Launcher.ExecutableSha256=new string('Z',64),
            x=>x.AuthorityObserved=false,x=>x.PreResumeReady=false,x=>x.Launcher.CreateAttempted=false,x=>x.Launcher.Created=false,
            x=>x.Launcher.CreateError=5,x=>x.Launcher.Assigned=false,x=>x.Launcher.Resumed=false,x=>x.Launcher.Wait=UInt32.MaxValue}) {
            row=PilotCmdTestRow();row.CmdExit23Observed=true;row.PositivePassed=true;mutate(row);ClassifyPilotFacts(row,PilotCmdTestFacts());
            PilotCmdTestAssert(!row.CmdExit23Observed && !row.PositivePassed,"incomplete or malformed sentinel evidence",ref checks);
        }
        row=PilotCmdTestRow();row.Launcher.Wait=WAIT_TIMEOUT;ClassifyPilotFacts(row,PilotCmdTestFacts());
        PilotCmdTestAssert(!row.CmdExit23Observed && row.Status=="deadline_exceeded","sentinel timeout",ref checks);
        row=PilotCmdTestRow();row.Case="cmd";ClassifyPilotFacts(row,PilotCmdTestFacts());
        PilotCmdTestAssert(!row.CmdExit23Observed && !row.PositivePassed,"original cmd never gets sentinel credit",ref checks);
        foreach(string mutation in new string[]{"changed","absent","outside_write"}) {
            var facts=PilotCmdTestFacts();if(mutation=="changed") facts["canary.txt"]="changed";
            if(mutation=="absent") facts.Remove("canary.txt");if(mutation=="outside_write") facts["probe-write.txt"]="";
            row=PilotCmdTestRow();row.CmdExit23Observed=true;ClassifyPilotFacts(row,facts);
            PilotCmdTestAssert(row.Fatal && !row.CmdExit23Observed && !row.PositivePassed && row.Status=="outside_boundary_failed","outside boundary precedes sentinel",ref checks);
        }
        row=PilotCmdTestRow();row.Fatal=true;row.CmdExit23Observed=true;row.Status="prior_failure";ClassifyPilotFacts(row,PilotCmdTestFacts());
        PilotCmdTestAssert(!row.CmdExit23Observed && row.Status=="prior_failure","fatal stale result reset",ref checks);
        var noisy=PilotCmdTestFacts();noisy["stdout.txt"]="runtime-ok";noisy["stderr.txt"]="unexpected output";
        noisy["script-entry.txt"]="runtime-entered";noisy["mutation.txt"]="runtime-ok";
        row=PilotCmdTestRow();ClassifyPilotFacts(row,noisy);
        PilotCmdTestAssert(row.CmdExit23Observed && !row.ScriptEntryObserved && !row.OutputOk && !row.MutationOk && !row.PositivePassed,
            "unexpected output does not prove script support",ref checks);
        var originals=PilotCmdTestOriginalSix();PilotCmdTestAssert(PilotOriginalSixPassed(originals),"original six complete",ref checks);
        foreach(bool success in new bool[]{true,false}) {
            var seven=PilotCmdTestOriginalSix();var sentinel=PilotCmdTestRow();sentinel.CmdExit23Observed=success;sentinel.Fatal=!success;seven.Add(sentinel);
            PilotCmdTestAssert(PilotOriginalSixPassed(seven),"sentinel outcome independent of original aggregate",ref checks);
            seven[3].PositivePassed=false;PilotCmdTestAssert(!PilotOriginalSixPassed(seven),"sentinel cannot rescue original cmd failure",ref checks);
        }
        for(int i=0;i<6;i++) {
            int slot=i;
            foreach(Action<PilotCaseReceipt> mutate in new Action<PilotCaseReceipt>[]{x=>x.Fatal=true,x=>x.Case="cmd-exit23",x=>x.Launcher.Kind="unknown",
                x=>x.IndividualResourceCleanupConfirmed=false,x=>x.CaptureIntegrityConfirmed=false,x=>x.ProfileDeleteApiConfirmed=false,
                x=>x.OwnedRootRemoved=false,x=>x.CleanupPreconditionsConfirmed=false,x=>x.CaseMarkerResolved=false,x=>x.ScopedLifecycleCleanupConfirmed=false}) {
                originals=PilotCmdTestOriginalSix();mutate(originals[slot]);PilotCmdTestAssert(!PilotOriginalSixPassed(originals),"original cleanup and identity mandatory",ref checks);
            }
        }
        originals=PilotCmdTestOriginalSix();originals.RemoveAt(5);PilotCmdTestAssert(!PilotOriginalSixPassed(originals),"six rows required",ref checks);
        originals=PilotCmdTestOriginalSix();originals.Add(originals[3]);PilotCmdTestAssert(PilotOriginalSixPassed(originals),"duplicate additive identity cannot rewrite originals",ref checks);
        originals=PilotCmdTestOriginalSix();originals.Add(null);PilotCmdTestAssert(PilotOriginalSixPassed(originals),"missing additive row cannot rewrite originals",ref checks);
        originals=PilotCmdTestOriginalSix();var unknown=new PilotCaseReceipt();unknown.Case="unknown";originals.Add(unknown);
        PilotCmdTestAssert(PilotOriginalSixPassed(originals),"unknown additive row cannot rewrite originals",ref checks);
        originals=PilotCmdTestOriginalSix();originals.Add(PilotCmdTestRow());originals.Add(PilotCmdTestRow());
        PilotCmdTestAssert(PilotOriginalSixPassed(originals),"extra additive rows cannot rewrite originals",ref checks);
        originals=PilotCmdTestOriginalSix();var swap=originals[2];originals[2]=originals[3];originals[3]=swap;
        PilotCmdTestAssert(!PilotOriginalSixPassed(originals),"original ordering fixed",ref checks);
        row=PilotCmdTestOriginalSix()[3];row.Case="cmd-exit23";row.PositivePassed=false;row.Launcher.Exit=1;
        PilotCmdTestAssert(PilotMayAdvance(row),"contained non23 may resolve scoped cleanup",ref checks);
        row.CaseMarkerResolved=false;PilotCmdTestAssert(!PilotMayAdvance(row),"uncertain sentinel marker blocks progression",ref checks);
        byte[] raw=new byte[]{0x00,0xff,0x0d,0x0a,0x1a};
        foreach(string fault in new string[]{"","fragmented"}) {
            using(var stream=new PilotCmdTestStream(raw,fault)) PilotCmdTestAssert(PilotCmdRawEqual(raw,ReadPilotCmdRawBytes(stream,raw.Length)),"exact raw CRLF and trailing bytes",ref checks);
        }
        foreach(string fault in new string[]{"read_error","early_eof","extra_byte","length_change"}) {
            bool rejected=false;try {using(var stream=new PilotCmdTestStream(raw,fault)) ReadPilotCmdRawBytes(stream,raw.Length);} catch(Exception) {rejected=true;}
            PilotCmdTestAssert(rejected,"raw stream failure rejected",ref checks);
        }
        foreach(long length in new long[]{-1,raw.Length-1,raw.Length+1,PilotCmdBatchLimit+1L}) {
            bool rejected=false;try {using(var stream=new MemoryStream(raw,false)) ReadPilotCmdRawBytes(stream,length);} catch(InvalidOperationException) {rejected=true;}
            PilotCmdTestAssert(rejected,"advertised bound and count rejected",ref checks);
        }
        foreach(int length in new int[]{0,PilotCmdBatchLimit}) {
            var bounded=new byte[length];using(var stream=new MemoryStream(bounded,false))
                PilotCmdTestAssert(ReadPilotCmdRawBytes(stream,length).Length==length,"exact size endpoints",ref checks);
        }
        PilotCmdTestAssert(PilotCmdRawHash(new byte[0])=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","raw SHA256 fixture",ref checks);
        var capture=new PilotCmdTestCapture("");byte[] original=(byte[])capture.Source.Clone();capture.Capture();
        PilotCmdTestAssert(PilotCmdRawEqual(original,capture.Source) && PilotCmdRawEqual(original,capture.Written),"original batch never rewritten or normalized",ref checks);
        PilotCmdTestAssert(capture.Subject.OwnershipCertain && PilotNumber(capture.Subject.Receipt,"pilot_cmd_batch_capture_confirmed",1) &&
            capture.SourceCloses==1 && capture.DestinationCloses==1 && capture.ReadbackCloses==1,"all capture closes confirmed",ref checks);
        PilotCmdTestAssert(capture.Events.IndexOf("source_close")<capture.Events.IndexOf("destination_open") &&
            capture.Events.IndexOf("destination_close")<capture.Events.IndexOf("readback_open"),"capture handles release in bounded stages",ref checks);
        PilotCmdTestAssert(PilotIdentity(capture.Subject.Receipt,"pilot_cmd_batch_source_sha256",PilotCmdRawHash(original)) &&
            PilotIdentity(capture.Subject.Receipt,"pilot_cmd_batch_destination_sha256",PilotCmdRawHash(original)) &&
            PilotIdentity(capture.Subject.Receipt,"pilot_cmd_batch_readback_sha256",PilotCmdRawHash(original)) &&
            PilotNumber(capture.Subject.Receipt,"pilot_cmd_batch_source_bytes",original.Length),"raw capture hashes and counts match",ref checks);
        foreach(string fault in new string[]{"source_missing","source_open_error","source_reparse","source_directory","source_nonregular","source_multilink",
            "source_oversize","source_high_size","source_zero_identity","source_identity","source_metadata","source_length","source_read_error","source_raw_count",
            "destination_exists","destination_open_error","destination_nonempty","destination_reparse","destination_nonregular","destination_multilink",
            "destination_identity","destination_length","destination_creation","destination_write_error","destination_flush_error",
            "readback_missing","readback_open_error","readback_reparse","readback_nonregular","readback_multilink","readback_identity","readback_metadata",
            "readback_length","readback_read_error","readback_raw_count","readback_bytes","source_close_false","source_close_throw",
            "destination_close_false","destination_close_throw","readback_close_false","readback_close_throw",
            "source_close_kept","destination_close_kept","readback_close_kept"}) {
            capture=new PilotCmdTestCapture(fault);bool rejected=false;try {capture.Capture();} catch(Exception) {rejected=true;}
            PilotCmdTestAssert(rejected && !PilotNumber(capture.Subject.Receipt,"pilot_cmd_batch_capture_confirmed",1),"capture failure is mandatory: "+fault,ref checks);
            PilotCmdTestAssert(!capture.Subject.ProfileCreated && !capture.Subject.Receipt.CreateAttempted && capture.Subject.Process.process==IntPtr.Zero,
                "capture failure precedes profile and process: "+fault,ref checks);
            bool destinationOwned=capture.Events.Contains("destination_open") && fault!="destination_exists";
            bool readbackOwned=capture.Events.Contains("readback_open") && fault!="readback_missing";
            PilotCmdTestAssert(capture.SourceCloses==(fault=="source_missing"?0:1) && capture.DestinationCloses==(destinationOwned?1:0) &&
                capture.ReadbackCloses==(readbackOwned?1:0),"every acquired handle closes once without retry: "+fault,ref checks);
            if(fault.Contains("close_")) PilotCmdTestAssert(!capture.Subject.OwnershipCertain,"false or throwing close invalidates ownership: "+fault,ref checks);
        }
        foreach(Action<QualificationSubject> mutate in new Action<QualificationSubject>[]{
            x=>x.Receipt.Identities["pilot_case_id"]="cmd-exit23",x=>x.Receipt.Kind="node",x=>x.ProfileCreated=true,
            x=>x.Receipt.CreateAttempted=true,x=>x.Receipt.Created=true,x=>x.OwnershipCertain=false,x=>x.Sid=new IntPtr(1),
            x=>x.Job=new IntPtr(2),x=>x.SourceToken=new IntPtr(3),x=>x.Process.process=new IntPtr(4)}) {
            capture=new PilotCmdTestCapture("");mutate(capture.Subject);bool rejected=false;try {capture.Capture();} catch(InvalidOperationException) {rejected=true;}
            PilotCmdTestAssert(rejected && capture.Events.Count==0,"exact original preallocation guard",ref checks);
        }
        return checks;
    }
}
