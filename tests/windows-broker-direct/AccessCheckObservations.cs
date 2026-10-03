// Test-only, observation-only authorization measurements against owned memory.
// No result here authorizes assignment, resume, or use of a token on a resource.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;

public static partial class BrokerDirectLauncher {
    const uint ACCESSCHECK_MAXIMUM_ALLOWED=0x02000000;
    const uint ACCESSCHECK_RAW_SENTINEL=0xA5A5A5A5;
    const int ACCESSCHECK_PRIVILEGE_BYTES=20;

    [StructLayout(LayoutKind.Sequential)] struct ACCESSCHECK_GENERIC_MAPPING {
        public uint GenericRead,GenericWrite,GenericExecute,GenericAll;
    }
    // Used to size and inspect an absolute descriptor. Native setters construct it.
    [StructLayout(LayoutKind.Sequential)] struct ACCESSCHECK_ABSOLUTE_DESCRIPTOR {
        public byte Revision,Reserved; public ushort Control;
        public IntPtr Owner,Group,Sacl,Dacl;
    }
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool DuplicateTokenEx(
        IntPtr existing,uint desiredAccess,IntPtr attributes,int level,int type,ref IntPtr duplicate);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool AccessCheck(
        IntPtr descriptor,IntPtr clientToken,uint desiredAccess,ref ACCESSCHECK_GENERIC_MAPPING mapping,
        IntPtr privileges,ref uint privilegeBytes,ref uint grantedAccess,ref int accessStatus);
    [DllImport("advapi32.dll")] static extern void MapGenericMask(ref uint mask,ref ACCESSCHECK_GENERIC_MAPPING mapping);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool InitializeSecurityDescriptor(IntPtr descriptor,uint revision);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetSecurityDescriptorOwner(IntPtr descriptor,IntPtr owner,bool defaulted);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetSecurityDescriptorGroup(IntPtr descriptor,IntPtr group,bool defaulted);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetSecurityDescriptorDacl(IntPtr descriptor,bool present,IntPtr dacl,bool defaulted);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool InitializeAcl(IntPtr acl,uint bytes,uint revision);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool AddAccessAllowedAceEx(IntPtr acl,uint revision,uint flags,uint mask,IntPtr sid);
    [DllImport("advapi32.dll")] static extern bool IsValidAcl(IntPtr acl);
    [DllImport("advapi32.dll")] static extern bool IsValidSecurityDescriptor(IntPtr descriptor);

    static bool FreeAccessCheckMemory(ref IntPtr memory,string label,DirectReceipt r) {
        if(memory==IntPtr.Zero) return true;
        IntPtr owned=memory;memory=IntPtr.Zero; // Never blindly retry an uncertain free.
        try {
            Marshal.FreeHGlobal(owned);r.Numbers[label+"_free_completed"]=1;return true;
        } catch(Exception failure) {
            r.Numbers[label+"_free_completed"]=0;r.Identities[label+"_free_exception"]=failure.GetType().Name;
            return false;
        }
    }
    static void AllocateAccessCheckMemory(ref IntPtr memory,byte[] bytes) {
        memory=Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes,0,memory,bytes.Length);
    }
    static byte[] AccessCheckSidBytes(string value) {
        var sid=new SecurityIdentifier(value);var bytes=new byte[sid.BinaryLength];
        sid.GetBinaryForm(bytes,0);return bytes;
    }
    // Unlike the existing inspection helpers, this records the cleanup of every
    // temporary allocation even if a query, conversion, or interpretation throws.
    static void ObserveAccessCheckTokenField(IntPtr token,int kind,string label,bool sidField,
        DirectReceipt r,ref bool cleanupCertain) {
        IntPtr data=IntPtr.Zero;
        r.Numbers[label+"_valid"]=0;
        try {
            uint size;bool initial=GetTokenInformation(token,kind,IntPtr.Zero,0,out size);
            int error=initial?0:Marshal.GetLastWin32Error();
            r.Numbers[label+"_size_call_success"]=initial?1:0;
            r.Numbers[label+"_size_error"]=error;r.Numbers[label+"_required_bytes"]=size;
            if(initial || error!=122 || size<4 || size>65536)
                throw new InvalidOperationException(label+" token sizing invalid");
            byte[] initialBytes=new byte[(int)size];
            for(int i=0;i<initialBytes.Length;i++) initialBytes[i]=0xA5;
            AllocateAccessCheckMemory(ref data,initialBytes);
            uint returned;bool success=GetTokenInformation(token,kind,data,size,out returned);
            error=success?0:Marshal.GetLastWin32Error();
            r.Numbers[label+"_query_success"]=success?1:0;
            r.Numbers[label+"_query_error"]=error;r.Numbers[label+"_returned_bytes"]=returned;
            if(!success || returned<4 || returned>size)
                throw new InvalidOperationException(label+" token query invalid");
            if(!sidField) {
                // TokenCapabilities is TOKEN_GROUPS; the other values are DWORDs.
                if(kind!=30 && returned!=4) throw new InvalidOperationException(label+" token DWORD size invalid");
                r.Numbers[label+"_value"]=Marshal.ReadInt32(data);
            } else {
                uint header=(uint)(kind==25?(IntPtr.Size==8?16:8):IntPtr.Size);
                if(returned<header) throw new InvalidOperationException(label+" token SID header invalid");
                IntPtr sid=Marshal.ReadIntPtr(data);
                ulong start=unchecked((ulong)data.ToInt64()),pointer=unchecked((ulong)sid.ToInt64());
                if(pointer<start || pointer-start<header || pointer-start>returned || returned-(pointer-start)<8)
                    throw new InvalidOperationException(label+" token SID pointer outside returned bytes");
                uint sidBytes=8u+4u*Marshal.ReadByte(sid,1);
                r.Numbers[label+"_sid_bytes"]=sidBytes;r.Numbers[label+"_sid_offset"]=(long)(pointer-start);
                if(sidBytes>returned-(pointer-start) || !IsValidSid(sid))
                    throw new InvalidOperationException(label+" token SID span invalid");
                r.Identities[label]=new SecurityIdentifier(sid).Value;
            }
            r.Numbers[label+"_valid"]=1;
        } finally {cleanupCertain=FreeAccessCheckMemory(ref data,label,r) && cleanupCertain;}
        if(!cleanupCertain) throw new InvalidOperationException("duplicate token observation memory cleanup uncertain");
    }
    static bool AccessCheckMappingIsZero(ACCESSCHECK_GENERIC_MAPPING mapping) {
        return mapping.GenericRead==0 && mapping.GenericWrite==0 && mapping.GenericExecute==0 && mapping.GenericAll==0;
    }
    static void ValidateAccessCheckSid(IntPtr pointer,byte[] expected,string identity) {
        if(pointer==IntPtr.Zero || expected.Length<8) throw new InvalidOperationException("synthetic SID absent");
        for(int i=0;i<expected.Length;i++) if(Marshal.ReadByte(pointer,i)!=expected[i])
            throw new InvalidOperationException("synthetic SID byte identity changed");
        if(8+4*Marshal.ReadByte(pointer,1)!=expected.Length || !IsValidSid(pointer) ||
            new SecurityIdentifier(pointer).Value!=identity) throw new InvalidOperationException("synthetic SID invalid");
    }
    static void ValidateAccessCheckDescriptor(IntPtr[] memory,int aclBytes,string[] sidNames,
        byte[][] sidBytes,uint[] masks,string label,DirectReceipt r) {
        var descriptor=(ACCESSCHECK_ABSOLUTE_DESCRIPTOR)Marshal.PtrToStructure(memory[6],typeof(ACCESSCHECK_ABSOLUTE_DESCRIPTOR));
        r.Numbers[label+"_sd_revision"]=descriptor.Revision;r.Numbers[label+"_sd_control"]=descriptor.Control;
        if(descriptor.Revision!=1 || descriptor.Reserved!=0 || descriptor.Control!=4 ||
            descriptor.Owner!=memory[0] || descriptor.Group!=memory[1] || descriptor.Sacl!=IntPtr.Zero ||
            descriptor.Dacl==IntPtr.Zero || descriptor.Dacl!=memory[5])
            throw new InvalidOperationException("synthetic descriptor is not the exact absolute non-NULL DACL descriptor");
        ValidateAccessCheckSid(descriptor.Owner,AccessCheckSidBytes("S-1-5-18"),"S-1-5-18");
        ValidateAccessCheckSid(descriptor.Group,AccessCheckSidBytes("S-1-5-18"),"S-1-5-18");
        r.Identities[label+"_owner_sid"]="S-1-5-18";r.Identities[label+"_group_sid"]="S-1-5-18";
        IntPtr acl=descriptor.Dacl;
        int observedBytes=(ushort)Marshal.ReadInt16(acl,2),count=(ushort)Marshal.ReadInt16(acl,4);
        r.Numbers[label+"_acl_bytes"]=observedBytes;r.Numbers[label+"_ace_count"]=count;
        if(Marshal.ReadByte(acl,0)!=2 || Marshal.ReadByte(acl,1)!=0 ||
            observedBytes!=aclBytes || count!=sidNames.Length || Marshal.ReadInt16(acl,6)!=0)
            throw new InvalidOperationException("synthetic ACL header changed");
        int offset=8;
        for(int i=0;i<count;i++) {
            if(offset>aclBytes-8) throw new InvalidOperationException("synthetic ACE header out of bounds");
            IntPtr ace=IntPtr.Add(acl,offset);
            int aceBytes=(ushort)Marshal.ReadInt16(ace,2);uint mask=unchecked((uint)Marshal.ReadInt32(ace,4));
            string aceLabel=label+"_ace_"+i;
            r.Numbers[aceLabel+"_type"]=Marshal.ReadByte(ace,0);r.Numbers[aceLabel+"_flags"]=Marshal.ReadByte(ace,1);
            r.Numbers[aceLabel+"_bytes"]=aceBytes;r.Numbers[aceLabel+"_mask"]=mask;
            if(Marshal.ReadByte(ace,0)!=0 || Marshal.ReadByte(ace,1)!=0 || aceBytes!=8+sidBytes[i].Length ||
                (aceBytes&3)!=0 || aceBytes>aclBytes-offset || mask!=masks[i] || (mask&~3u)!=0)
                throw new InvalidOperationException("synthetic allow ACE type/order/mask/span changed");
            ValidateAccessCheckSid(IntPtr.Add(ace,8),sidBytes[i],sidNames[i]);
            r.Identities[aceLabel+"_sid"]=sidNames[i];offset=checked(offset+aceBytes);
        }
        if(offset!=aclBytes || !IsValidAcl(acl) || !IsValidSecurityDescriptor(memory[6]))
            throw new InvalidOperationException("synthetic descriptor validation failed");
        r.Numbers[label+"_sacl_present"]=0;r.Numbers[label+"_dacl_present"]=1;
        r.Numbers[label+"_descriptor_valid"]=1;
    }
    // One of four fixed descriptors, one AccessCheck call, and no buffer-size retry.
    // Completion is observation completion; cleanup certainty is returned separately.
    static bool ObserveAccessCheckDescriptor(IntPtr duplicate,string name,DirectReceipt r,ref bool cleanupCertain) {
        string label="accesscheck_"+name;
        IntPtr[] memory=new IntPtr[8];
        r.Numbers[label+"_descriptor_valid"]=0;r.Numbers[label+"_decision_valid"]=0;
        r.Numbers[label+"_api_called"]=0;r.Numbers[label+"_api_success"]=-1;
        r.Numbers[label+"_access_status_raw"]=-1;r.Numbers[label+"_granted_access_raw"]=ACCESSCHECK_RAW_SENTINEL;
        r.Numbers[label+"_privilege_count_raw"]=-1;r.Numbers[label+"_privilege_header_valid"]=0;
        r.Numbers[label+"_error"]=-1;r.Numbers[label+"_error_available"]=0;
        r.Identities[label+"_interpreted_decision"]="unknown";
        bool completed=false;
        try {
            string[] sids;uint[] masks;
            switch(name) {
                case "mixed": sids=new string[]{"S-1-1-0","S-1-15-2-1","S-1-15-2-2"};masks=new uint[]{3,1,2};break;
                case "aap": sids=new string[]{"S-1-1-0","S-1-15-2-1"};masks=new uint[]{1,1};break;
                case "arap": sids=new string[]{"S-1-1-0","S-1-15-2-2"};masks=new uint[]{2,2};break;
                case "world": sids=new string[]{"S-1-1-0"};masks=new uint[]{3};break;
                default: throw new ArgumentException("fixed synthetic descriptor required");
            }
            r.Identities[label+"_descriptor_identity"]="absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;"+name;
            AllocateAccessCheckMemory(ref memory[0],AccessCheckSidBytes("S-1-5-18"));
            AllocateAccessCheckMemory(ref memory[1],AccessCheckSidBytes("S-1-5-18"));
            byte[][] sidBytes=new byte[sids.Length][];int aclBytes=8;
            for(int i=0;i<sids.Length;i++) {
                sidBytes[i]=AccessCheckSidBytes(sids[i]);aclBytes=checked(aclBytes+8+sidBytes[i].Length);
                AllocateAccessCheckMemory(ref memory[2+i],sidBytes[i]);
            }
            if(aclBytes<28 || aclBytes>76) throw new InvalidOperationException("fixed synthetic ACL size exceeded");
            AllocateAccessCheckMemory(ref memory[5],new byte[aclBytes]);
            Check(InitializeAcl(memory[5],(uint)aclBytes,2),"synthetic ACL initialization");
            for(int i=0;i<sids.Length;i++)
                Check(AddAccessAllowedAceEx(memory[5],2,0,masks[i],memory[2+i]),"synthetic allow ACE construction");
            int descriptorBytes=Marshal.SizeOf(typeof(ACCESSCHECK_ABSOLUTE_DESCRIPTOR));
            if(descriptorBytes!=(IntPtr.Size==8?40:20)) throw new InvalidOperationException("absolute descriptor ABI mismatch");
            AllocateAccessCheckMemory(ref memory[6],new byte[descriptorBytes]);
            Check(InitializeSecurityDescriptor(memory[6],1),"absolute synthetic descriptor initialization");
            Check(SetSecurityDescriptorOwner(memory[6],memory[0],false),"synthetic descriptor owner");
            Check(SetSecurityDescriptorGroup(memory[6],memory[1],false),"synthetic descriptor group");
            Check(SetSecurityDescriptorDacl(memory[6],true,memory[5],false),"synthetic descriptor non-NULL DACL");
            ValidateAccessCheckDescriptor(memory,aclBytes,sids,sidBytes,masks,label,r);

            var mapping=new ACCESSCHECK_GENERIC_MAPPING();
            mapping.GenericRead=0;mapping.GenericWrite=0;mapping.GenericExecute=0;mapping.GenericAll=0;
            uint desired=ACCESSCHECK_MAXIMUM_ALLOWED;
            r.Numbers[label+"_desired_access_before_mapping"]=desired;
            MapGenericMask(ref desired,ref mapping);
            r.Numbers[label+"_desired_access_after_mapping"]=desired;
            r.Numbers[label+"_mapping_read"]=mapping.GenericRead;r.Numbers[label+"_mapping_write"]=mapping.GenericWrite;
            r.Numbers[label+"_mapping_execute"]=mapping.GenericExecute;r.Numbers[label+"_mapping_all"]=mapping.GenericAll;
            if(desired!=ACCESSCHECK_MAXIMUM_ALLOWED || !AccessCheckMappingIsZero(mapping))
                throw new InvalidOperationException("synthetic mapping changed fixed maximum access mask");

            byte[] privilegeInitial=new byte[ACCESSCHECK_PRIVILEGE_BYTES];
            for(int i=0;i<privilegeInitial.Length;i++) privilegeInitial[i]=0xA5;
            AllocateAccessCheckMemory(ref memory[7],privilegeInitial);
            uint privilegeBytes=ACCESSCHECK_PRIVILEGE_BYTES,granted=ACCESSCHECK_RAW_SENTINEL;
            int accessStatus=-1;
            r.Numbers[label+"_privilege_allocation_bytes"]=ACCESSCHECK_PRIVILEGE_BYTES;
            r.Numbers[label+"_privilege_initial_count"]=ACCESSCHECK_RAW_SENTINEL;
            r.Numbers[label+"_api_called"]=1;r.Numbers["accesscheck_call_attempts"]++;
            bool success=AccessCheck(memory[6],duplicate,desired,ref mapping,memory[7],ref privilegeBytes,ref granted,ref accessStatus);
            // Capture before logging/parsing. Allowed decisions have no last-error claim.
            int? error=(!success || accessStatus==0)?(int?)Marshal.GetLastWin32Error():null;
            r.Numbers[label+"_api_success"]=success?1:0;r.Numbers[label+"_access_status_raw"]=accessStatus;
            r.Numbers[label+"_granted_access_raw"]=granted;r.Numbers[label+"_privilege_returned_bytes"]=privilegeBytes;
            if(error.HasValue) {r.Numbers[label+"_error"]=error.Value;r.Numbers[label+"_error_available"]=1;}
            uint? privilegeCount=null;bool privilegeHeaderValid=false;
            if(privilegeBytes>=8 && privilegeBytes<=ACCESSCHECK_PRIVILEGE_BYTES) {
                privilegeCount=unchecked((uint)Marshal.ReadInt32(memory[7],0));
                r.Numbers[label+"_privilege_count_raw"]=privilegeCount.Value;
                r.Numbers[label+"_privilege_control_raw"]=unchecked((uint)Marshal.ReadInt32(memory[7],4));
                long span=checked(8L+12L*privilegeCount.Value);
                r.Numbers[label+"_privilege_entry_span_bytes"]=span;
                privilegeHeaderValid=span<=privilegeBytes;
                // At most one entry fits this fixed allocation; never parse outside returned bytes.
                if(privilegeHeaderValid && privilegeCount.Value==1) {
                    r.Numbers[label+"_privilege_luid_low_raw"]=unchecked((uint)Marshal.ReadInt32(memory[7],8));
                    r.Numbers[label+"_privilege_luid_high_raw"]=Marshal.ReadInt32(memory[7],12);
                    r.Numbers[label+"_privilege_attributes_raw"]=unchecked((uint)Marshal.ReadInt32(memory[7],16));
                }
            }
            r.Numbers[label+"_privilege_header_valid"]=privilegeHeaderValid?1:0;
            bool decisionValid=success && privilegeHeaderValid && privilegeCount.HasValue && privilegeCount.Value==0 &&
                (accessStatus==0 || accessStatus==1) && granted!=ACCESSCHECK_RAW_SENTINEL &&
                (accessStatus!=0 || granted==0) && AccessCheckMappingIsZero(mapping) &&
                r.Numbers[label+"_descriptor_valid"]==1 && r.Numbers["duplicate_valid"]==1;
            r.Numbers[label+"_decision_valid"]=decisionValid?1:0;
            if(decisionValid) {
                r.Identities[label+"_interpreted_decision"]=accessStatus==1?"allowed":"denied";
                r.Numbers[label+"_interpreted_granted_access"]=granted;
            }
            completed=true;
        } catch(Exception failure) {
            r.Identities[label+"_exception"]=failure.GetType().Name+": "+failure.Message;
            r.Numbers[label+"_decision_valid"]=0;r.Identities[label+"_interpreted_decision"]="unknown";
        } finally {
            // All eight slots are visited even if another free is uncertain.
            for(int i=memory.Length-1;i>=0;i--)
                cleanupCertain=FreeAccessCheckMemory(ref memory[i],label+"_memory_"+i,r) && cleanupCertain;
        }
        r.Numbers[label+"_observation_completed"]=completed?1:0;
        return completed;
    }
    // The caller owns sourceToken, opened QUERY|DUPLICATE on its newly created,
    // still-suspended target after primary/AppContainer/SID/capability/IL checks.
    // This return value means ONLY temporary-handle/memory cleanup certainty.
    static bool ObserveAccessCheckToken(IntPtr sourceToken,string packageSid,DirectReceipt receipt) {
        DirectReceipt r=receipt;IntPtr duplicate=IntPtr.Zero;bool cleanupCertain=true,duplicateOwned=false;
        r.Numbers["duplicate_valid"]=0;r.Numbers["accesscheck_observer_completed"]=0;
        r.Numbers["duplicate_ownership_confirmed"]=0;
        r.Numbers["accesscheck_call_attempts"]=0;r.Numbers["accesscheck_observer_cleanup_confirmed"]=0;
        r.Numbers["duplicate_desired_access"]=0x0008;r.Numbers["duplicate_attributes_null"]=1;
        r.Numbers["duplicate_requested_level"]=1;r.Numbers["duplicate_requested_type"]=2;
        try {
            if(sourceToken==IntPtr.Zero || sourceToken==new IntPtr(-1) || String.IsNullOrEmpty(packageSid))
                throw new ArgumentException("caller-owned suspended source token and package SID required");
            bool duplicated=DuplicateTokenEx(sourceToken,0x0008,IntPtr.Zero,1,2,ref duplicate);
            int error=duplicated?0:Marshal.GetLastWin32Error();
            duplicateOwned=duplicated && duplicate!=IntPtr.Zero && duplicate!=new IntPtr(-1) && duplicate!=sourceToken;
            if(duplicated && !duplicateOwned) cleanupCertain=false;
            r.Numbers["duplicate_api_success"]=duplicated?1:0;r.Numbers["duplicate_error"]=error;
            if(!duplicated) {
                if(duplicate!=IntPtr.Zero) {
                    // A failed API does not establish ownership of its output.
                    // It could be stale or foreign: never try closing that value.
                    r.Numbers["duplicate_failed_nonzero_output"]=1;
                    duplicate=IntPtr.Zero;cleanupCertain=false;
                }
                throw new InvalidOperationException("identification query-only duplication failed");
            }
            if(duplicate==sourceToken) {
                // A malformed result must never consume the caller's source ownership.
                duplicate=IntPtr.Zero;cleanupCertain=false;
                throw new InvalidOperationException("duplicate unexpectedly aliases caller-owned source token");
            }
            if(duplicate==IntPtr.Zero || duplicate==new IntPtr(-1)) {
                duplicate=IntPtr.Zero;cleanupCertain=false;
                throw new InvalidOperationException("identification query-only duplicate unavailable");
            }
            r.Numbers["duplicate_ownership_confirmed"]=1;
            uint flags;bool flagsRead=GetHandleInformation(duplicate,out flags);
            error=flagsRead?0:Marshal.GetLastWin32Error();
            r.Numbers["duplicate_handle_flags_success"]=flagsRead?1:0;r.Numbers["duplicate_handle_flags_error"]=error;
            r.Numbers["duplicate_handle_flags"]=flags;
            if(!flagsRead || (flags&1)!=0) throw new InvalidOperationException("duplicate noninheritance unverified");
            ObserveAccessCheckTokenField(duplicate,8,"duplicate_type",false,r,ref cleanupCertain);
            ObserveAccessCheckTokenField(duplicate,9,"duplicate_level",false,r,ref cleanupCertain);
            ObserveAccessCheckTokenField(duplicate,29,"duplicate_appcontainer",false,r,ref cleanupCertain);
            ObserveAccessCheckTokenField(duplicate,30,"duplicate_capabilities",false,r,ref cleanupCertain);
            ObserveAccessCheckTokenField(duplicate,31,"duplicate_appcontainer_sid",true,r,ref cleanupCertain);
            ObserveAccessCheckTokenField(duplicate,25,"duplicate_integrity_sid",true,r,ref cleanupCertain);
            if(!cleanupCertain || r.Numbers["duplicate_type_value"]!=2 || r.Numbers["duplicate_level_value"]!=1 ||
                r.Numbers["duplicate_appcontainer_value"]!=1 || r.Numbers["duplicate_capabilities_value"]!=0 ||
                r.Identities["duplicate_appcontainer_sid"]!=packageSid || r.Identities["duplicate_integrity_sid"]!="S-1-16-4096")
                throw new InvalidOperationException("duplicate restricted-token properties unverified");
            r.Numbers["duplicate_valid"]=1;
            bool allCompleted=true;
            foreach(string name in new string[]{"mixed","aap","arap","world"}) {
                allCompleted=ObserveAccessCheckDescriptor(duplicate,name,r,ref cleanupCertain) && allCompleted;
                if(!cleanupCertain) break;
            }
            r.Numbers["accesscheck_observer_completed"]=allCompleted && cleanupCertain && r.Numbers["accesscheck_call_attempts"]==4?1:0;
        } catch(Exception failure) {
            r.Numbers["accesscheck_observer_completed"]=0;
            r.Identities["accesscheck_observer_exception"]=failure.GetType().Name+": "+failure.Message;
        } finally {
            try {
                if(duplicate!=IntPtr.Zero && !duplicateOwned) {
                    duplicate=IntPtr.Zero;cleanupCertain=false;
                    r.Identities["duplicate_close_exception"]="unconfirmed duplicate output; not closed";
                } else cleanupCertain=CloseOwned(ref duplicate,"duplicate",r) && cleanupCertain;
            } catch(Exception failure) {
                duplicate=IntPtr.Zero;cleanupCertain=false;
                r.Identities["duplicate_close_exception"]=failure.GetType().Name;
            }
            r.Numbers["accesscheck_observer_cleanup_confirmed"]=cleanupCertain?1:0;
        }
        return cleanupCertain;
    }
}
