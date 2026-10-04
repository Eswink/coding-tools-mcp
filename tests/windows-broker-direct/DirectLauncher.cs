// CI-only direct-broker comparison. All original nested observations remain required.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static partial class BrokerDirectLauncher {
    public static DirectReceipt RunDirect(string fixture,string parent,string outside,int port,string kind,string bundle) {
        if(kind!="reference" && kind!="node" && kind!="cmd" && kind!="powershell" && kind!="pwsh") throw new ArgumentException("fixed case required");
        var r=new DirectReceipt();r.Kind=kind;
        string root=Path.Combine(parent,"direct-"+Guid.NewGuid().ToString("N"));
        string code=Path.Combine(root,"code"),workspace=Path.Combine(root,"workspace");
        string name="ctm.fixture."+Guid.NewGuid().ToString("N");
        IntPtr sid=IntPtr.Zero,list=IntPtr.Zero,caps=IntPtr.Zero,policy=IntPtr.Zero,env=IntPtr.Zero,job=IntPtr.Zero,handles=IntPtr.Zero;
        IntPtr input=IntPtr.Zero,output=IntPtr.Zero,error=IntPtr.Zero,writer=IntPtr.Zero;
        PROCESS_INFORMATION pi=new PROCESS_INFORMATION();
        bool initialized=false,profile=false,closeCertain=true;
        string recovery=Path.Combine(parent,"cleanup-uncertain.txt");
        File.WriteAllText(recovery,"Pending owned recovery scope: "+root+"; profile="+name);
        try {
            Directory.CreateDirectory(root);Directory.CreateDirectory(code);Directory.CreateDirectory(workspace);
            File.Copy(fixture,Path.Combine(code,"fixture.exe"),false);CopyOwnedBundle(bundle,code);
            string exe;r.CommandLine=FixedCommand(kind,code,workspace,outside,port,out exe);r.Executable=exe;r.ExecutableSha256=HashFile(exe);
            // Compare every copied source/destination byte identity before applying private fixture ACLs.
            var provenance=new StringBuilder();
            foreach(string source in Directory.GetFiles(bundle,"*",SearchOption.AllDirectories)) {
                string relative=source.Substring(bundle.Length+1),destination=Path.Combine(code,relative);
                string sourceHash=HashFile(source),destinationHash=HashFile(destination);
                provenance.AppendLine(sourceHash+" "+destinationHash+" "+relative);
                if(sourceHash!=destinationHash) throw new InvalidOperationException("private payload byte mismatch");
            }
            string fixtureHash=HashFile(fixture),privateFixtureHash=HashFile(Path.Combine(code,"fixture.exe"));
            if(fixtureHash!=privateFixtureHash) throw new InvalidOperationException("native fixture byte mismatch");
            provenance.AppendLine(fixtureHash+" "+privateFixtureHash+" fixture.exe");
            File.WriteAllText(Path.Combine(parent,"copy-source-destination-sha256.txt"),provenance.ToString());
            var hashes=new StringBuilder();
            foreach(string path in Directory.GetFiles(code,"*",SearchOption.AllDirectories))
                hashes.AppendLine(HashFile(path)+" "+path.Substring(code.Length+1));
            File.WriteAllText(Path.Combine(parent,"private-code-sha256.txt"),hashes.ToString());
            int hr=CreateAppContainerProfile(name,name,"Temporary direct runtime containment test",IntPtr.Zero,0,out sid);
            if(hr!=0) Marshal.ThrowExceptionForHR(hr);profile=true;
            var package=new SecurityIdentifier(sid);r.ProfileSid=package.Value;
            OwnedAcl(outside,new SecurityIdentifier("S-1-15-2-1"),FileSystemRights.ReadAndExecute);
            OwnedAcl(root,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(code,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(workspace,package,FileSystemRights.Modify);
            string inputPath=Path.Combine(workspace,"stdin-empty.txt");
            OpenPrivate(ref writer,inputPath,0x40000000,1,false,"stdin_writer",r);
            closeCertain=CloseOwned(ref writer,"stdin_writer",r) && closeCertain;
            if(!closeCertain) throw new InvalidOperationException("input writer close uncertain");
            OpenPrivate(ref input,inputPath,0x80000000,3,true,"stdin",r);
            OpenPrivate(ref output,Path.Combine(workspace,"stdout.txt"),0x40000000,1,true,"stdout",r);
            OpenPrivate(ref error,Path.Combine(workspace,"stderr.txt"),0x40000000,1,true,"stderr",r);
            if(input==output || input==error || output==error || r.Identities["stdin"]==r.Identities["stdout"] ||
                r.Identities["stdin"]==r.Identities["stderr"] || r.Identities["stdout"]==r.Identities["stderr"] ||
                r.Identities["stdin_writer"]!=r.Identities["stdin"])
                throw new InvalidOperationException("stdio object identity mismatch");
            r.StdioValidated=true;
            IntPtr bytes=IntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,3,0,ref bytes);
            if(bytes==IntPtr.Zero) throw new InvalidOperationException("attribute size unavailable");
            list=Marshal.AllocHGlobal(bytes);Check(InitializeProcThreadAttributeList(list,3,0,ref bytes),"attribute initialization");initialized=true;
            SECURITY_CAPABILITIES capabilities=new SECURITY_CAPABILITIES();capabilities.Sid=sid;
            caps=Marshal.AllocHGlobal(Marshal.SizeOf(capabilities));Marshal.StructureToPtr(capabilities,caps,false);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20009),caps,new IntPtr(Marshal.SizeOf(capabilities)),IntPtr.Zero,IntPtr.Zero),"AppContainer attribute");
            policy=Marshal.AllocHGlobal(4);Marshal.WriteInt32(policy,(int)TOKEN_ALL_PACKAGES_OPT_OUT);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x2000f),policy,new IntPtr(4),IntPtr.Zero,IntPtr.Zero),"LPAC attribute");
            handles=Marshal.AllocHGlobal(3*IntPtr.Size);
            Marshal.WriteIntPtr(handles,0,input);Marshal.WriteIntPtr(handles,IntPtr.Size,output);Marshal.WriteIntPtr(handles,2*IntPtr.Size,error);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(3*IntPtr.Size),IntPtr.Zero,IntPtr.Zero),"exact private stdio handle list");
            r.HandleListCount=3;
            job=CreateJobObject(IntPtr.Zero,null);Check(job!=IntPtr.Zero,"job creation");
            var limits=new EXTENDED_LIMIT();limits.Basic.flags=KILL_ON_JOB_CLOSE;
            Check(SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(limits)),"job limits");
            string environment=EnvironmentBlock(workspace,code);env=Marshal.StringToHGlobalUni(environment);
            File.WriteAllText(Path.Combine(parent,"environment.txt"),environment.Replace('\0','\n'));
            var startup=new STARTUPINFOEX();startup.Startup.cb=(uint)Marshal.SizeOf(startup);startup.Attributes=list;
            startup.Startup.flags=0x100;startup.Startup.input=input;startup.Startup.output=output;startup.Startup.error=error;
            r.Stage="create_suspended";r.CreateAttempted=true;
            bool created=CreateProcess(exe,new StringBuilder(r.CommandLine),IntPtr.Zero,IntPtr.Zero,true,
                CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u,env,workspace,ref startup,out pi);
            r.CreateError=created?0:Marshal.GetLastWin32Error();r.Created=created;
            // Even failed creation closes each broker stdio copy. No child has run yet.
            closeCertain=CloseOwned(ref input,"stdin",r) && closeCertain;
            closeCertain=CloseOwned(ref output,"stdout",r) && closeCertain;
            closeCertain=CloseOwned(ref error,"stderr",r) && closeCertain;
            r.HostStdioClosed=closeCertain;
            if(!closeCertain) throw new InvalidOperationException("broker stdio close uncertain");
            if(!created) throw new System.ComponentModel.Win32Exception(r.CreateError,"direct CreateProcessW failed");
            r.Stage="verify_suspended_token";r.TokenVerified=VerifyToken(pi.process,r.ProfileSid,r);
            if(!r.TokenVerified) throw new InvalidOperationException("exact suspended target token unverified");
            // Even an unexpected successful Win32 verifier cannot resume this observation-only run.
            if(r.Numbers.ContainsKey("native_queries_observation_only"))
                throw new InvalidOperationException("native token observations collected; reference must remain unresumed");
            r.Stage="assign_job";Check(AssignProcessToJobObject(job,pi.process),"assign before resume");r.Assigned=true;
            r.Stage="resume";
            uint previous=ResumeThread(pi.thread);r.Numbers["resume_previous_count"]=previous;
            if(previous!=1) throw new InvalidOperationException("unexpected suspension state");r.Resumed=true;
            r.Stage="wait";r.Wait=WaitForSingleObject(pi.process,30000);
            if(r.Wait!=WAIT_OBJECT_0) throw new InvalidOperationException(r.Wait==WAIT_TIMEOUT?"direct runtime deadline exceeded":"direct runtime wait failed");
            uint exit;Check(GetExitCodeProcess(pi.process,out exit),"direct runtime exit code");r.Exit=exit;r.Stage="exited";
        } catch(Exception failure) {
            r.Failure=failure.GetType().Name+": "+failure.Message;
            var win32=failure as System.ComponentModel.Win32Exception;r.FailureCode=win32==null?failure.HResult:win32.NativeErrorCode;
        } finally {
            // No uncertain handle is blindly closed twice. Any uncertainty retains the owned recovery scope.
            closeCertain=CloseOwned(ref writer,"stdin_writer_cleanup",r) && closeCertain;
            closeCertain=CloseOwned(ref input,"stdin_cleanup",r) && closeCertain;
            closeCertain=CloseOwned(ref output,"stdout_cleanup",r) && closeCertain;
            closeCertain=CloseOwned(ref error,"stderr_cleanup",r) && closeCertain;
            bool stopped=true;
            if(pi.process!=IntPtr.Zero) {
                if(WaitForSingleObject(pi.process,0)!=WAIT_OBJECT_0) {
                    bool terminated=TerminateProcess(pi.process,91);r.Numbers["terminate_process_error"]=terminated?0:Marshal.GetLastWin32Error();
                }
                stopped=WaitForSingleObject(pi.process,5000)==WAIT_OBJECT_0;
            }
            if(job!=IntPtr.Zero) {
                bool terminated=TerminateJobObject(job,91);r.Numbers["terminate_job_error"]=terminated?0:Marshal.GetLastWin32Error();
                stopped=terminated && stopped;
                for(int attempt=0;attempt<250;attempt++) {
                    JOB_ACCOUNTING accounting;
                    bool queried=QueryInformationJobObject(job,1,out accounting,(uint)Marshal.SizeOf(typeof(JOB_ACCOUNTING)),IntPtr.Zero);
                    r.Numbers["job_query_error"]=queried?0:Marshal.GetLastWin32Error();
                    if(!queried) break;
                    r.Numbers["job_active_processes"]=accounting.activeProcesses;
                    if(accounting.activeProcesses==0) {r.Drained=true;break;}
                    System.Threading.Thread.Sleep(20);
                }
                stopped=stopped && r.Drained;
            } else {r.Drained=!r.Created;}
            closeCertain=CloseOwned(ref pi.thread,"thread",r) && closeCertain;
            closeCertain=CloseOwned(ref pi.process,"process",r) && closeCertain;
            closeCertain=CloseOwned(ref job,"job",r) && closeCertain;
            if(initialized) DeleteProcThreadAttributeList(list);
            foreach(IntPtr allocation in new IntPtr[]{list,caps,policy,handles,env}) if(allocation!=IntPtr.Zero) Marshal.FreeHGlobal(allocation);
            if(sid!=IntPtr.Zero) FreeSid(sid);
            r.CleanupConfirmed=stopped && closeCertain && (!r.Created || (r.TokenVerified && r.Assigned && r.Resumed));
            if(stopped && r.Drained) {
                foreach(string file in new string[]{"stdout.txt","stderr.txt","script-entry.txt","mutation.txt","runtime-canary.txt","outside-read.txt","pre-network.txt","runtime-checks.txt","receipt.txt"})
                    closeCertain=CaptureOwnedFile(workspace,parent,file,r) && closeCertain;
                r.CleanupConfirmed=r.CleanupConfirmed && closeCertain;
            }
            if(r.CleanupConfirmed && profile) {
                int hr=DeleteAppContainerProfile(name);r.Numbers["delete_profile_hresult"]=hr;
                if(hr!=0) r.CleanupConfirmed=false;
            }
            if(!r.CleanupConfirmed) {
                File.WriteAllText(recovery,"Owned recovery resources retained: "+root+"; profile="+name);
            } else {
                if(Directory.Exists(root)) Directory.Delete(root,true);
                File.Delete(recovery);
            }
        }
        return r;
    }
}
