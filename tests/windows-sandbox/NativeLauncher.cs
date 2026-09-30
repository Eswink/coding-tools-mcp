// Test-only documented Win32 LPAC launcher. No production execution entry.
using System;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static class LpacFixtureLauncher {
    const uint CREATE_SUSPENDED=4, EXTENDED=0x80000, UNICODE=0x400;
    const uint WAIT_OBJECT_0=0, WAIT_TIMEOUT=258;
    const uint TOKEN_ALL_PACKAGES_OPT_OUT=1, KILL_ON_JOB_CLOSE=0x2000;
    const uint LABEL_SECURITY_INFORMATION=0x10;
    [StructLayout(LayoutKind.Sequential)] struct SECURITY_CAPABILITIES {
        public IntPtr Sid, Capabilities; public uint Count, Reserved;
    }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct STARTUPINFO {
        public uint cb; public IntPtr reserved, desktop, title;
        public uint x,y,xSize,ySize,xCount,yCount,fill,flags;
        public ushort show, reserved2; public IntPtr reservedBytes,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)] struct STARTUPINFOEX {
        public STARTUPINFO Startup; public IntPtr Attributes;
    }
    [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION {
        public IntPtr process,thread; public uint pid,tid;
    }
    [StructLayout(LayoutKind.Sequential)] struct BASIC_LIMIT {
        public long processTime,jobTime; public uint flags;
        public UIntPtr minWorking,maxWorking; public uint activeLimit;
        public UIntPtr affinity; public uint priority,scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IO_COUNTERS {
        public ulong readOps,writeOps,otherOps,readBytes,writeBytes,otherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct JOB_ACCOUNTING {
        public long user,kernel,periodUser,periodKernel;
        public uint faults,totalProcesses,activeProcesses,terminatedProcesses;
    }
    [StructLayout(LayoutKind.Sequential)] struct EXTENDED_LIMIT {
        public BASIC_LIMIT Basic; public IO_COUNTERS Io;
        public UIntPtr processMemory,jobMemory,peakProcess,peakJob;
    }
    [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int CreateAppContainerProfile(
        string name,string display,string description,IntPtr capabilities,uint count,out IntPtr sid);
    [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int DeleteAppContainerProfile(string name);
    [DllImport("advapi32.dll")] static extern IntPtr FreeSid(IntPtr sid);
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool
        ConvertStringSecurityDescriptorToSecurityDescriptor(string sddl,uint revision,out IntPtr sd,out uint size);
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool
        SetFileSecurity(string name,uint info,IntPtr sd);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr p);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(
        IntPtr list,int count,int flags,ref IntPtr bytes);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(
        IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr bytes,IntPtr previous,IntPtr returned);
    [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(
        string app,StringBuilder command,IntPtr processAttrs,IntPtr threadAttrs,bool inherit,uint flags,
        IntPtr environment,string cwd,ref STARTUPINFOEX startup,out PROCESS_INFORMATION process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attrs,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(
        IntPtr job,int kind,ref EXTENDED_LIMIT value,uint size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(
        IntPtr job,int kind,out JOB_ACCOUNTING value,uint size,IntPtr returned);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint timeout);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    static void Check(bool ok,string label) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),label); }
    static string Quote(string s) {
        // All inputs are fixture paths/arguments. Reject syntax instead of accepting arbitrary shell quoting.
        if(s.IndexOf('"')>=0 || s.IndexOf('\0')>=0 || s.EndsWith("\\")) throw new ArgumentException("fixture argument rejected");
        return "\""+s+"\"";
    }
    static void OwnedAcl(string path,SecurityIdentifier package,FileSystemRights rights) {
        var acl=new DirectorySecurity();
        acl.SetAccessRuleProtection(true,false);
        var inheritance=InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit;
        acl.AddAccessRule(new FileSystemAccessRule(WindowsIdentity.GetCurrent().User,FileSystemRights.FullControl,
            inheritance,PropagationFlags.None,AccessControlType.Allow));
        acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.LocalSystemSid,null),
            FileSystemRights.FullControl,inheritance,PropagationFlags.None,AccessControlType.Allow));
        acl.AddAccessRule(new FileSystemAccessRule(package,rights,inheritance,PropagationFlags.None,AccessControlType.Allow));
        Directory.SetAccessControl(path,acl);
        IntPtr sd;uint length;
        Check(ConvertStringSecurityDescriptorToSecurityDescriptor("S:(ML;OICI;NW;;;LW)",1,out sd,out length),"owned fixture label parse");
        try { Check(SetFileSecurity(path,LABEL_SECURITY_INFORMATION,sd),"owned fixture integrity label"); }
        finally { LocalFree(sd); }
    }
    // root must be a NEW EMPTY directory created by this method; no caller-selected existing ACLs are touched.
    public static int Run(string fixture,string parent,string outside,int port,bool lpac) {
        string root=Path.Combine(parent,"lpac-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string code=Path.Combine(root,"code"),workspace=Path.Combine(root,"workspace");
        Directory.CreateDirectory(code);Directory.CreateDirectory(workspace);
        string exe=Path.Combine(code,"fixture.exe");File.Copy(fixture,exe,false);
        string name="ctm.fixture."+Guid.NewGuid().ToString("N");
        IntPtr sid=IntPtr.Zero,list=IntPtr.Zero,caps=IntPtr.Zero,policy=IntPtr.Zero,env=IntPtr.Zero,job=IntPtr.Zero;
        PROCESS_INFORMATION pi=new PROCESS_INFORMATION(); bool initialized=false,profile=false;
        try {
            int hr=CreateAppContainerProfile(name,name,"Temporary native containment test",IntPtr.Zero,0,out sid);
            if(hr!=0) Marshal.ThrowExceptionForHR(hr);
            profile=true;
            var package=new SecurityIdentifier(sid);
            // AAP-readable canary distinguishes LPAC from an ordinary AppContainer.
            // Outside is also freshly created synthetic test data, never a real workspace.
            OwnedAcl(outside,new SecurityIdentifier("S-1-15-2-1"),FileSystemRights.ReadAndExecute);
            OwnedAcl(root,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(code,package,FileSystemRights.ReadAndExecute);
            OwnedAcl(workspace,package,FileSystemRights.Modify);
            IntPtr bytes=IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero,lpac?2:1,0,ref bytes);
            if(bytes==IntPtr.Zero) throw new InvalidOperationException("attribute size unavailable");
            list=Marshal.AllocHGlobal(bytes);
            Check(InitializeProcThreadAttributeList(list,lpac?2:1,0,ref bytes),"attribute initialization");initialized=true;
            SECURITY_CAPABILITIES capabilities=new SECURITY_CAPABILITIES();capabilities.Sid=sid;
            caps=Marshal.AllocHGlobal(Marshal.SizeOf(capabilities));Marshal.StructureToPtr(capabilities,caps,false);
            Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20009),caps,
                new IntPtr(Marshal.SizeOf(capabilities)),IntPtr.Zero,IntPtr.Zero),"AppContainer attribute");
            if(lpac) {
                policy=Marshal.AllocHGlobal(4);Marshal.WriteInt32(policy,(int)TOKEN_ALL_PACKAGES_OPT_OUT);
                Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x2000f),policy,new IntPtr(4),IntPtr.Zero,IntPtr.Zero),"LPAC attribute");
            }
            job=CreateJobObject(IntPtr.Zero,null);Check(job!=IntPtr.Zero,"job creation");
            var limits=new EXTENDED_LIMIT();limits.Basic.flags=KILL_ON_JOB_CLOSE;
            Check(SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(limits)),"job limits");
            string environment="SystemRoot="+Environment.GetEnvironmentVariable("SystemRoot")+"\0TEMP="+workspace+"\0TMP="+workspace+"\0\0";
            env=Marshal.StringToHGlobalUni(environment);
            var startup=new STARTUPINFOEX();startup.Startup.cb=(uint)Marshal.SizeOf(startup);startup.Attributes=list;
            string command=Quote(exe)+" sandbox "+Quote(workspace)+" "+Quote(outside)+" 127.0.0.1:"+port;
            Check(CreateProcess(exe,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,false,
                CREATE_SUSPENDED|EXTENDED|UNICODE,env,workspace,ref startup,out pi),"LPAC create suspended");
            Check(AssignProcessToJobObject(job,pi.process),"assign before resume");
            if(ResumeThread(pi.thread)!=1) throw new InvalidOperationException("unexpected suspension state");
            uint wait=WaitForSingleObject(pi.process,15000);
            if(wait!=WAIT_OBJECT_0) throw new InvalidOperationException(wait==WAIT_TIMEOUT?"native fixture timeout":"native fixture wait failure");
            uint exit;Check(GetExitCodeProcess(pi.process,out exit),"fixture exit code");
            string receipt=Path.Combine(workspace,"receipt.txt");
            if(!File.Exists(receipt)) throw new InvalidOperationException("fixture did not produce receipt; startup is not containment proof");
            // Copy only fixed booleans into the evidence root; no source/payload paths.
            File.Copy(receipt,Path.Combine(parent,lpac?"sandbox-receipt.txt":"ordinary-appcontainer-receipt.txt"),false);
            return checked((int)exit);
        } finally {
            bool stopped=true;
            if(pi.process!=IntPtr.Zero) {
                TerminateProcess(pi.process,91);
                stopped=WaitForSingleObject(pi.process,5000)==WAIT_OBJECT_0;
            }
            if(job!=IntPtr.Zero) {
                stopped=TerminateJobObject(job,91) && stopped;
                bool drained=false;
                for(int attempt=0;attempt<250;attempt++) {
                    JOB_ACCOUNTING accounting;
                    if(!QueryInformationJobObject(job,1,out accounting,(uint)Marshal.SizeOf(typeof(JOB_ACCOUNTING)),IntPtr.Zero)) break;
                    if(accounting.activeProcesses==0) { drained=true;break; }
                    System.Threading.Thread.Sleep(20);
                }
                stopped=stopped && drained;
                CloseHandle(job);
            }
            if(pi.process!=IntPtr.Zero) CloseHandle(pi.process);
            if(pi.thread!=IntPtr.Zero) CloseHandle(pi.thread);
            if(initialized) DeleteProcThreadAttributeList(list);
            if(list!=IntPtr.Zero) Marshal.FreeHGlobal(list);
            if(caps!=IntPtr.Zero) Marshal.FreeHGlobal(caps);
            if(policy!=IntPtr.Zero) Marshal.FreeHGlobal(policy);
            if(env!=IntPtr.Zero) Marshal.FreeHGlobal(env);
            if(sid!=IntPtr.Zero) FreeSid(sid);
            if(!stopped) {
                // Keep owned recovery data and profile if process-tree termination is uncertain.
                File.WriteAllText(Path.Combine(parent,"cleanup-uncertain.txt"),"owned process-tree termination unconfirmed");
                throw new InvalidOperationException("fixture cleanup uncertain; resources retained");
            }
            if(profile) { int hr=DeleteAppContainerProfile(name);if(hr!=0) Marshal.ThrowExceptionForHR(hr); }
            // Only this newly created fixture directory is removed. No app journals or user workspace.
            Directory.Delete(root,true);
        }
    }
}
