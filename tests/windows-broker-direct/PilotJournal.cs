// Current-invocation evidence journals only. Never reopen an earlier recovery owner.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static partial class BrokerDirectLauncher {
    sealed class PilotJournal {
        public readonly string Path,CompletedPath,PreconditionsPath,Nonce,Identity,Body;
        public readonly DirectReceipt Receipt;
        public bool Resolved,Failed;
        string PreconditionsIdentity,PreconditionsBody;
        bool PreconditionsBound;
        public PilotJournal(string directory,string label,string plannedRoot,string plannedProfile,DirectReceipt receipt) {
            SafePath(directory);SafePath(plannedRoot);
            if(plannedProfile!=null && (plannedProfile.Length>64 || plannedProfile.IndexOfAny(new char[]{'\r','\n','\0'})>=0))
                throw new ArgumentException("bounded planned diagnostic profile required");
            Receipt=receipt;Nonce=Guid.NewGuid().ToString("N");
            Path=System.IO.Path.Combine(directory,"cleanup-uncertain.txt");
            CompletedPath=System.IO.Path.Combine(directory,"completed-"+Nonce+".txt");
            PreconditionsPath=System.IO.Path.Combine(directory,"preconditions-"+Nonce+".json");
            Body="protocol=owned-pending-journal-v1\nstate=pending\nnonce="+Nonce+"\nlabel="+label+
                "\nplanned_root="+plannedRoot+"\nplanned_profile="+(plannedProfile??"none")+
                "\npreconditions_record="+System.IO.Path.GetFileName(PreconditionsPath)+
                "\nresolution=completed filename commits the immutable nonce-bound preconditions record; pending is not completion\n";
            receipt.Identities["pilot_journal_"+label+"_nonce"]=Nonce;
            IntPtr handle=IntPtr.Zero;bool closed=false;
            try {
                OpenPrivate(ref handle,Path,0x40000000,1,false,"journal_"+label,receipt);
                Identity=receipt.Identities["journal_"+label];
                WritePilotBytes(handle,Encoding.UTF8.GetBytes(Body));
            } finally {closed=PilotCloseHandle(ref handle,"journal_create_"+label,receipt);}
            if(!closed) throw new InvalidOperationException("journal creation close uncertain");
        }
        public void VerifyPending() {
            if(Resolved || Failed) throw new InvalidOperationException("only current pending journal may proceed");
            VerifyPilotStoredFile(Path,Identity,Body,Receipt,"journal_verify");
        }
        public void BindPreconditions(string body) {
            VerifyPending();if(PreconditionsBound) throw new InvalidOperationException("preconditions are immutable and single-use");
            WritePilotEvidence(PreconditionsPath,body,Receipt,"journal_preconditions_"+Nonce);
            PreconditionsIdentity=Receipt.Identities["evidence_journal_preconditions_"+Nonce];
            PreconditionsBody=body;PreconditionsBound=true;
        }
        public void Resolve() {
            PilotCommitBoundary(Resolved,Failed,PreconditionsBound,
                delegate {VerifyPending();},
                delegate {VerifyPilotStoredFile(PreconditionsPath,PreconditionsIdentity,PreconditionsBody,Receipt,"journal_binding_verify");},
                delegate {File.Move(Path,CompletedPath);});
            // Same-directory no-replace rename is the final required fallible pilot action.
            Resolved=true;
        }
    }
    static void VerifyPilotStoredFile(string path,string identity,string body,DirectReceipt receipt,string label) {
        byte[] expected=Encoding.UTF8.GetBytes(body);
        if(expected.Length>4*1024*1024) throw new InvalidOperationException("bounded immutable evidence required");
        IntPtr handle=IntPtr.Zero;bool closed=false;
        try {
            var security=new SECURITY_ATTRIBUTES();security.length=(uint)Marshal.SizeOf(security);security.inherit=false;
            handle=CreateFile(path,0x80000000,1,ref security,3,0x00200080,IntPtr.Zero);
            if(handle==new IntPtr(-1)) {int error=Marshal.GetLastWin32Error();handle=IntPtr.Zero;throw new System.ComponentModel.Win32Exception(error,"owned journal/evidence open");}
            FILE_INFO info;Check(GetFileInformationByHandle(handle,out info),"owned journal/evidence information");
            uint flags;Check(GetHandleInformation(handle,out flags),"owned journal/evidence flags");
            var final=new StringBuilder(32768);uint length=GetFinalPathNameByHandle(handle,final,(uint)final.Capacity,0);
            Check(length>0 && length<final.Capacity,"owned journal/evidence path");
            string actual=final.ToString();if(actual.StartsWith("\\\\?\\")) actual=actual.Substring(4);
            string observed=info.volume+":"+info.indexHigh+":"+info.indexLow;
            if((flags&1)!=0 || GetFileType(handle)!=1 || (info.attributes&0x410)!=0 || info.links!=1 ||
                info.sizeHigh!=0 || info.sizeLow!=expected.Length || observed!=identity ||
                !String.Equals(actual,System.IO.Path.GetFullPath(path),StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("journal/evidence identity or boundary changed");
            using(var safe=new SafeFileHandle(handle,false)) using(var stream=new FileStream(safe,FileAccess.Read)) {
                for(int i=0;i<expected.Length;i++) if(stream.ReadByte()!=expected[i]) throw new InvalidOperationException("journal/evidence content changed");
                if(stream.ReadByte()!=-1) throw new InvalidOperationException("journal/evidence trailing data");
            }
        } finally {closed=PilotCloseHandle(ref handle,label,receipt);}
        if(!closed) throw new InvalidOperationException("journal/evidence validation close uncertain");
    }
    static void WritePilotBytes(IntPtr handle,byte[] bytes) {
        using(var safe=new SafeFileHandle(handle,false)) using(var stream=new FileStream(safe,FileAccess.Write)) {
            stream.Write(bytes,0,bytes.Length);stream.Flush(true);
        }
    }
    static void WritePilotEvidence(string path,string value,DirectReceipt receipt,string label) {
        SafePath(path);byte[] bytes=Encoding.UTF8.GetBytes(value);
        if(bytes.Length>4*1024*1024) throw new InvalidOperationException("broker receipt exceeds 4 MiB bound");
        IntPtr handle=IntPtr.Zero;bool closed=false;
        try {OpenPrivate(ref handle,path,0x40000000,1,false,"evidence_"+label,receipt);WritePilotBytes(handle,bytes);}
        finally {closed=PilotCloseHandle(ref handle,"evidence_"+label,receipt);}
        if(!closed) throw new InvalidOperationException("broker evidence close uncertain");
    }
}
