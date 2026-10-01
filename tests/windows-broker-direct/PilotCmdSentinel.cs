// Additive CI-only builtin observation and raw original-batch evidence capture.
using System;
using System.IO;
using System.Collections.Generic;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

public static partial class BrokerDirectLauncher {
    const int PilotCmdBatchLimit=1024*1024;
    delegate void PilotCmdCaptureOpen(ref IntPtr handle,string path,string label,DirectReceipt receipt);
    delegate bool PilotCmdCaptureClose(ref IntPtr handle,string label,DirectReceipt receipt);
    sealed class PilotCmdCaptureOperations {
        public PilotCmdCaptureOpen OpenRead,OpenWrite;
        public Func<IntPtr,string,string,FILE_INFO> Validate;
        public Func<IntPtr,long,byte[]> Read;
        public Action<IntPtr,byte[]> Write;
        public PilotCmdCaptureClose Close;
    }
    static string FixedPilotCmdSentinelCommand(string privateCmdExe) {
        SafePath(privateCmdExe);
        if(Path.GetFileName(privateCmdExe)!="cmd.exe") throw new ArgumentException("fixed private cmd executable required");
        return Quote(privateCmdExe)+" /d /q /c exit 23";
    }
    static bool PilotCmdSha256(string value) {
        if(value==null || value.Length!=64) return false;
        foreach(char c in value) if(!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
        return true;
    }
    static string PilotCmdRawHash(byte[] bytes) {
        using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
    }
    static bool PilotCmdRawEqual(byte[] left,byte[] right) {
        if(left==null || right==null || left.Length!=right.Length) return false;
        for(int i=0;i<left.Length;i++) if(left[i]!=right[i]) return false;
        return true;
    }
    static string PilotCmdFileIdentity(FILE_INFO info) {
        return info.volume+":"+info.indexHigh+":"+info.indexLow;
    }
    static long PilotCmdBatchLength(FILE_INFO info) {
        if((info.attributes&0x450)!=0 || info.links!=1 || (info.indexHigh==0 && info.indexLow==0) ||
            info.sizeHigh!=0 || info.sizeLow>PilotCmdBatchLimit)
            throw new InvalidOperationException("cmd batch must remain one bounded ordinary file");
        return info.sizeLow;
    }
    static bool PilotCmdStableMetadata(FILE_INFO before,FILE_INFO after) {
        return before.attributes==after.attributes && before.creationLow==after.creationLow && before.creationHigh==after.creationHigh &&
            before.writeLow==after.writeLow && before.writeHigh==after.writeHigh && before.volume==after.volume &&
            before.sizeHigh==after.sizeHigh && before.sizeLow==after.sizeLow && before.links==after.links &&
            before.indexHigh==after.indexHigh && before.indexLow==after.indexLow;
    }
    static byte[] ReadPilotCmdRawBytes(Stream stream,long advertised) {
        if(stream==null || !stream.CanRead || !stream.CanSeek || advertised<0 || advertised>PilotCmdBatchLimit ||
            stream.Position!=0 || stream.Length!=advertised) throw new InvalidOperationException("cmd batch length unavailable or outside bound");
        var bytes=new byte[(int)advertised];int total=0;
        while(total<bytes.Length) {
            int read=stream.Read(bytes,total,bytes.Length-total);
            if(read<=0 || read>bytes.Length-total) throw new InvalidOperationException("cmd batch ended before its advertised length");
            total+=read;
        }
        // One EOF probe detects trailing bytes; no extra byte is accepted into the bounded capture.
        if(stream.ReadByte()!=-1 || stream.Position!=advertised || stream.Length!=advertised)
            throw new InvalidOperationException("cmd batch trailing bytes or changing length");
        return bytes;
    }
    static PilotCmdCaptureOperations PilotCmdNativeCaptureOperations() {
        var ops=new PilotCmdCaptureOperations();
        ops.OpenRead=delegate(ref IntPtr h,string path,string label,DirectReceipt r) {PilotOpenHandle(ref h,path,0x80000000,false,label,r);};
        ops.OpenWrite=delegate(ref IntPtr h,string path,string label,DirectReceipt r) {OpenPrivate(ref h,path,0x40000000,1,false,label,r);};
        ops.Validate=delegate(IntPtr h,string path,string identity) {return PilotValidateObject(h,path,false,identity,null);};
        ops.Read=delegate(IntPtr h,long size) {
            using(var safe=new SafeFileHandle(h,false)) using(var stream=new FileStream(safe,FileAccess.Read))
                return ReadPilotCmdRawBytes(stream,size);
        };
        ops.Write=WritePilotBytes;ops.Close=PilotCloseHandle;
        return ops;
    }
    static bool ClosePilotCmdCaptureHandle(ref IntPtr handle,string label,QualificationSubject s,PilotCmdCaptureOperations ops) {
        if(handle==IntPtr.Zero) return true;
        // Transfer before calling the adapter: a false or throwing close is never retried.
        IntPtr owned=handle;handle=IntPtr.Zero;bool closed=false;
        try {closed=ops.Close(ref owned,label,s.Receipt) && owned==IntPtr.Zero;}
        catch(Exception failure) {s.Receipt.Identities[label+"_close_exception"]=failure.GetType().Name;}
        s.Receipt.Numbers[label+"_close_confirmed"]=closed?1:0;
        if(!closed) s.OwnershipCertain=false;
        return closed;
    }
    static byte[] ReadPilotCmdCapture(QualificationSubject s,string path,string identity,string label,PilotCmdCaptureOperations ops) {
        DirectReceipt r=s.Receipt;IntPtr handle=IntPtr.Zero;bool closed=false;byte[] bytes=null;
        r.Identities[label+"_path"]=path;r.Numbers[label+"_read_confirmed"]=0;
        try {
            ops.OpenRead(ref handle,path,label,r);
            FILE_INFO before=ops.Validate(handle,path,identity);long size=PilotCmdBatchLength(before);
            string observed=PilotCmdFileIdentity(before);
            if(identity!=null && observed!=identity) throw new InvalidOperationException("cmd batch identity changed before read");
            r.Identities[label]=observed;r.Numbers[label+"_advertised_bytes"]=size;
            bytes=ops.Read(handle,size);
            if(bytes==null || bytes.Length!=size || bytes.Length>PilotCmdBatchLimit)
                throw new InvalidOperationException("cmd batch raw count mismatch");
            FILE_INFO after=ops.Validate(handle,path,observed);PilotCmdBatchLength(after);
            if(!PilotCmdStableMetadata(before,after)) throw new InvalidOperationException("cmd batch metadata changed during read");
            r.Numbers[label+"_bytes"]=bytes.Length;r.Identities[label+"_sha256"]=PilotCmdRawHash(bytes);
            r.Numbers[label+"_read_confirmed"]=1;
        } finally {closed=ClosePilotCmdCaptureHandle(ref handle,label,s,ops);}
        if(!closed) throw new InvalidOperationException("cmd batch read close uncertain");
        return bytes;
    }
    static void CapturePilotCmdBatchUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops) {
        if(s==null || s.Receipt==null || !s.OwnershipCertain || s.ProfileCreated || s.Sid!=IntPtr.Zero ||
            s.Job!=IntPtr.Zero || s.SourceToken!=IntPtr.Zero || s.Process.process!=IntPtr.Zero || s.Process.thread!=IntPtr.Zero ||
            s.Receipt.CreateAttempted || s.Receipt.Created || s.Receipt.Assigned || s.Receipt.Resumed ||
            s.Receipt.Kind!="cmd" || !PilotIdentity(s.Receipt,"pilot_case_id","cmd"))
            throw new InvalidOperationException("original cmd capture must precede all profile/process allocation");
        if(ops==null || ops.OpenRead==null || ops.OpenWrite==null || ops.Validate==null || ops.Read==null || ops.Write==null || ops.Close==null)
            throw new ArgumentException("complete cmd capture operations required");
        DirectReceipt r=s.Receipt;r.Numbers["pilot_cmd_batch_capture_confirmed"]=0;
        string source=Path.GetFullPath(Path.Combine(s.Workspace,"direct.cmd"));
        string destination=Path.GetFullPath(Path.Combine(evidence,"generated-direct.cmd.bin"));
        SafePath(source);SafePath(destination);
        if(String.Equals(source,destination,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("cmd capture paths must be distinct");
        r.Identities["pilot_cmd_batch_stage"]="before_profile_and_process_creation";
        byte[] bytes=ReadPilotCmdCapture(s,source,null,"pilot_cmd_batch_source",ops);
        IntPtr writer=IntPtr.Zero;bool closed=false;string destinationIdentity=null;
        r.Identities["pilot_cmd_batch_destination_path"]=destination;r.Numbers["pilot_cmd_batch_destination_write_confirmed"]=0;
        try {
            ops.OpenWrite(ref writer,destination,"pilot_cmd_batch_destination",r);
            if(!r.Identities.TryGetValue("pilot_cmd_batch_destination",out destinationIdentity) || String.IsNullOrEmpty(destinationIdentity))
                throw new InvalidOperationException("fresh cmd capture identity missing");
            FILE_INFO empty=ops.Validate(writer,destination,destinationIdentity);
            if(PilotCmdBatchLength(empty)!=0 || PilotCmdFileIdentity(empty)!=destinationIdentity)
                throw new InvalidOperationException("cmd capture destination is not the same fresh empty file");
            ops.Write(writer,bytes);
            FILE_INFO written=ops.Validate(writer,destination,destinationIdentity);
            if(PilotCmdBatchLength(written)!=bytes.Length || PilotCmdFileIdentity(written)!=destinationIdentity ||
                written.creationLow!=empty.creationLow || written.creationHigh!=empty.creationHigh)
                throw new InvalidOperationException("cmd capture destination changed during write");
            r.Numbers["pilot_cmd_batch_destination_bytes"]=bytes.Length;
            r.Identities["pilot_cmd_batch_destination_sha256"]=PilotCmdRawHash(bytes);
            r.Numbers["pilot_cmd_batch_destination_write_confirmed"]=1;
        } finally {closed=ClosePilotCmdCaptureHandle(ref writer,"pilot_cmd_batch_destination",s,ops);}
        if(!closed) throw new InvalidOperationException("cmd batch destination close uncertain");
        byte[] readback=ReadPilotCmdCapture(s,destination,destinationIdentity,"pilot_cmd_batch_readback",ops);
        if(!PilotCmdRawEqual(bytes,readback) || r.Identities["pilot_cmd_batch_source_sha256"]!=r.Identities["pilot_cmd_batch_readback_sha256"])
            throw new InvalidOperationException("cmd batch raw readback mismatch");
        r.Numbers["pilot_cmd_batch_capture_confirmed"]=1;
    }
    static void CapturePilotOriginalCmdBatch(QualificationSubject s,string evidence) {
        CapturePilotCmdBatchUsing(s,evidence,PilotCmdNativeCaptureOperations());
    }
    static void ClassifyPilotCmdSentinel(PilotCaseReceipt row) {
        if(row==null || row.Launcher==null) throw new ArgumentNullException("cmd sentinel facts");
        row.CmdExit23Observed=false;row.PositivePassed=false;row.ScriptEntryObserved=false;row.OutputOk=false;row.MutationOk=false;
        row.OfflineReferenceRouteValid=false;row.NativeFiveAssertionsPassed=false;row.NetworkDenialProven=false;
        if(row.Fatal) return;
        DirectReceipt r=row.Launcher;row.ExitHex=r.Exit.ToString("X8");
        row.CanaryClassification="sentinel_did_not_attempt_runtime_canary";
        row.CmdExit23Observed=row.Case=="cmd-exit23" && r.Kind=="cmd" && PilotIdentity(r,"pilot_case_id","cmd-exit23") &&
            PilotCmdSha256(r.ExecutableSha256) && PilotIdentity(r,"pilot_original_cmd_sha256",r.ExecutableSha256) &&
            PilotNumber(r,"pilot_cmd_same_binary_verified",1) && PilotNumber(r,"pilot_exit_query_success",1) &&
            row.AuthorityObserved && row.PreResumeReady && row.OutsideUnchanged && row.OutsideWriteAbsent &&
            !row.OutsideReadObserved && !row.OutsideWriteObserved && r.CreateAttempted && r.Created && r.CreateError==0 &&
            r.Assigned && r.Resumed && r.Wait==WAIT_OBJECT_0 && r.Exit==23;
        row.Status=r.Wait==WAIT_TIMEOUT?"deadline_exceeded":row.CmdExit23Observed?"cmd_exit23_observed":"cmd_exit23_not_observed";
    }
    static bool PilotOriginalSixPassed(IList<PilotCaseReceipt> rows) {
        if(rows==null || rows.Count<6) return false;
        string[] kinds=new string[]{"ordinary","reference","node","cmd","powershell","pwsh"};
        for(int i=0;i<kinds.Length;i++) {
            PilotCaseReceipt row=rows[i];
            if(row==null || row.Case!=kinds[i] || row.Launcher==null || row.Launcher.Kind!=kinds[i] ||
                !PilotMayAdvance(row) || !row.ScopedLifecycleCleanupConfirmed) return false;
            if(i==0 && (!row.OrdinarySignatureMatched || !row.OrdinaryRejected)) return false;
            if(i==1 && !row.OfflineReferenceRouteValid) return false;
            if(i>=2 && !row.PositivePassed) return false;
        }
        // Additive identity/result/count validation belongs to the separate full-run gate.
        return true;
    }
}
