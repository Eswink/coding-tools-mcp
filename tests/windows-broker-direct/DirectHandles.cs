// Read-only object/token inspection. No token alteration or general handle forwarding.
using System;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Collections.Generic;
using System.Text;

public static partial class BrokerDirectLauncher {
    [StructLayout(LayoutKind.Sequential)] struct SECURITY_ATTRIBUTES {
        public uint length; public IntPtr descriptor; [MarshalAs(UnmanagedType.Bool)] public bool inherit;
    }
    [StructLayout(LayoutKind.Sequential)] struct FILE_INFO {
        public uint attributes,creationLow,creationHigh,accessLow,accessHigh,writeLow,writeHigh;
        public uint volume,sizeHigh,sizeLow,links,indexHigh,indexLow;
    }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(
        string name,uint access,uint share,ref SECURITY_ATTRIBUTES attributes,uint creation,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint GetFileType(IntPtr file);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetHandleInformation(IntPtr handle,out uint flags);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(IntPtr file,out FILE_INFO info);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetFinalPathNameByHandle(
        IntPtr file,StringBuilder path,uint size,uint flags);
    [DllImport("kernel32.dll",EntryPoint="CloseHandle",SetLastError=true)] static extern bool CloseChecked(IntPtr handle);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(
        IntPtr token,int kind,IntPtr buffer,uint length,out uint returned);
    [DllImport("advapi32.dll")] static extern bool IsValidSid(IntPtr sid);

    public sealed class DirectReceipt {
        public string Kind,Stage="setup",Failure,Executable,CommandLine,ExecutableSha256,ProfileSid;
        public bool CreateAttempted,Created,StdioValidated,HostStdioClosed,TokenVerified,Assigned,Resumed,Drained,CleanupConfirmed;
        public int CreateError=-1,FailureCode;
        public uint Wait=UInt32.MaxValue,Exit=UInt32.MaxValue,CreationFlags=0x08080404;
        public int HandleListCount;
        public string StdinKind="broker_fresh_private_empty_regular_file";
        public Dictionary<string,long> Numbers=new Dictionary<string,long>();
        public Dictionary<string,string> Identities=new Dictionary<string,string>();
    }
    static bool CloseOwned(ref IntPtr handle,string label,DirectReceipt r) {
        if(handle==IntPtr.Zero) return true;
        bool ok=CloseChecked(handle);int error=ok?0:Marshal.GetLastWin32Error();
        r.Numbers[label+"_close_error"]=error;
        // Never blindly retry an uncertain close: preserve its original numeric observation.
        handle=IntPtr.Zero;
        return ok;
    }
    static void OpenPrivate(ref IntPtr handle,string path,uint access,uint creation,bool inherit,string label,DirectReceipt r) {
        var security=new SECURITY_ATTRIBUTES();security.length=(uint)Marshal.SizeOf(security);security.inherit=inherit;
        handle=CreateFile(path,access,7,ref security,creation,0x00200080,IntPtr.Zero);
        int error=handle==new IntPtr(-1)?Marshal.GetLastWin32Error():0;
        r.Numbers[label+"_open_error"]=error;r.Numbers[label+"_desired_access"]=access;
        if(handle==new IntPtr(-1)) {handle=IntPtr.Zero;throw new Win32Exception(error,label+" open");}
        uint handleFlags;Check(GetHandleInformation(handle,out handleFlags),label+" handle information");
        r.Numbers[label+"_handle_flags"]=handleFlags;
        if(((handleFlags&1)!=0)!=inherit) throw new InvalidOperationException("stdio inheritance flag mismatch");
        r.Numbers[label+"_file_type"]=GetFileType(handle);
        FILE_INFO info;Check(GetFileInformationByHandle(handle,out info),label+" file information");
        r.Numbers[label+"_attributes"]=info.attributes;r.Numbers[label+"_length"]=((long)info.sizeHigh<<32)|info.sizeLow;
        r.Numbers[label+"_links"]=info.links;
        var finalPath=new StringBuilder(32768);
        uint length=GetFinalPathNameByHandle(handle,finalPath,(uint)finalPath.Capacity,0);
        Check(length>0 && length<finalPath.Capacity,label+" final path");
        string actual=finalPath.ToString();if(actual.StartsWith("\\\\?\\")) actual=actual.Substring(4);
        if(r.Numbers[label+"_file_type"]!=1 || (info.attributes&0x410)!=0 || info.sizeHigh!=0 || info.sizeLow!=0 || info.links!=1 ||
            !String.Equals(actual,Path.GetFullPath(path),StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(label+" not the exact fresh empty regular file");
        r.Identities[label]=info.volume+":"+info.indexHigh+":"+info.indexLow;
    }
    static IntPtr TokenData(IntPtr token,int kind,string label,DirectReceipt r) {
        uint size;bool initial=GetTokenInformation(token,kind,IntPtr.Zero,0,out size);
        int error=initial?0:Marshal.GetLastWin32Error();
        r.Numbers[label+"_size_error"]=error;r.Numbers[label+"_required_bytes"]=size;
        if(initial || error!=122 || size==0 || size>65536) throw new InvalidOperationException(label+" token sizing failed");
        IntPtr data=Marshal.AllocHGlobal((int)size);
        uint returned;bool ok=GetTokenInformation(token,kind,data,size,out returned);
        error=ok?0:Marshal.GetLastWin32Error();r.Numbers[label+"_query_error"]=error;r.Numbers[label+"_returned_bytes"]=returned;
        if(!ok || returned==0 || returned>size) {Marshal.FreeHGlobal(data);throw new InvalidOperationException(label+" token query failed");}
        return data;
    }
    static int TokenCount(IntPtr token,int kind,string label,DirectReceipt r) {
        IntPtr data=TokenData(token,kind,label,r);
        try {
            if(r.Numbers[label+"_returned_bytes"]<4) throw new InvalidOperationException("short token integer");
            int value=Marshal.ReadInt32(data);r.Numbers[label+"_value"]=value;return value;
        } finally {Marshal.FreeHGlobal(data);}
    }
    static string TokenSid(IntPtr token,int kind,string label,DirectReceipt r) {
        IntPtr data=TokenData(token,kind,label,r);
        try {
            long returned=r.Numbers[label+"_returned_bytes"];
            // TOKEN_MANDATORY_LABEL is SID_AND_ATTRIBUTES; TOKEN_APPCONTAINER_INFORMATION is a pointer.
            long header=kind==25?(IntPtr.Size==8?16:8):IntPtr.Size;
            if(returned<header) throw new InvalidOperationException("short token SID structure");
            IntPtr sid=Marshal.ReadIntPtr(data);
            ulong start=unchecked((ulong)data.ToInt64()),pointer=unchecked((ulong)sid.ToInt64());
            if(pointer<start || pointer-start<(ulong)header || pointer-start>(ulong)returned ||
                (ulong)returned-(pointer-start)<8) throw new InvalidOperationException("token SID pointer outside returned buffer");
            uint sidBytes=8u+4u*Marshal.ReadByte(sid,1);
            r.Numbers[label+"_sid_bytes"]=sidBytes;r.Numbers[label+"_sid_offset"]=(long)(pointer-start);
            if(sidBytes>(ulong)returned-(pointer-start) || !IsValidSid(sid))
                throw new InvalidOperationException("token SID span invalid");
            string value=new SecurityIdentifier(sid).Value;r.Identities[label]=value;return value;
        } finally {Marshal.FreeHGlobal(data);}
    }
    static void ObserveLpacSizing(IntPtr token,DirectReceipt r) {
        uint size;bool success=GetTokenInformation(token,46,IntPtr.Zero,0,out size);
        int error=success?0:Marshal.GetLastWin32Error();
        // Preserve the original null/zero observation, including its error87 on the prior run.
        r.Numbers["lpac_size_call_success"]=success?1:0;
        r.Numbers["lpac_size_error"]=error;r.Numbers["lpac_required_bytes"]=size;
        r.Numbers["lpac_sizing_expected_insufficient_buffer"] = !success && error==122 && size==4 ? 1 : 0;
    }
    static int? ObserveFixedLpacDword(IntPtr token,DirectReceipt r) {
        // DWORD is a native-enum hypothesis, not a portable Win32 support guarantee.
        // One aligned, initialized four-byte observation; no alternate/native query path.
        IntPtr data=Marshal.AllocHGlobal(4);
        try {
            Marshal.WriteInt32(data,unchecked((int)0xA5A5A5A5));
            uint returned;bool success=GetTokenInformation(token,46,data,4,out returned);
            int error=success?0:Marshal.GetLastWin32Error();
            int raw=Marshal.ReadInt32(data);
            r.Numbers["lpac_fixed_buffer_bytes"]=4;r.Numbers["lpac_fixed_initial_value"]=unchecked((int)0xA5A5A5A5);
            r.Numbers["lpac_fixed_query_success"]=success?1:0;r.Numbers["lpac_fixed_query_error"]=error;
            r.Numbers["lpac_fixed_returned_bytes"]=returned;r.Numbers["lpac_fixed_raw_value"]=raw;
            r.Numbers["lpac_fixed_value_valid"]=success && returned==4 ? 1 : 0;
            if(!success || returned!=4) return null;
            return raw;
        } finally {Marshal.FreeHGlobal(data);}
    }
    static bool RequiredTokenObservation(Func<bool> observation,string label,DirectReceipt r) {
        bool success=false;
        try {success=observation();}
        catch(Exception failure) {r.Identities[label+"_observation_failure"]=failure.GetType().Name;}
        r.Numbers[label+"_observation_success"]=success?1:0;return success;
    }
    static bool VerifyToken(IntPtr process,string package,DirectReceipt r) {
        IntPtr token=IntPtr.Zero;bool valid=false,closed=true;
        try {
            bool opened=OpenProcessToken(process,8,out token);
            r.Numbers["token_open_error"]=opened?0:Marshal.GetLastWin32Error();
            Check(opened,"read-only target token");
            int? app=null,lpac=null,capabilities=null;string actualPackage=null,integrity=null;
            bool all=true;
            // Each left operand runs even after a previous failure. Missing data stays null.
            all=RequiredTokenObservation(delegate {app=TokenCount(token,29,"appcontainer",r);return r.Numbers["appcontainer_returned_bytes"]==4;},"appcontainer",r) && all;
            ObserveLpacSizing(token,r);
            all=RequiredTokenObservation(delegate {lpac=ObserveFixedLpacDword(token,r);return lpac.HasValue;},"lpac",r) && all;
            all=RequiredTokenObservation(delegate {capabilities=TokenCount(token,30,"capabilities",r);return true;},"capabilities",r) && all;
            all=RequiredTokenObservation(delegate {actualPackage=TokenSid(token,31,"appcontainer_sid",r);return true;},"appcontainer_sid",r) && all;
            all=RequiredTokenObservation(delegate {integrity=TokenSid(token,25,"integrity_sid",r);return true;},"integrity_sid",r) && all;
            valid=all && app==1 && lpac==1 && capabilities==0 && actualPackage==package && integrity=="S-1-16-4096";
        } finally {closed=CloseOwned(ref token,"token",r);}
        return valid && closed;
    }
}
