// Test-only owned-scope disposal. The coordinator supplies the terminal lifecycle gate.
using System;
using System.IO;
using System.ComponentModel;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

public static partial class BrokerDirectLauncher {
    const int PilotDirectoryBuffer=65536, PilotEntryLimit=32768, PilotDepthLimit=32;
    const uint PilotReadDirectory=0x00020081, PilotDeleteAccess=0x00010080;

    sealed class PilotOwnedScope {
        public readonly string Parent,Root,Leaf,ParentIdentity,RootIdentity;
        public readonly uint Volume;
        public bool RemovalAttempted,RemovalConfirmed;
        public PilotOwnedScope(string parent,string root,string leaf,string parentIdentity,string rootIdentity,uint volume) {
            Parent=parent;Root=root;Leaf=leaf;ParentIdentity=parentIdentity;RootIdentity=rootIdentity;Volume=volume;
        }
    }
    sealed class PilotDirectoryEntry {
        public string Name;public uint Attributes;public ulong FileId;
    }
    sealed class PilotCleanupBudget {
        public int Entries,Queries,Handles;
    }
    [DllImport("kernel32.dll",EntryPoint="CreateDirectoryW",CharSet=CharSet.Unicode,ExactSpelling=true,SetLastError=true)]
    static extern bool PilotCreateDirectory(string path,IntPtr security);
    [DllImport("kernel32.dll",EntryPoint="GetFileInformationByHandleEx",SetLastError=true)]
    static extern bool PilotGetDirectoryInformation(IntPtr handle,int kind,IntPtr data,uint bytes);
    [DllImport("kernel32.dll",EntryPoint="SetFileInformationByHandle",SetLastError=true)]
    static extern bool PilotSetDisposition(IntPtr handle,int kind,ref byte delete,uint bytes);
    [DllImport("advapi32.dll",EntryPoint="GetKernelObjectSecurity",SetLastError=true)]
    static extern bool PilotGetObjectSecurity(IntPtr handle,uint information,IntPtr data,uint bytes,out uint needed);
    [DllImport("kernel32.dll",EntryPoint="GetCurrentProcess",ExactSpelling=true)]
    static extern IntPtr PilotGetCurrentProcess();

    static string PilotOwnedPath(string path) {
        SafePath(path);
        string full=Path.GetFullPath(path).TrimEnd('\\');
        if(full.Length<4 || full.Length>32700 || !((full[0]>='A' && full[0]<='Z') || (full[0]>='a' && full[0]<='z')) || full[1]!=':' || full[2]!='\\' ||
            full.IndexOf(':',2)>=0 || full.IndexOf('/')>=0 ||
            !String.Equals(full,path.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("pilot requires an exact local absolute directory path");
        return full;
    }
    static void PilotLeafName(string name,bool generated) {
        if(String.IsNullOrEmpty(name) || name.Length>255 || name=="." || name==".." ||
            name.EndsWith(".",StringComparison.Ordinal) || name.EndsWith(" ",StringComparison.Ordinal) ||
            name.IndexOfAny(Path.GetInvalidFileNameChars())>=0 || name.IndexOfAny(new char[]{'\\','/',':'})>=0)
            throw new InvalidOperationException("pilot directory name rejected");
        foreach(char c in name) if(Char.IsControl(c)) throw new InvalidOperationException("pilot control character in name");
        // Also rejects isolated UTF-16 surrogates without accepting replacement characters.
        new UnicodeEncoding(false,false,true).GetBytes(name);
        string stem=name.Split('.')[0].ToUpperInvariant();
        if(stem=="CON" || stem=="PRN" || stem=="AUX" || stem=="NUL" || stem=="CONIN$" || stem=="CONOUT$" ||
            (stem.Length==4 && (stem.StartsWith("COM",StringComparison.Ordinal) || stem.StartsWith("LPT",StringComparison.Ordinal)) &&
            ((stem[3]>='1' && stem[3]<='9') || stem[3]=='\u00b9' || stem[3]=='\u00b2' || stem[3]=='\u00b3')))
            throw new InvalidOperationException("pilot DOS device alias rejected");
        if(!generated) return;
        string prefix=name.StartsWith("ctm-direct-pilot-",StringComparison.Ordinal)?"ctm-direct-pilot-":"owned-";
        if(!name.StartsWith(prefix,StringComparison.Ordinal) || name.Length!=prefix.Length+32)
            throw new ArgumentException("pilot generated root name required");
        for(int i=prefix.Length;i<name.Length;i++)
            if(!((name[i]>='0' && name[i]<='9') || (name[i]>='a' && name[i]<='f')))
                throw new ArgumentException("pilot generated root suffix rejected");
    }
    static bool PilotCloseHandle(ref IntPtr handle,string label,DirectReceipt r) {
        // Transfer once so even a throwing close cannot be retried by an outer finally.
        IntPtr owned=handle;handle=IntPtr.Zero;
        try {
            bool closed=CloseOwned(ref owned,label,r);r.Numbers[label+"_close_confirmed"]=closed?1:0;return closed;
        } catch(Exception failure) {
            r.Identities[label+"_close_exception"]=failure.GetType().Name;
            r.Numbers[label+"_close_confirmed"]=0;return false;
        }
    }
    static bool PilotFreeBuffer(ref IntPtr data,string label,DirectReceipt r) {
        IntPtr owned=data;data=IntPtr.Zero;
        try {
            if(owned!=IntPtr.Zero) Marshal.FreeHGlobal(owned);
            r.Numbers[label+"_free_confirmed"]=1;return true;
        } catch(Exception failure) {
            r.Identities[label+"_free_exception"]=failure.GetType().Name;
            r.Numbers[label+"_free_confirmed"]=0;return false;
        }
    }
    static void PilotOpenHandle(ref IntPtr handle,string path,uint access,bool directory,string label,DirectReceipt r) {
        var security=new SECURITY_ATTRIBUTES();security.length=(uint)Marshal.SizeOf(security);security.inherit=false;
        // Deny write/delete sharing while the exact object is pinned. BACKUP_SEMANTICS
        // is required for directory handles; no privilege is enabled or requested.
        IntPtr opened=CreateFile(path,access,1,ref security,3,directory?0x02200000u:0x00200000u,IntPtr.Zero);
        int error=opened==new IntPtr(-1)?Marshal.GetLastWin32Error():0;
        r.Numbers[label+"_open_error"]=error;r.Numbers[label+"_desired_access"]=access;
        if(opened==new IntPtr(-1)) throw new Win32Exception(error,"pilot owned object open");
        if(opened==IntPtr.Zero) throw new InvalidOperationException("pilot open returned an ambiguous handle");
        handle=opened;
        uint flags;Check(GetHandleInformation(handle,out flags),"pilot handle information");
        r.Numbers[label+"_handle_flags"]=flags;
        if((flags&1)!=0) throw new InvalidOperationException("pilot cleanup handle inherited");
    }
    static FILE_INFO PilotValidateObject(IntPtr handle,string path,bool directory,string identity,uint? volume) {
        FILE_INFO info;Check(GetFileInformationByHandle(handle,out info),"pilot owned object information");
        if(GetFileType(handle)!=1 || (info.attributes&0x440)!=0 || ((info.attributes&0x10)!=0)!=directory ||
            (!directory && info.links!=1) || (info.indexHigh==0 && info.indexLow==0) ||
            (volume.HasValue && info.volume!=volume.Value))
            throw new InvalidOperationException("pilot link, nonregular object, or volume mismatch");
        string actualIdentity=info.volume+":"+info.indexHigh+":"+info.indexLow;
        if(identity!=null && !String.Equals(identity,actualIdentity,StringComparison.Ordinal))
            throw new InvalidOperationException("pilot owned object identity changed");
        var finalPath=new StringBuilder(32768);
        uint length=GetFinalPathNameByHandle(handle,finalPath,(uint)finalPath.Capacity,0);
        Check(length>0 && length<finalPath.Capacity,"pilot owned object final path");
        string actual=finalPath.ToString();if(actual.StartsWith("\\\\?\\",StringComparison.Ordinal)) actual=actual.Substring(4);
        if(!String.Equals(actual,path,StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("pilot owned object containment mismatch");
        return info;
    }
    // Separate broker-owner metadata query, never the target authority predicate.
    // The returned SID stays in memory for parent ownership/ACE comparisons only.
    static string PilotBrokerOwnerSid(string label,DirectReceipt r) {
        IntPtr token=IntPtr.Zero,data=IntPtr.Zero;string sidValue=null;
        bool freed=false,closed=false;
        r.Numbers[label+"_broker_owner_query_confirmed"]=0;
        try {
            IntPtr returnedToken=IntPtr.Zero;
            // GetCurrentProcess is a borrowed pseudo handle: never duplicate or close it.
            bool opened=OpenProcessToken(PilotGetCurrentProcess(),0x8,out returnedToken);
            int error=opened?0:Marshal.GetLastWin32Error();
            bool validOutput=returnedToken!=IntPtr.Zero && returnedToken!=new IntPtr(-1);
            if(opened && validOutput) token=returnedToken;
            r.Numbers[label+"_broker_owner_token_desired_access"]=0x8;
            r.Numbers[label+"_broker_owner_token_open_success"]=opened?1:0;
            r.Numbers[label+"_broker_owner_token_open_error"]=error;
            r.Numbers[label+"_broker_owner_token_unowned_output"]=token==IntPtr.Zero && returnedToken!=IntPtr.Zero?1:0;
            if(!opened || !validOutput) throw new InvalidOperationException("pilot broker-owner token open uncertain");
            uint flags;bool inspected=GetHandleInformation(token,out flags);
            error=inspected?0:Marshal.GetLastWin32Error();
            r.Numbers[label+"_broker_owner_handle_query_success"]=inspected?1:0;
            r.Numbers[label+"_broker_owner_handle_query_error"]=error;
            r.Numbers[label+"_broker_owner_handle_flags"]=flags;
            if(!inspected || (flags&1)!=0) throw new InvalidOperationException("pilot broker-owner handle inheritance unverified");
            uint needed;bool sized=GetTokenInformation(token,1,IntPtr.Zero,0,out needed);
            error=sized?0:Marshal.GetLastWin32Error();
            r.Numbers[label+"_broker_owner_size_success"]=sized?1:0;
            r.Numbers[label+"_broker_owner_size_error"]=error;
            r.Numbers[label+"_broker_owner_required_bytes"]=needed;
            uint header=IntPtr.Size==8?16u:8u; // TOKEN_USER contains SID_AND_ATTRIBUTES.
            if(sized || error!=122 || needed<header+8 || needed>65536)
                throw new InvalidOperationException("pilot broker-owner TokenUser sizing rejected");
            data=Marshal.AllocHGlobal((int)needed);
            uint returned;bool queried=GetTokenInformation(token,1,data,needed,out returned);
            error=queried?0:Marshal.GetLastWin32Error();
            r.Numbers[label+"_broker_owner_read_success"]=queried?1:0;
            r.Numbers[label+"_broker_owner_read_error"]=error;
            r.Numbers[label+"_broker_owner_returned_bytes"]=returned;
            if(!queried || returned<header+8 || returned>needed)
                throw new InvalidOperationException("pilot broker-owner TokenUser query rejected");
            IntPtr sid=Marshal.ReadIntPtr(data);
            ulong start=unchecked((ulong)data.ToInt64()),pointer=unchecked((ulong)sid.ToInt64());
            if(pointer<start || pointer-start<header || pointer-start>returned || returned-(pointer-start)<8)
                throw new InvalidOperationException("pilot broker-owner SID pointer outside returned buffer");
            uint sidBytes=8u+4u*Marshal.ReadByte(sid,1);
            if(sidBytes>returned-(pointer-start) || !IsValidSid(sid))
                throw new InvalidOperationException("pilot broker-owner SID span invalid");
            sidValue=new SecurityIdentifier(sid).Value;
        } finally {
            // Both known-owned releases are attempted; an uncertain one is never retried.
            try {freed=PilotFreeBuffer(ref data,label+"_broker_owner_data",r);}
            finally {closed=PilotCloseHandle(ref token,label+"_broker_owner_token",r);}
            if(!freed || !closed) throw new InvalidOperationException("pilot broker-owner cleanup uncertain");
        }
        r.Numbers[label+"_broker_owner_query_confirmed"]=1;
        return sidValue;
    }
    static string PilotOwnerCategory(string sid,string broker) {
        if(sid==broker) return "current_broker";
        if(sid=="S-1-5-18") return "system";
        if(sid=="S-1-5-32-544") return "administrators";
        if(sid=="S-1-3-0") return "creator_owner";
        return "other";
    }
    // Observation only: finish the already-buffered ACL before evaluating trust.
    // Completion/count are committed only after every ACE's existing metadata succeeds.
    static void RecordPilotParentAcl(RawSecurityDescriptor descriptor,string user,string label,DirectReceipt r) {
        r.Numbers[label+"_acl_observation_completed"]=0;
        r.Numbers[label+"_acl_observed_ace_count"]=-1;
        int observed=0;
        if(descriptor.DiscretionaryAcl!=null) foreach(GenericAce raw in descriptor.DiscretionaryAcl) {
            string aceLabel=label+"_ace_"+observed;
            r.Identities[aceLabel+"_type"]=raw.GetType().Name;
            r.Numbers[aceLabel+"_native_type"]=(int)raw.AceType;
            r.Numbers[aceLabel+"_flags"]=(int)raw.AceFlags;
            var known=raw as KnownAce;
            if(known!=null) {
                r.Numbers[aceLabel+"_access_mask"]=unchecked((uint)known.AccessMask);
                r.Identities[aceLabel+"_sid_category"]=PilotOwnerCategory(known.SecurityIdentifier==null?null:known.SecurityIdentifier.Value,user);
            }
            var ace=raw as CommonAce;
            if(ace!=null) {
                r.Numbers[aceLabel+"_qualifier"]=(int)ace.AceQualifier;
                r.Numbers[aceLabel+"_callback"]=ace.IsCallback?1:0;
            }
            observed++;
        }
        r.Numbers[label+"_acl_observed_ace_count"]=observed;
        r.Numbers[label+"_acl_observation_completed"]=1;
    }
    static FILE_INFO PilotValidateParent(IntPtr handle,string path,string identity,string label,DirectReceipt r) {
        FILE_INFO info=PilotValidateObject(handle,path,true,identity,null);
        IntPtr data=IntPtr.Zero;
        try {
            uint needed;bool sized=PilotGetObjectSecurity(handle,5,IntPtr.Zero,0,out needed);
            int error=sized?0:Marshal.GetLastWin32Error();r.Numbers[label+"_security_size_error"]=error;
            if(sized || error!=122 || needed<20 || needed>65536)
                throw new InvalidOperationException("pilot parent security sizing failed");
            data=Marshal.AllocHGlobal((int)needed);
            uint returned;bool read=PilotGetObjectSecurity(handle,5,data,needed,out returned);
            error=read?0:Marshal.GetLastWin32Error();r.Numbers[label+"_security_read_error"]=error;
            if(!read || returned<20 || returned>needed) throw new InvalidOperationException("pilot parent security query failed");
            var bytes=new byte[returned];Marshal.Copy(data,bytes,0,bytes.Length);
            var descriptor=new RawSecurityDescriptor(bytes,0);
            string user=PilotBrokerOwnerSid(label,r);
            string owner=descriptor.Owner==null?null:descriptor.Owner.Value;
            r.Identities[label+"_owner_category"]=PilotOwnerCategory(owner,user);
            r.Numbers[label+"_security_control_flags"]=(int)descriptor.ControlFlags;
            r.Numbers[label+"_dacl_ace_count"]=descriptor.DiscretionaryAcl==null?-1:descriptor.DiscretionaryAcl.Count;
            r.Numbers[label+"_broker_owned"]=0;
            r.Numbers[label+"_first_rejected_ace_index"]=-1;
            r.Identities[label+"_first_rejected_reason"]="not_evaluated";
            RecordPilotParentAcl(descriptor,user,label,r);
            r.Identities[label+"_first_rejected_reason"]="none";
            if((owner!=user && owner!="S-1-5-18" && owner!="S-1-5-32-544") ||
                (descriptor.ControlFlags&ControlFlags.DiscretionaryAclPresent)==0 || descriptor.DiscretionaryAcl==null) {
                r.Identities[label+"_first_rejected_reason"]="owner_or_dacl";
                throw new InvalidOperationException("pilot parent is not broker-owned");
            }
            // Exact original rejection order/predicate, including inherit-only grants.
            const uint writeMask=0x500D0156; // GENERIC_WRITE/ALL, DELETE, WRITE_DAC/OWNER, directory writes.
            int aceIndex=0;
            foreach(GenericAce raw in descriptor.DiscretionaryAcl) {
                int currentIndex=aceIndex++;
                var ace=raw as CommonAce;
                if(ace==null || ace.IsCallback || (ace.AceQualifier!=AceQualifier.AccessAllowed && ace.AceQualifier!=AceQualifier.AccessDenied)) {
                    r.Numbers[label+"_first_rejected_ace_index"]=currentIndex;
                    r.Identities[label+"_first_rejected_reason"]="unsupported_ace_shape";
                    throw new InvalidOperationException("pilot parent ACL shape unsupported");
                }
                if(ace.AceQualifier!=AceQualifier.AccessAllowed) continue;
                uint mask=unchecked((uint)ace.AccessMask);
                if((mask&~0xF01F01FFu)!=0) {
                    r.Numbers[label+"_first_rejected_ace_index"]=currentIndex;
                    r.Identities[label+"_first_rejected_reason"]="unsupported_access_mask";
                    throw new InvalidOperationException("pilot parent ACL access mask unsupported");
                }
                string sid=ace.SecurityIdentifier.Value;
                if((mask&writeMask)!=0 && sid!=user && sid!="S-1-5-18" && sid!="S-1-5-32-544") {
                    r.Numbers[label+"_first_rejected_ace_index"]=currentIndex;
                    r.Identities[label+"_first_rejected_reason"]="untrusted_write_grant";
                    throw new InvalidOperationException("pilot parent has an untrusted write grant");
                }
            }
            r.Numbers[label+"_broker_owned"]=1;
        } finally {
            if(!PilotFreeBuffer(ref data,label+"_security",r)) throw new InvalidOperationException("pilot parent security free uncertain");
        }
        return info;
    }
    static List<PilotDirectoryEntry> PilotEnumerateDirectory(IntPtr handle,string label,PilotCleanupBudget budget,DirectReceipt r) {
        // FILE_ID_BOTH_DIR_INFO: fixed fields through FileId occupy 104 bytes.
        // Each nonterminal NextEntryOffset is DWORDLONG-aligned. The Win32 API
        // gives no returned-byte count, so every span is bounded by the supplied buffer.
        const int header=104;
        IntPtr data=IntPtr.Zero;var entries=new List<PilotDirectoryEntry>();
        var names=new Dictionary<string,bool>(StringComparer.OrdinalIgnoreCase);
        try {
            data=Marshal.AllocHGlobal(PilotDirectoryBuffer);
            if((data.ToInt64()&7)!=0) throw new InvalidOperationException("pilot enumeration buffer alignment");
            var clear=new byte[PilotDirectoryBuffer];bool first=true;
            while(true) {
                if(++budget.Queries>PilotEntryLimit+1) throw new InvalidOperationException("pilot enumeration query bound");
                Marshal.Copy(clear,0,data,clear.Length);
                bool queried=PilotGetDirectoryInformation(handle,first?11:10,data,PilotDirectoryBuffer);first=false;
                int error=queried?0:Marshal.GetLastWin32Error();r.Numbers[label+"_enumeration_error"]=error;
                if(!queried) {
                    if(error!=18) throw new Win32Exception(error,"pilot directory enumeration");
                    r.Numbers[label+"_enumeration_complete"]=1;return entries;
                }
                int offset=0;
                while(true) {
                    if(++budget.Entries>PilotEntryLimit || offset<0 || offset>PilotDirectoryBuffer-header || (offset&7)!=0)
                        throw new InvalidOperationException("pilot enumeration record bound");
                    uint next=unchecked((uint)Marshal.ReadInt32(data,offset));
                    uint nameBytes=unchecked((uint)Marshal.ReadInt32(data,offset+60));
                    if(nameBytes==0 || nameBytes>510 || (nameBytes&1)!=0 || nameBytes>PilotDirectoryBuffer-offset-header ||
                        (next!=0 && ((next&7)!=0 || next<header+nameBytes || next>PilotDirectoryBuffer-offset-header)))
                        throw new InvalidOperationException("pilot enumeration name/offset span");
                    int shortBytes=Marshal.ReadByte(data,offset+68);
                    if(shortBytes>24 || (shortBytes&1)!=0) throw new InvalidOperationException("pilot short-name span");
                    var nameData=new byte[nameBytes];Marshal.Copy(IntPtr.Add(data,offset+header),nameData,0,nameData.Length);
                    string name=new UnicodeEncoding(false,false,true).GetString(nameData);
                    if(names.ContainsKey(name)) throw new InvalidOperationException("pilot duplicate directory entry");
                    names.Add(name,true);
                    if(name!="." && name!="..") {
                        PilotLeafName(name,false);
                        entries.Add(new PilotDirectoryEntry {Name=name,Attributes=unchecked((uint)Marshal.ReadInt32(data,offset+56)),
                            FileId=unchecked((ulong)Marshal.ReadInt64(data,offset+96))});
                    }
                    if(next==0) break;
                    offset=checked(offset+(int)next);
                }
            }
        } finally {
            if(!PilotFreeBuffer(ref data,label+"_enumeration",r)) throw new InvalidOperationException("pilot enumeration free uncertain");
        }
    }
    static PilotOwnedScope CreatePilotOwnedScope(string parent,string generatedLeaf,DirectReceipt r) {
        parent=PilotOwnedPath(parent);PilotLeafName(generatedLeaf,true);
        string root=PilotOwnedPath(Path.Combine(parent,generatedLeaf));
        IntPtr parentHandle=IntPtr.Zero,rootHandle=IntPtr.Zero;PilotOwnedScope result=null;
        bool closed=true;r.Numbers["pilot_scope_creation_confirmed"]=0;
        r.Identities["pilot_owned_parent_path"]=parent;r.Identities["pilot_owned_root_path"]=root;
        try {
            PilotOpenHandle(ref parentHandle,parent,PilotReadDirectory,true,"pilot_create_parent",r);
            FILE_INFO parentInfo=PilotValidateParent(parentHandle,parent,null,"pilot_create_parent",r);
            string parentIdentity=parentInfo.volume+":"+parentInfo.indexHigh+":"+parentInfo.indexLow;
            r.Identities["pilot_owned_parent_identity"]=parentIdentity;
            bool created=PilotCreateDirectory(root,IntPtr.Zero);
            int error=created?0:Marshal.GetLastWin32Error();r.Numbers["pilot_create_root_error"]=error;
            if(!created) throw new Win32Exception(error,"pilot exact fresh root creation");
            r.Numbers["pilot_root_create_api_confirmed"]=1;
            PilotOpenHandle(ref rootHandle,root,0x80,true,"pilot_create_root",r);
            FILE_INFO rootInfo=PilotValidateObject(rootHandle,root,true,null,parentInfo.volume);
            string rootIdentity=rootInfo.volume+":"+rootInfo.indexHigh+":"+rootInfo.indexLow;
            r.Identities["pilot_owned_root_identity"]=rootIdentity;
            // Parent must still be the same broker-owned object after creation.
            PilotValidateParent(parentHandle,parent,parentIdentity,"pilot_create_parent_recheck",r);
            result=new PilotOwnedScope(parent,root,generatedLeaf,parentIdentity,rootIdentity,parentInfo.volume);
        } finally {
            closed=PilotCloseHandle(ref rootHandle,"pilot_create_root",r) && closed;
            closed=PilotCloseHandle(ref parentHandle,"pilot_create_parent",r) && closed;
        }
        if(!closed) throw new InvalidOperationException("pilot scope preparation close uncertain");
        r.Numbers["pilot_scope_creation_confirmed"]=1;return result;
    }
    static void PilotDeleteEntry(string path,bool directory,string identity,uint volume,int depth,PilotCleanupBudget budget,DirectReceipt r) {
        if(depth>PilotDepthLimit) throw new InvalidOperationException("pilot cleanup depth bound");
        IntPtr handle=IntPtr.Zero;string label="pilot_remove_entry_"+(++budget.Handles);
        try {
            PilotOpenHandle(ref handle,path,PilotDeleteAccess|(directory?1u:0u),directory,label,r);
            FILE_INFO info=PilotValidateObject(handle,path,directory,identity,volume);
            if((info.attributes&1)!=0) throw new InvalidOperationException("pilot read-only object retained without repair");
            if(directory) {
                List<PilotDirectoryEntry> children=PilotEnumerateDirectory(handle,label,budget,r);
                foreach(PilotDirectoryEntry child in children) {
                    if((child.Attributes&0x440)!=0 || child.FileId==0)
                        throw new InvalidOperationException("pilot reparse or unsupported directory entry");
                    string childPath=PilotOwnedPath(Path.Combine(path,child.Name));
                    if(!String.Equals(Path.GetDirectoryName(childPath),path,StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("pilot child containment mismatch");
                    string childIdentity=volume+":"+(uint)(child.FileId>>32)+":"+(uint)child.FileId;
                    PilotDeleteEntry(childPath,(child.Attributes&0x10)!=0,childIdentity,volume,depth+1,budget,r);
                }
            }
            // Revalidate before mutating this exact handle, never a second path-based delete.
            PilotValidateObject(handle,path,directory,identity,volume);
            byte delete=1;bool removed=PilotSetDisposition(handle,4,ref delete,1);
            int error=removed?0:Marshal.GetLastWin32Error();r.Numbers[label+"_delete_error"]=error;
            if(!removed) throw new Win32Exception(error,"pilot exact owned object disposition");
        } finally {
            if(!PilotCloseHandle(ref handle,label,r)) throw new InvalidOperationException("pilot deletion handle close uncertain");
        }
    }
    // Call only after exact target stop, job drain, every process/preparation close,
    // no-follow capture and canary checks, and S_OK profile deletion. This helper
    // owns no journal and can neither authorize that gate nor resolve any marker.
    static bool RemovePilotOwnedScope(PilotOwnedScope scope,DirectReceipt r) {
        if(scope==null || scope.RemovalAttempted) throw new InvalidOperationException("pilot requires a current unused owned scope");
        scope.RemovalAttempted=true;r.Numbers["pilot_owned_root_removed"]=0;
        IntPtr parentHandle=IntPtr.Zero;bool valid=false,closed=true;
        var budget=new PilotCleanupBudget();
        try {
            PilotOpenHandle(ref parentHandle,scope.Parent,PilotReadDirectory,true,"pilot_remove_parent",r);
            PilotValidateParent(parentHandle,scope.Parent,scope.ParentIdentity,"pilot_remove_parent",r);
            PilotDeleteEntry(scope.Root,true,scope.RootIdentity,scope.Volume,0,budget,r);
            // Every deletion handle is closed before checking the name. Close and
            // reopen only the pre-recorded parent; never descend through the child.
            if(!PilotCloseHandle(ref parentHandle,"pilot_remove_parent",r))
                throw new InvalidOperationException("pilot deletion parent close uncertain");
            PilotOpenHandle(ref parentHandle,scope.Parent,PilotReadDirectory,true,"pilot_absence_parent",r);
            PilotValidateParent(parentHandle,scope.Parent,scope.ParentIdentity,"pilot_absence_parent",r);
            List<PilotDirectoryEntry> remaining=PilotEnumerateDirectory(parentHandle,"pilot_absence_parent",budget,r);
            foreach(PilotDirectoryEntry entry in remaining)
                if(String.Equals(entry.Name,scope.Leaf,StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("pilot root name still present after deletion");
            PilotValidateParent(parentHandle,scope.Parent,scope.ParentIdentity,"pilot_absence_parent_recheck",r);
            valid=true;
        } catch(Exception failure) {
            r.Identities["pilot_owned_cleanup_failure"]=failure.GetType().Name+": "+failure.Message;
        } finally {
            closed=PilotCloseHandle(ref parentHandle,"pilot_absence_parent",r);
            r.Numbers["pilot_cleanup_enumerated_records"]=budget.Entries;r.Numbers["pilot_cleanup_enumeration_calls"]=budget.Queries;
        }
        scope.RemovalConfirmed=valid && closed;
        r.Numbers["pilot_owned_root_removed"]=scope.RemovalConfirmed?1:0;
        return scope.RemovalConfirmed;
    }
}
