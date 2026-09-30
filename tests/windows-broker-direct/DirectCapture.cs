// Broker evidence reads occur only after the exact process stopped and its job drained.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static partial class BrokerDirectLauncher {
    static bool CaptureOwnedFile(string workspace,string parent,string file,DirectReceipt r) {
        const long CaptureLimit=1024*1024;
        string path=Path.Combine(workspace,file);IntPtr handle=IntPtr.Zero;bool closed=true;
        try {
            var security=new SECURITY_ATTRIBUTES();security.length=(uint)Marshal.SizeOf(security);security.inherit=false;
            handle=CreateFile(path,0x80000000,7,ref security,3,0x00200080,IntPtr.Zero);
            int error=handle==new IntPtr(-1)?Marshal.GetLastWin32Error():0;r.Numbers["capture_"+file+"_open_error"]=error;
            if(handle==new IntPtr(-1)) {
                handle=IntPtr.Zero;
                if(error==2 && !(r.StdioValidated && (file=="stdout.txt" || file=="stderr.txt"))) return true;
                throw new System.ComponentModel.Win32Exception(error,"owned evidence open");
            }
            FILE_INFO info;Check(GetFileInformationByHandle(handle,out info),"owned evidence information");
            r.Numbers["capture_"+file+"_advertised_bytes"]=((long)info.sizeHigh<<32)|info.sizeLow;
            if(info.sizeHigh!=0 || info.sizeLow>CaptureLimit) throw new InvalidOperationException("evidence exceeds 1 MiB capture limit");
            var finalPath=new StringBuilder(32768);uint length=GetFinalPathNameByHandle(handle,finalPath,(uint)finalPath.Capacity,0);
            Check(length>0 && length<finalPath.Capacity,"owned evidence final path");
            string actual=finalPath.ToString();if(actual.StartsWith("\\\\?\\")) actual=actual.Substring(4);
            string identity=info.volume+":"+info.indexHigh+":"+info.indexLow;
            if(GetFileType(handle)!=1 || (info.attributes&0x410)!=0 || info.links!=1 ||
                !String.Equals(actual,Path.GetFullPath(path),StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("evidence must remain a private regular file");
            if((file=="stdout.txt" && identity!=r.Identities["stdout"]) || (file=="stderr.txt" && identity!=r.Identities["stderr"]))
                throw new InvalidOperationException("stdio evidence object changed");
            r.Identities["capture_"+file]=identity;
            // Read via the validated no-follow handle, not a second path-based open.
            using(var safe=new SafeFileHandle(handle,false)) using(var source=new FileStream(safe,FileAccess.Read))
            using(var destination=new FileStream(Path.Combine(parent,file),FileMode.CreateNew,FileAccess.Write)) {
                var buffer=new byte[8192];long total=0;
                while(true) {
                    int count=source.Read(buffer,0,(int)Math.Min(buffer.Length,CaptureLimit+1-total));
                    if(count==0) break;
                    total+=count;
                    if(total>CaptureLimit) throw new InvalidOperationException("evidence stream exceeds 1 MiB capture limit");
                    destination.Write(buffer,0,count);
                }
                r.Numbers["capture_"+file+"_copied_bytes"]=total;
            }
        } finally {closed=CloseOwned(ref handle,"capture_"+file,r);}
        return closed;
    }
}
