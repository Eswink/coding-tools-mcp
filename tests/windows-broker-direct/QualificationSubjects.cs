// Two independently owned suspended references. No assignment or resume path.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static partial class BrokerDirectLauncher {
    sealed class QualificationSubject {
        public DirectReceipt Receipt=new DirectReceipt();
        public string Parent,Root,Code,Workspace,Outside,Profile;
        public IntPtr Sid=IntPtr.Zero,Job=IntPtr.Zero,SourceToken=IntPtr.Zero;
        public PROCESS_INFORMATION Process=new PROCESS_INFORMATION();
        public bool ProfileCreated,OwnershipCertain=true,ProcessStopped,JobDrained;
    }
    static QualificationSubject NewQualificationSubject(string parent,string kind) {
        var s=new QualificationSubject();s.Receipt.Kind=kind;
        s.Parent=Path.Combine(parent,kind);s.Root=Path.Combine(s.Parent,"owned-"+Guid.NewGuid().ToString("N"));
        s.Code=Path.Combine(s.Root,"code");s.Workspace=Path.Combine(s.Root,"workspace");s.Outside=Path.Combine(s.Parent,"outside");
        s.Profile="ctm.fixture.qual."+Guid.NewGuid().ToString("N");
        return s;
    }
    static bool QualificationSetupCleanup(QualificationSubject s,Action operation,string label) {
        try {operation();s.Receipt.Numbers[label+"_completed"]=1;return true;}
        catch(Exception failure) {
            s.OwnershipCertain=false;
            s.Receipt.Numbers[label+"_completed"]=0;
            s.Receipt.Identities[label+"_exception"]=failure.GetType().Name;return false;
        }
    }
    static bool QualificationSourceObservation(QualificationSubject s,Func<bool> observation,string label) {
        bool success=RequiredTokenObservation(observation,label,s.Receipt);
        if(s.Receipt.Identities.ContainsKey(label+"_observation_failure")) {
            // Old readers do not separately attest allocation frees on exceptional exits.
            s.OwnershipCertain=false;s.Receipt.Numbers["source_allocation_cleanup_uncertain"]=1;
            throw new InvalidOperationException("source inspection exception leaves allocation cleanup unconfirmed: "+label);
        }
        return success;
    }
    static void PrepareQualificationSubject(QualificationSubject s,string fixture,bool lpac,int port) {
        DirectReceipt r=s.Receipt;
        IntPtr list=IntPtr.Zero,caps=IntPtr.Zero,policy=IntPtr.Zero,handles=IntPtr.Zero,environment=IntPtr.Zero;
        IntPtr writer=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,error=IntPtr.Zero;
        bool initialized=false,closed=true;
        try {
            if(Directory.Exists(s.Parent) || File.Exists(s.Parent)) throw new InvalidOperationException("qualification subject parent must be new");
            foreach(string path in new string[]{s.Parent,s.Root,s.Code,s.Workspace,s.Outside}) {SafePath(path);Directory.CreateDirectory(path);}
            File.WriteAllText(Path.Combine(s.Outside,"canary.txt"),"synthetic-outside-canary");
            if((File.GetAttributes(fixture)&FileAttributes.ReparsePoint)!=0) throw new InvalidOperationException("native fixture reparse rejected");
            string exe=Path.Combine(s.Code,"fixture.exe");File.Copy(fixture,exe,false);
            string sourceHash=HashFile(fixture),privateHash=HashFile(exe);
            if(sourceHash!=privateHash) throw new InvalidOperationException("native fixture copy hash mismatch");
            r.Executable=exe;r.ExecutableSha256=privateHash;r.Identities["fixture_source_sha256"]=sourceHash;
            IntPtr candidateSid=IntPtr.Zero;
            int hr=CreateAppContainerProfile(s.Profile,s.Profile,"Temporary paired token qualification",IntPtr.Zero,0,out candidateSid);
            r.Numbers["profile_create_hresult"]=hr;
            if(hr!=0) {
                if(candidateSid!=IntPtr.Zero) {s.OwnershipCertain=false;r.Numbers["profile_unconfirmed_output"]=1;}
                // Failed output is not proof of owned memory; do not FreeSid it.
                candidateSid=IntPtr.Zero;Marshal.ThrowExceptionForHR(hr);
                throw new InvalidOperationException("profile creation did not report S_OK");
            }
            s.ProfileCreated=true;
            if(candidateSid==IntPtr.Zero || candidateSid==new IntPtr(-1)) {s.OwnershipCertain=false;throw new InvalidOperationException("successful profile returned invalid SID output");}
            s.Sid=candidateSid;
            var package=new SecurityIdentifier(s.Sid);r.ProfileSid=package.Value;
            OwnedAcl(s.Outside,new SecurityIdentifier("S-1-15-2-1"),FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Root,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Code,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(s.Workspace,package,FileSystemRights.Modify);
            string inputPath=Path.Combine(s.Workspace,"stdin-empty.txt");
            OpenPrivate(ref writer,inputPath,0x40000000,1,false,"stdin_writer",r);
            closed=CloseOwned(ref writer,"stdin_writer",r) && closed;
            if(!closed) throw new InvalidOperationException("paired input writer close uncertain");
            OpenPrivate(ref input,inputPath,0x80000000,3,true,"stdin",r);
            OpenPrivate(ref output,Path.Combine(s.Workspace,"stdout.txt"),0x40000000,1,true,"stdout",r);
            OpenPrivate(ref error,Path.Combine(s.Workspace,"stderr.txt"),0x40000000,1,true,"stderr",r);
            if(input==output || input==error || output==error || r.Identities["stdin"]==r.Identities["stdout"] ||
                r.Identities["stdin"]==r.Identities["stderr"] || r.Identities["stdout"]==r.Identities["stderr"] ||
                r.Identities["stdin_writer"]!=r.Identities["stdin"]) throw new InvalidOperationException("paired stdio identity mismatch");
            r.StdioValidated=true;
            int attributeCount=lpac?3:2;IntPtr bytes=IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero,attributeCount,0,ref bytes);
            if(bytes==IntPtr.Zero) throw new InvalidOperationException("paired attribute size unavailable");
            list=Marshal.AllocHGlobal(bytes);
            Check(InitializeProcThreadAttributeList(list,attributeCount,0,ref bytes),"paired attribute initialization");initialized=true;
            SECURITY_CAPABILITIES capabilities=new SECURITY_CAPABILITIES();capabilities.Sid=s.Sid;
            caps=Marshal.AllocHGlobal(Marshal.SizeOf(capabilities));Marshal.StructureToPtr(capabilities,caps,false);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20009),caps,new IntPtr(Marshal.SizeOf(capabilities)),IntPtr.Zero,IntPtr.Zero),"paired AppContainer attribute");
            r.Numbers["configured_lpac_request"]=lpac?1:0;
            if(lpac) {
                policy=Marshal.AllocHGlobal(4);Marshal.WriteInt32(policy,(int)TOKEN_ALL_PACKAGES_OPT_OUT);
                Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x2000f),policy,new IntPtr(4),IntPtr.Zero,IntPtr.Zero),"paired LPAC attribute");
            }
            handles=Marshal.AllocHGlobal(3*IntPtr.Size);
            Marshal.WriteIntPtr(handles,0,input);Marshal.WriteIntPtr(handles,IntPtr.Size,output);Marshal.WriteIntPtr(handles,2*IntPtr.Size,error);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(3*IntPtr.Size),IntPtr.Zero,IntPtr.Zero),"paired exact private stdio list");
            r.HandleListCount=3;
            IntPtr candidateJob=CreateJobObject(IntPtr.Zero,null);Check(candidateJob!=IntPtr.Zero,"paired job creation");
            if(candidateJob==new IntPtr(-1)) {s.OwnershipCertain=false;throw new InvalidOperationException("job returned invalid handle");}
            s.Job=candidateJob;
            var limits=new EXTENDED_LIMIT();limits.Basic.flags=KILL_ON_JOB_CLOSE;
            Check(SetInformationJobObject(s.Job,9,ref limits,(uint)Marshal.SizeOf(limits)),"paired job limits");
            string env=EnvironmentBlock(s.Workspace,s.Code);environment=Marshal.StringToHGlobalUni(env);
            File.WriteAllText(Path.Combine(s.Parent,"environment.txt"),env.Replace('\0','\n'));
            var startup=new STARTUPINFOEX();startup.Startup.cb=(uint)Marshal.SizeOf(startup);startup.Attributes=list;
            startup.Startup.flags=0x100;startup.Startup.input=input;startup.Startup.output=output;startup.Startup.error=error;
            r.CommandLine=Quote(exe)+" sandbox "+Quote(s.Workspace)+" "+Quote(s.Outside)+" 127.0.0.1:"+port;
            r.Stage="create_suspended";r.CreateAttempted=true;
            PROCESS_INFORMATION candidateProcess=new PROCESS_INFORMATION();
            bool created=CreateProcess(exe,new StringBuilder(r.CommandLine),IntPtr.Zero,IntPtr.Zero,true,
                CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u,environment,s.Workspace,ref startup,out candidateProcess);
            r.CreateError=created?0:Marshal.GetLastWin32Error();r.Created=created;
            if(!created) {
                if(candidateProcess.process!=IntPtr.Zero || candidateProcess.thread!=IntPtr.Zero || candidateProcess.pid!=0 || candidateProcess.tid!=0) {
                    s.OwnershipCertain=false;r.Numbers["create_unconfirmed_outputs"]=1;
                }
                // Do not close, terminate, or reopen by PID from failed API outputs.
                candidateProcess=new PROCESS_INFORMATION();
                throw new System.ComponentModel.Win32Exception(r.CreateError,"paired suspended CreateProcessW");
            }
            s.Process=candidateProcess;
            bool processValid=s.Process.process!=IntPtr.Zero && s.Process.process!=new IntPtr(-1);
            bool threadValid=s.Process.thread!=IntPtr.Zero && s.Process.thread!=new IntPtr(-1);
            if(!processValid || !threadValid || s.Process.pid==0 || s.Process.tid==0) {
                s.OwnershipCertain=false;
                if(!processValid) s.Process.process=IntPtr.Zero;
                if(!threadValid) s.Process.thread=IntPtr.Zero;
                throw new InvalidOperationException("successful creation returned incomplete process ownership");
            }
        } finally {
            closed=QualificationSetupCleanup(s,delegate {closed=CloseOwned(ref writer,"stdin_writer_cleanup",r) && closed;},"setup_writer_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=CloseOwned(ref input,"stdin",r) && closed;},"setup_stdin_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=CloseOwned(ref output,"stdout",r) && closed;},"setup_stdout_cleanup") && closed;
            closed=QualificationSetupCleanup(s,delegate {closed=CloseOwned(ref error,"stderr",r) && closed;},"setup_stderr_cleanup") && closed;
            r.HostStdioClosed=closed;s.OwnershipCertain=closed && s.OwnershipCertain;
            if(initialized) QualificationSetupCleanup(s,delegate {DeleteProcThreadAttributeList(list);},"setup_attribute_cleanup");
            IntPtr[] memory=new IntPtr[]{list,caps,policy,handles,environment};
            for(int i=0;i<memory.Length;i++) if(memory[i]!=IntPtr.Zero)
                QualificationSetupCleanup(s,delegate {Marshal.FreeHGlobal(memory[i]);},"setup_heap_"+i);
        }
        if(!s.OwnershipCertain) throw new InvalidOperationException("paired setup cleanup uncertain");
    }
    static bool ObserveQualificationSource(QualificationSubject s) {
        DirectReceipt r=s.Receipt;r.Stage="inspect_suspended_source";
        r.Numbers["source_token_requested_access"]=0x000A;
        IntPtr candidateToken=IntPtr.Zero;
        bool opened=OpenProcessToken(s.Process.process,0x000A,out candidateToken);
        r.Numbers["source_token_open_error"]=opened?0:Marshal.GetLastWin32Error();
        if(!opened) {
            if(candidateToken!=IntPtr.Zero) {
                s.OwnershipCertain=false;r.Numbers["source_token_unconfirmed_output"]=1;
                candidateToken=IntPtr.Zero;
                throw new InvalidOperationException("failed source token query returned unconfirmed ownership");
            }
            return false;
        }
        if(candidateToken==IntPtr.Zero || candidateToken==new IntPtr(-1)) {s.OwnershipCertain=false;throw new InvalidOperationException("successful token query returned invalid handle");}
        s.SourceToken=candidateToken;
        try {
            int? app=null,lpac=null,capabilities=null,type=null;string sid=null,integrity=null;
            bool restricted=true;
            restricted=QualificationSourceObservation(s,delegate {type=TokenCount(s.SourceToken,8,"source_type",r);return r.Numbers["source_type_returned_bytes"]==4;},"source_type") && restricted;
            restricted=QualificationSourceObservation(s,delegate {app=TokenCount(s.SourceToken,29,"appcontainer",r);return r.Numbers["appcontainer_returned_bytes"]==4;},"appcontainer") && restricted;
            ObserveLpacSizing(s.SourceToken,r);
            bool lpacQuery=QualificationSourceObservation(s,delegate {lpac=ObserveFixedLpacDword(s.SourceToken,r);return lpac.HasValue;},"lpac");
            restricted=QualificationSourceObservation(s,delegate {capabilities=TokenCount(s.SourceToken,30,"capabilities",r);return true;},"capabilities") && restricted;
            restricted=QualificationSourceObservation(s,delegate {sid=TokenSid(s.SourceToken,31,"appcontainer_sid",r);return true;},"appcontainer_sid") && restricted;
            restricted=QualificationSourceObservation(s,delegate {integrity=TokenSid(s.SourceToken,25,"integrity_sid",r);return true;},"integrity_sid") && restricted;
            bool sourceValid=restricted && type==1 && app==1 && capabilities==0 && sid==r.ProfileSid && integrity=="S-1-16-4096";
            r.Numbers["source_restricted_properties_verified"]=sourceValid?1:0;
            r.TokenVerified=sourceValid && lpacQuery && lpac==1;
            r.Numbers["native_queries_observation_only"]=1;
            ObserveNativeDword(s.SourceToken,29,"native_appcontainer",r);
            ObserveNativeDword(s.SourceToken,46,"native_lpac",r);
            return sourceValid;
        } catch {
            // Includes exceptions escaping old fixed/native readers' finally blocks.
            s.OwnershipCertain=false;r.Numbers["source_inspection_cleanup_uncertain"]=1;throw;
        }
    }
}
