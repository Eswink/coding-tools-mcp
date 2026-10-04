// Test-only documented Win32 LPAC launcher. No production execution entry.
using System;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static partial class BrokerDirectLauncher {
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
    static void Check(bool ok,string label) {
        if(!ok) {
            int code=Marshal.GetLastWin32Error();
            throw new Win32Exception(code,label+" win32="+code);
        }
    }
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
    // The payload is a disposable CI copy; reject links rather than traverse to an existing ACL scope.
    static void CopyOwnedBundle(string source,string target) {
        if((File.GetAttributes(source)&FileAttributes.ReparsePoint)!=0) throw new ArgumentException("bundle link rejected");
        foreach(string file in Directory.GetFiles(source)) {
            if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0) throw new ArgumentException("bundle file link rejected");
            File.Copy(file,Path.Combine(target,Path.GetFileName(file)),false);
        }
        foreach(string dir in Directory.GetDirectories(source)) {
            string child=Path.Combine(target,Path.GetFileName(dir));Directory.CreateDirectory(child);
            CopyOwnedBundle(dir,child);
        }
    }
}
