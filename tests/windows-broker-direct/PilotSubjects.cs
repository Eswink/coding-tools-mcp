// CI-only suspended preparation adapter. No assignment, resume, token policy, or removal.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static partial class BrokerDirectLauncher {
    // Reuse the same exclusive CreateDirectoryW import as the owned-scope helper.
    static bool PilotNewProcessHandle(IntPtr value,IntPtr job,IntPtr input,IntPtr output,IntPtr error) {
        return value!=IntPtr.Zero && value!=new IntPtr(-1) && value!=job && value!=input && value!=output && value!=error;
    }
    static void ValidatePilotPreparation(QualificationSubject s,string fixture,string payload,string kind,int port) {
        if(s==null || s.Receipt==null || !s.OwnershipCertain || s.ProfileCreated || s.Sid!=IntPtr.Zero ||
            s.Job!=IntPtr.Zero || s.SourceToken!=IntPtr.Zero || s.Process.process!=IntPtr.Zero || s.Process.thread!=IntPtr.Zero ||
            s.Receipt.CreateAttempted || s.Receipt.Assigned || s.Receipt.Resumed)
            throw new InvalidOperationException("fresh coordinator-owned pilot subject required");
        if(kind!="ordinary" && kind!="reference" && kind!="node" && kind!="cmd" && kind!="powershell" && kind!="pwsh" && kind!="cmd-exit23" && kind!="cmd-batch-exit23" && !PilotCmdObservationKind(kind))
            throw new ArgumentException("fixed pilot kind required");
        if(port<1 || port>65535 || String.IsNullOrEmpty(s.Profile)) throw new ArgumentException("fixed pilot setup invalid");
        foreach(string path in new string[]{s.Parent,s.Root,s.Code,s.Workspace,s.Outside,fixture,payload}) SafePath(path);
        string root=Path.GetFullPath(s.Root),parent=Path.GetFullPath(s.Parent);
        string name=Path.GetFileName(root);
        if(!String.Equals(Path.GetDirectoryName(root),parent,StringComparison.OrdinalIgnoreCase) ||
            name.Length!=38 || !name.StartsWith("owned-",StringComparison.Ordinal)) throw new InvalidOperationException("pilot root is not an immediate generated child");
        for(int i=6;i<name.Length;i++) if("0123456789abcdef".IndexOf(name[i])<0) throw new InvalidOperationException("pilot root nonce invalid");
        string[] actual=new string[]{s.Code,s.Workspace,s.Outside},leaf=new string[]{"code","workspace","outside"};
        for(int i=0;i<actual.Length;i++) if(!String.Equals(Path.GetFullPath(actual[i]),Path.Combine(root,leaf[i]),StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("pilot child layout changed");
        foreach(string path in new string[]{parent,root}) {
            FileAttributes attributes=File.GetAttributes(path);
            if((attributes&FileAttributes.Directory)==0 || (attributes&FileAttributes.ReparsePoint)!=0)
                throw new InvalidOperationException("coordinator-owned pilot directory unavailable");
        }
    }
    static void CopyPilotFile(string source,string destination,string relative,StringBuilder provenance) {
        if((File.GetAttributes(source)&(FileAttributes.ReparsePoint|FileAttributes.Directory))!=0)
            throw new InvalidOperationException("pilot copy source is not an ordinary file");
        File.Copy(source,destination,false);
        string sourceHash=HashFile(source),destinationHash=HashFile(destination);
        if(sourceHash!=destinationHash) throw new InvalidOperationException("pilot copied bytes mismatch");
        provenance.AppendLine(sourceHash+" "+destinationHash+" "+relative);
    }
    static void RecordPilotCopyHashes(string source,string destination,string relative,StringBuilder provenance) {
        if((File.GetAttributes(source)&FileAttributes.ReparsePoint)!=0 || (File.GetAttributes(destination)&FileAttributes.ReparsePoint)!=0)
            throw new InvalidOperationException("pilot copied directory reparse rejected");
        foreach(string file in Directory.GetFiles(source)) {
            if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0) throw new InvalidOperationException("pilot source file reparse rejected");
            string target=Path.Combine(destination,Path.GetFileName(file));
            if((File.GetAttributes(target)&FileAttributes.ReparsePoint)!=0) throw new InvalidOperationException("pilot target file reparse rejected");
            string sourceHash=HashFile(file),destinationHash=HashFile(target);
            if(sourceHash!=destinationHash) throw new InvalidOperationException("pilot runtime copied bytes mismatch");
            provenance.AppendLine(sourceHash+" "+destinationHash+" "+Path.Combine(relative,Path.GetFileName(file)));
        }
        foreach(string dir in Directory.GetDirectories(source))
            RecordPilotCopyHashes(dir,Path.Combine(destination,Path.GetFileName(dir)),Path.Combine(relative,Path.GetFileName(dir)),provenance);
    }
    static void PreparePilotSubject(QualificationSubject s,string fixture,string payload,string kind,int port,string evidence,Action profileCheckpoint) {
        if(profileCheckpoint==null) throw new ArgumentNullException("profileCheckpoint");
        ValidatePilotPreparation(s,fixture,payload,kind,port);
        DirectReceipt r=s.Receipt;bool lpac=kind!="ordinary";r.Kind=(kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind))?"cmd":kind;
        IntPtr list=IntPtr.Zero,caps=IntPtr.Zero,policy=IntPtr.Zero,handles=IntPtr.Zero,environment=IntPtr.Zero;
        IntPtr writer=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,error=IntPtr.Zero;
        bool initialized=false,closed=true;
        try {
            // The coordinator has already created and identity-pinned Parent and Root.
            // These three children are exclusively created; preexisting entries are rejected.
            foreach(string path in new string[]{s.Code,s.Workspace,s.Outside})
                Check(PilotCreateDirectory(path,IntPtr.Zero),"fresh pilot child directory");
            File.WriteAllText(Path.Combine(s.Outside,"canary.txt"),"synthetic-outside-canary");
            var provenance=new StringBuilder();
            string privateFixture=Path.Combine(s.Code,"fixture.exe");
            CopyPilotFile(fixture,privateFixture,"fixture.exe",provenance);
            r.Identities["fixture_source_sha256"]=HashFile(fixture);
            if(kind=="cmd" || kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind)) CopyPilotFile(Path.Combine(payload,"cmd.exe"),Path.Combine(s.Code,"cmd.exe"),"cmd.exe",provenance);
            else if(kind!="ordinary" && kind!="reference") {
                string runtime=Path.Combine(s.Code,"runtime"),source=Path.Combine(payload,kind);
                Check(PilotCreateDirectory(runtime,IntPtr.Zero),"fresh pilot runtime directory");
                CopyOwnedBundle(source,runtime);
                RecordPilotCopyHashes(source,runtime,"runtime",provenance);
            }
            string exe;
            if(kind=="cmd-exit23") {
                exe=Path.Combine(s.Code,"cmd.exe");r.CommandLine=FixedPilotCmdSentinelCommand(exe);
            } else if(kind=="cmd-batch-exit23") {
                exe=Path.Combine(s.Code,"cmd.exe");r.CommandLine=FixedPilotCmdBatchCommand(exe);
                File.WriteAllBytes(Path.Combine(s.Workspace,"direct.cmd"),PilotCmdMinimalBatchBytes());
            } else if(PilotCmdObservationKind(kind)) {
                exe=Path.Combine(s.Code,"cmd.exe");
                r.CommandLine=FixedPilotCmdObservationCommand(kind,exe);
                PilotOwnedPath(s.Workspace);
                if(!String.Equals(s.Workspace,Path.GetFullPath(s.Workspace),StringComparison.Ordinal))
                    throw new InvalidOperationException("exact pilot observation cwd required");
                r.Identities["pilot_cmd_observation_protocol"]=PilotCmdObservationProtocol(kind);
                r.Identities["pilot_cmd_observation_case"]=kind;
                r.Identities["pilot_cmd_observation_command"]=r.CommandLine;
                r.Identities["pilot_cmd_observation_cwd"]=s.Workspace;
                if(kind=="cmd-read-direct" || kind=="cmd-relative-batch-exit23") File.WriteAllBytes(Path.Combine(s.Workspace,"direct.cmd"),PilotCmdMinimalBatchBytes());
            } else r.CommandLine=FixedCommand(kind=="ordinary"?"reference":kind,s.Code,s.Workspace,s.Outside,port,out exe);
            r.Executable=exe;r.ExecutableSha256=HashFile(exe);
            if(kind=="cmd") CapturePilotOriginalCmdBatch(s,evidence);
            if(kind=="cmd-batch-exit23") CapturePilotMinimalCmdBatch(s,evidence);
            if(kind=="cmd-read-direct") CapturePilotCmdReadBatch(s,evidence);
            if(kind=="cmd-relative-batch-exit23") CapturePilotCmdRelativeBatch(s,evidence);
            File.WriteAllText(Path.Combine(s.Root,"copy-source-destination-sha256.txt"),provenance.ToString());
            var privateHashes=new StringBuilder();
            foreach(string file in Directory.GetFiles(s.Code,"*",SearchOption.AllDirectories))
                privateHashes.AppendLine(HashFile(file)+" "+file.Substring(s.Code.Length+1));
            File.WriteAllText(Path.Combine(s.Root,"private-code-sha256.txt"),privateHashes.ToString());
            r.Numbers["pilot_copied_bytes_verified"]=1;
            IntPtr candidateSid=IntPtr.Zero;int hr;
            try {hr=CreateAppContainerProfile(s.Profile,s.Profile,"Temporary broker-direct pilot",IntPtr.Zero,0,out candidateSid);}
            catch {s.OwnershipCertain=false;candidateSid=IntPtr.Zero;throw;}
            if(hr==0) {
                s.ProfileCreated=true;
                if(candidateSid==IntPtr.Zero || candidateSid==new IntPtr(-1)) s.OwnershipCertain=false;
                else s.Sid=candidateSid;
            } else if(candidateSid!=IntPtr.Zero) s.OwnershipCertain=false;
            r.Numbers["profile_create_hresult"]=hr;
            if(hr!=0) {
                if(candidateSid!=IntPtr.Zero) r.Numbers["profile_unconfirmed_output"]=1;
                // A failed output is unowned; never free or adopt that value.
                candidateSid=IntPtr.Zero;Marshal.ThrowExceptionForHR(hr);
                throw new InvalidOperationException("profile creation did not report S_OK");
            }
            if(!s.OwnershipCertain || s.Sid==IntPtr.Zero || !IsValidSid(s.Sid))
                throw new InvalidOperationException("successful profile returned invalid SID output");
            var package=new SecurityIdentifier(s.Sid);r.ProfileSid=package.Value;
            r.Numbers["pilot_profile_owned"]=1;r.Identities["pilot_profile_name"]=s.Profile;
            r.Numbers["pilot_profile_checkpoint_completed"]=0;
            // The active-journal owner durably records the profile before further setup.
            profileCheckpoint();
            r.Numbers["pilot_profile_checkpoint_completed"]=1;
            OwnedAcl(s.Outside,new SecurityIdentifier("S-1-15-2-1"),FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Root,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Code,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Workspace,package,FileSystemRights.Modify);
            string inputPath=Path.Combine(s.Workspace,"stdin-empty.txt");
            OpenPrivate(ref writer,inputPath,0x40000000,1,false,"stdin_writer",r);
            closed=PilotCloseHandle(ref writer,"stdin_writer",r) && closed;
            if(!closed) throw new InvalidOperationException("pilot input writer close uncertain");
            OpenPrivate(ref input,inputPath,0x80000000,3,true,"stdin",r);
            OpenPrivate(ref output,Path.Combine(s.Workspace,"stdout.txt"),0x40000000,1,true,"stdout",r);
            OpenPrivate(ref error,Path.Combine(s.Workspace,"stderr.txt"),0x40000000,1,true,"stderr",r);
            if(input==output || input==error || output==error || r.Identities["stdin"]==r.Identities["stdout"] ||
                r.Identities["stdin"]==r.Identities["stderr"] || r.Identities["stdout"]==r.Identities["stderr"] ||
                r.Identities["stdin_writer"]!=r.Identities["stdin"]) throw new InvalidOperationException("pilot stdio identity mismatch");
            r.StdioValidated=true;
            int attributeCount=lpac?3:2;IntPtr bytes=IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero,attributeCount,0,ref bytes);
            if(bytes==IntPtr.Zero) throw new InvalidOperationException("pilot attribute size unavailable");
            list=Marshal.AllocHGlobal(bytes);
            Check(InitializeProcThreadAttributeList(list,attributeCount,0,ref bytes),"pilot attribute initialization");initialized=true;
            SECURITY_CAPABILITIES capabilities=new SECURITY_CAPABILITIES();capabilities.Sid=s.Sid;
            caps=Marshal.AllocHGlobal(Marshal.SizeOf(capabilities));Marshal.StructureToPtr(capabilities,caps,false);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20009),caps,new IntPtr(Marshal.SizeOf(capabilities)),IntPtr.Zero,IntPtr.Zero),"pilot AppContainer attribute");
            r.Numbers["configured_lpac_request"]=lpac?1:0;
            if(lpac) {
                policy=Marshal.AllocHGlobal(4);Marshal.WriteInt32(policy,(int)TOKEN_ALL_PACKAGES_OPT_OUT);
                Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x2000f),policy,new IntPtr(4),IntPtr.Zero,IntPtr.Zero),"pilot LPAC attribute");
            }
            handles=Marshal.AllocHGlobal(3*IntPtr.Size);
            Marshal.WriteIntPtr(handles,0,input);Marshal.WriteIntPtr(handles,IntPtr.Size,output);Marshal.WriteIntPtr(handles,2*IntPtr.Size,error);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(3*IntPtr.Size),IntPtr.Zero,IntPtr.Zero),"pilot exact private stdio list");
            r.HandleListCount=3;
            IntPtr candidateJob=CreateJobObject(IntPtr.Zero,null);Check(candidateJob!=IntPtr.Zero,"pilot job creation");
            if(candidateJob==new IntPtr(-1)) {s.OwnershipCertain=false;throw new InvalidOperationException("job returned invalid handle");}
            s.Job=candidateJob;
            var limits=new EXTENDED_LIMIT();limits.Basic.flags=KILL_ON_JOB_CLOSE;
            Check(SetInformationJobObject(s.Job,9,ref limits,(uint)Marshal.SizeOf(limits)),"pilot job limits");
            string env=EnvironmentBlock(s.Workspace,s.Code);environment=Marshal.StringToHGlobalUni(env);
            File.WriteAllText(Path.Combine(s.Root,"environment.txt"),env.Replace('\0','\n'));
            var startup=new STARTUPINFOEX();startup.Startup.cb=(uint)Marshal.SizeOf(startup);startup.Attributes=list;
            startup.Startup.flags=0x100;startup.Startup.input=input;startup.Startup.output=output;startup.Startup.error=error;
            r.Stage="create_suspended";r.CreateAttempted=true;
            PROCESS_INFORMATION candidateProcess=new PROCESS_INFORMATION();
            bool created;
            try {
                created=CreateProcess(exe,new StringBuilder(r.CommandLine),IntPtr.Zero,IntPtr.Zero,true,
                    CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u,environment,s.Workspace,ref startup,out candidateProcess);
            } catch {s.OwnershipCertain=false;candidateProcess=new PROCESS_INFORMATION();throw;}
            int createError=created?0:Marshal.GetLastWin32Error();
            r.CreateError=createError;r.Created=created;
            if(!created) {
                if(candidateProcess.process!=IntPtr.Zero || candidateProcess.thread!=IntPtr.Zero || candidateProcess.pid!=0 || candidateProcess.tid!=0) {
                    s.OwnershipCertain=false;r.Numbers["create_unconfirmed_outputs"]=1;
                }
                // Failed outputs never establish handle or PID ownership.
                candidateProcess=new PROCESS_INFORMATION();
                throw new System.ComponentModel.Win32Exception(createError,"pilot suspended CreateProcessW");
            }
            bool processValid=PilotNewProcessHandle(candidateProcess.process,s.Job,input,output,error);
            bool threadValid=PilotNewProcessHandle(candidateProcess.thread,s.Job,input,output,error);
            if(candidateProcess.process==candidateProcess.thread) {processValid=false;threadValid=false;}
            if(!processValid || !threadValid || candidateProcess.pid==0 || candidateProcess.tid==0) s.OwnershipCertain=false;
            if(!processValid) candidateProcess.process=IntPtr.Zero;
            if(!threadValid) candidateProcess.thread=IntPtr.Zero;
            // Only independently owned successful outputs reach the shared stop/drain helper.
            s.Process=candidateProcess;
            r.Numbers["pilot_process_outputs_owned"]=s.OwnershipCertain?1:0;
            if(!s.OwnershipCertain) throw new InvalidOperationException("successful creation returned incomplete process ownership");
            // Correlation only: ownership remains the exact successful API handles.
            r.Numbers["pilot_created_pid"]=s.Process.pid;r.Numbers["pilot_created_tid"]=s.Process.tid;
        } finally {
            closed=QualificationSetupCleanup(s,delegate {closed=PilotCloseHandle(ref writer,"stdin_writer_cleanup",r) && closed;},"setup_writer_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=PilotCloseHandle(ref input,"stdin",r) && closed;},"setup_stdin_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=PilotCloseHandle(ref output,"stdout",r) && closed;},"setup_stdout_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=PilotCloseHandle(ref error,"stderr",r) && closed;},"setup_stderr_cleanup") && closed;
            r.HostStdioClosed=closed;s.OwnershipCertain=closed && s.OwnershipCertain;
            if(initialized) QualificationSetupCleanup(s,delegate {DeleteProcThreadAttributeList(list);},"setup_attribute_cleanup");
            IntPtr[] memory=new IntPtr[]{list,caps,policy,handles,environment};
            for(int i=0;i<memory.Length;i++) if(memory[i]!=IntPtr.Zero)
                QualificationSetupCleanup(s,delegate {Marshal.FreeHGlobal(memory[i]);},"setup_heap_"+i);
        }
        if(!s.OwnershipCertain) throw new InvalidOperationException("pilot setup cleanup uncertain");
    }
}
