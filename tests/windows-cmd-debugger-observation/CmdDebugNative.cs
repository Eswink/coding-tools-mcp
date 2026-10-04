// Test-only AMD64 observer ABI, exact native adapter and bounded remote-image parser.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static partial class BrokerDirectLauncher {
    struct CmdOriginalProcess { public readonly IntPtr Value; public CmdOriginalProcess(IntPtr value) { Value=value; } }
    struct CmdOriginalThread { public readonly IntPtr Value; public CmdOriginalThread(IntPtr value) { Value=value; } }
    struct CmdBorrowedProcess { public readonly IntPtr Value; public CmdBorrowedProcess(IntPtr value) { Value=value; } }
    struct CmdBorrowedThread {
        public readonly IntPtr Value; public readonly uint Tid; public readonly long Generation;
        public CmdBorrowedThread(IntPtr value,uint tid,long generation) { Value=value;Tid=tid;Generation=generation; }
    }
    struct CmdImageFile { public readonly IntPtr Value; public CmdImageFile(IntPtr value) { Value=value; } }
    struct CmdDuplicate { public readonly IntPtr Value; public CmdDuplicate(IntPtr value) { Value=value; } }
    struct CmdFileIdentity { public uint Attributes,Volume,High,Low; }
    sealed class CmdDebugEvent {
        public uint Code,Pid,Tid,ExceptionCode,ExceptionFlags,FirstChance,ExitCode;
        public ulong Address,Base;
        public IntPtr File,Process,Thread;
    }
    sealed class CmdDebugFault:Exception {
        public readonly string Code,Api; public readonly int NativeError;
        public CmdDebugFault(string code,string api,int error):base("cmd debug observation failed") {
            Code=code;Api=api;NativeError=error;
        }
    }
    static ushort CmdU16(byte[] bytes,int offset) { return BitConverter.ToUInt16(bytes,offset); }
    static uint CmdU32(byte[] bytes,int offset) { return BitConverter.ToUInt32(bytes,offset); }
    static ulong CmdU64(byte[] bytes,int offset) { return BitConverter.ToUInt64(bytes,offset); }
    sealed class CmdDebugContext {
        public readonly byte[] Raw;
        public CmdDebugContext() { Raw=new byte[1232];Put32(48,0x00100003); }
        public CmdDebugContext(byte[] bytes) {
            if(bytes==null || bytes.Length!=1232) throw new CmdDebugFault("context_failed","none",0);
            Raw=(byte[])bytes.Clone();
        }
        public uint U32(int offset) { return CmdU32(Raw,offset); }
        public ulong U64(int offset) { return CmdU64(Raw,offset); }
        void Put32(int offset,uint value) { Array.Copy(BitConverter.GetBytes(value),0,Raw,offset,4); }
        void Put64(int offset,ulong value) { Array.Copy(BitConverter.GetBytes(value),0,Raw,offset,8); }
        public CmdDebugContext Copy() { return new CmdDebugContext(Raw); }
        public CmdDebugContext WithRipTf(ulong rip,bool tf) {
            var result=Copy();result.Put64(248,rip);
            result.Put32(68,tf?U32(68)|0x100U:U32(68)&~0x100U);return result;
        }
        public bool SameRequested(CmdDebugContext other) {
            if(other==null || U32(48)!=0x00100003 || other.U32(48)!=0x00100003 ||
                CmdU16(Raw,56)!=CmdU16(other.Raw,56) || CmdU16(Raw,66)!=CmdU16(other.Raw,66) || U32(68)!=other.U32(68)) return false;
            for(int offset=120;offset<=248;offset+=8) if(U64(offset)!=other.U64(offset)) return false;
            return true;
        }
        public long RequestedMismatchMask(CmdDebugContext other) {
            if(other==null) return -1;
            long mask=0;
            if(U32(48)!=0x00100003 || other.U32(48)!=0x00100003) mask|=1L;
            if(CmdU16(Raw,56)!=CmdU16(other.Raw,56)) mask|=1L<<1;
            if(CmdU16(Raw,66)!=CmdU16(other.Raw,66)) mask|=1L<<2;
            if(U32(68)!=other.U32(68)) mask|=1L<<3;
            for(int offset=120;offset<=248;offset+=8)
                if(U64(offset)!=other.U64(offset)) mask|=1L<<(4+(offset-120)/8);
            return mask;
        }
        public bool MatchesAfterMov(CmdDebugContext before) {
            var expected=before.WithRipTf(CmdRemoteReader.Add(before.U64(248),2),(U32(68)&0x100)!=0);
            expected.Put64(200,before.U64(128));return SameRequested(expected);
        }
    }
    abstract class CmdDebugApi {
        public int Error { get; protected set; }
        public abstract long NowMilliseconds { get; }
        public virtual int PointerSize { get { return IntPtr.Size; } }
        public abstract uint ProcessId(CmdOriginalProcess process);
        public abstract bool ProcessTimes(CmdOriginalProcess process,out ulong creation);
        public abstract bool Machines(CmdOriginalProcess process,out ushort machine,out ushort native);
        public abstract bool SystemDirectory(out string path);
        public abstract bool Attach(uint pid);
        public abstract bool Wait(uint milliseconds,out CmdDebugEvent value);
        public abstract bool Continue(CmdDebugEvent value,uint disposition);
        public abstract bool Read(CmdOriginalProcess process,ulong address,byte[] bytes,out ulong count);
        public abstract bool WriteByte(CmdOriginalProcess process,ulong address,byte value,out ulong count);
        public abstract bool FlushByte(CmdOriginalProcess process,ulong address);
        public abstract bool GetContext(CmdBorrowedThread thread,out CmdDebugContext context);
        public abstract bool SetContext(CmdBorrowedThread thread,CmdDebugContext context);
        public abstract uint Suspend(CmdBorrowedThread thread);
        public abstract uint ResumePeer(CmdBorrowedThread thread);
        public abstract uint ResumeMain(CmdOriginalThread thread);
        public abstract bool ImagePath(CmdImageFile file,out string path);
        public abstract bool Duplicate(CmdOriginalProcess process,ulong target,out CmdDuplicate duplicate);
        public abstract bool FileInfo(CmdDuplicate file,out CmdFileIdentity identity);
        public abstract bool CloseImage(CmdImageFile file);
        public abstract bool CloseDuplicate(CmdDuplicate file);
        public abstract uint WaitProcess(CmdOriginalProcess process,uint milliseconds);
        public abstract bool ExitCode(CmdOriginalProcess process,out uint exit);
        public abstract bool Terminate(CmdOriginalProcess process);
    }
    // Allocations own broker memory only, never a process, thread or file handle.
    sealed class CmdContextBuffer:IDisposable {
        IntPtr allocation; public readonly IntPtr Aligned;
        public CmdContextBuffer() {
            allocation=Marshal.AllocHGlobal(1232+15);
            Aligned=new IntPtr(checked((allocation.ToInt64()+15)&~15L));
        }
        public void Dispose() { if(allocation!=IntPtr.Zero) { Marshal.FreeHGlobal(allocation);allocation=IntPtr.Zero; } }
    }
    [StructLayout(LayoutKind.Explicit,Size=1232)] struct CmdContextLayout {
        [FieldOffset(48)] public uint Flags; [FieldOffset(56)] public ushort Cs;
        [FieldOffset(66)] public ushort Ss; [FieldOffset(68)] public uint EFlags;
        [FieldOffset(120)] public ulong Rax; [FieldOffset(128)] public ulong Rcx;
        [FieldOffset(136)] public ulong Rdx; [FieldOffset(144)] public ulong Rbx;
        [FieldOffset(152)] public ulong Rsp; [FieldOffset(160)] public ulong Rbp;
        [FieldOffset(168)] public ulong Rsi; [FieldOffset(176)] public ulong Rdi;
        [FieldOffset(184)] public ulong R8; [FieldOffset(192)] public ulong R9;
        [FieldOffset(200)] public ulong R10; [FieldOffset(208)] public ulong R11;
        [FieldOffset(216)] public ulong R12; [FieldOffset(224)] public ulong R13;
        [FieldOffset(232)] public ulong R14; [FieldOffset(240)] public ulong R15;
        [FieldOffset(248)] public ulong Rip;
    }
    [StructLayout(LayoutKind.Explicit,Size=176)] struct CmdEventLayout {
        [FieldOffset(0)] public uint Code; [FieldOffset(4)] public uint Pid; [FieldOffset(8)] public uint Tid;
        [FieldOffset(16)] public uint ExceptionCode; [FieldOffset(20)] public uint ExceptionFlags;
        [FieldOffset(24)] public ulong ExceptionRecord; [FieldOffset(32)] public ulong ExceptionAddress;
        [FieldOffset(40)] public uint ParameterCount; [FieldOffset(168)] public uint FirstChance;
        [FieldOffset(16)] public IntPtr File; [FieldOffset(24)] public IntPtr Process; [FieldOffset(32)] public IntPtr Thread;
        [FieldOffset(40)] public ulong CreateBase; [FieldOffset(48)] public uint CreateDebugOffset;
        [FieldOffset(52)] public uint CreateDebugSize; [FieldOffset(56)] public ulong CreateLocalBase;
        [FieldOffset(64)] public ulong CreateStart; [FieldOffset(72)] public ulong CreateImageName;
        [FieldOffset(80)] public ushort CreateUnicode; [FieldOffset(16)] public IntPtr NewThread;
        [FieldOffset(24)] public ulong ThreadLocalBase; [FieldOffset(32)] public ulong ThreadStart;
        [FieldOffset(24)] public ulong LoadBase; [FieldOffset(32)] public uint LoadDebugOffset;
        [FieldOffset(36)] public uint LoadDebugSize; [FieldOffset(40)] public ulong LoadImageName;
        [FieldOffset(48)] public ushort LoadUnicode; [FieldOffset(16)] public uint Exit;
        [FieldOffset(16)] public ulong UnloadBase; [FieldOffset(16)] public uint RipError; [FieldOffset(20)] public uint RipType;
    }
    [StructLayout(LayoutKind.Explicit,Size=48)] struct CmdObjectAttributesLayout {
        [FieldOffset(0)] public uint Length; [FieldOffset(8)] public ulong Root; [FieldOffset(16)] public ulong Name;
        [FieldOffset(24)] public uint Attributes; [FieldOffset(32)] public ulong Security; [FieldOffset(40)] public ulong Quality;
    }
    [StructLayout(LayoutKind.Explicit,Size=16)] struct CmdUnicodeLayout {
        [FieldOffset(0)] public ushort Length; [FieldOffset(2)] public ushort Maximum; [FieldOffset(8)] public ulong Buffer;
    }
    [StructLayout(LayoutKind.Sequential)] struct CmdFileTime { public uint Low,High; }
    [StructLayout(LayoutKind.Sequential)] struct CmdFileInfoLayout {
        public uint Attributes,CreationLow,CreationHigh,AccessLow,AccessHigh,WriteLow,WriteHigh;
        public uint Volume,SizeHigh,SizeLow,Links,High,Low;
    }
    sealed class CmdDebugNative:CmdDebugApi {
        readonly Stopwatch clock=Stopwatch.StartNew();
        public override long NowMilliseconds { get { return clock.ElapsedMilliseconds; } }
        bool Result(bool ok) { Error=ok?0:Marshal.GetLastWin32Error();return ok; }
        uint Count(uint count) { Error=count==UInt32.MaxValue?Marshal.GetLastWin32Error():0;return count; }
        static IntPtr Pointer(ulong value) { return new IntPtr(unchecked((long)value)); }
        static void Layout(Type type,int size,string[] names,int[] offsets) {
            if(Marshal.SizeOf(type)!=size || names.Length!=offsets.Length) throw new CmdDebugFault("abi_unsupported","none",0);
            for(int i=0;i<names.Length;i++) if(Marshal.OffsetOf(type,names[i]).ToInt32()!=offsets[i])
                throw new CmdDebugFault("abi_unsupported","none",0);
        }
        public static void AssertAbi() {
            if(IntPtr.Size!=8 || !BitConverter.IsLittleEndian) throw new CmdDebugFault("abi_unsupported","none",0);
            Layout(typeof(CmdContextLayout),1232,new string[]{"Flags","Cs","Ss","EFlags","Rax","Rcx","Rdx","Rbx",
                "Rsp","Rbp","Rsi","Rdi","R8","R9","R10","R11","R12","R13","R14","R15","Rip"},
                new int[]{48,56,66,68,120,128,136,144,152,160,168,176,184,192,200,208,216,224,232,240,248});
            Layout(typeof(CmdEventLayout),176,new string[]{"Code","Pid","Tid","ExceptionCode","ExceptionFlags","ExceptionRecord","ExceptionAddress","ParameterCount","FirstChance",
                "File","Process","Thread","CreateBase","CreateDebugOffset","CreateDebugSize","CreateLocalBase","CreateStart","CreateImageName","CreateUnicode",
                "NewThread","ThreadLocalBase","ThreadStart","LoadBase","LoadDebugOffset","LoadDebugSize","LoadImageName","LoadUnicode","Exit","UnloadBase","RipError","RipType"},
                new int[]{0,4,8,16,20,24,32,40,168,16,24,32,40,48,52,56,64,72,80,16,24,32,24,32,36,40,48,16,16,16,20});
            Layout(typeof(CmdObjectAttributesLayout),48,new string[]{"Length","Root","Name","Attributes","Security","Quality"},new int[]{0,8,16,24,32,40});
            Layout(typeof(CmdUnicodeLayout),16,new string[]{"Length","Maximum","Buffer"},new int[]{0,2,8});
            Layout(typeof(CmdFileTime),8,new string[]{"Low","High"},new int[]{0,4});
            Layout(typeof(CmdFileInfoLayout),52,new string[]{"Attributes","CreationLow","CreationHigh","AccessLow","AccessHigh",
                "WriteLow","WriteHigh","Volume","SizeHigh","SizeLow","Links","High","Low"},new int[]{0,4,8,12,16,20,24,28,32,36,40,44,48});
            using(var buffer=new CmdContextBuffer()) if((buffer.Aligned.ToInt64()&15)!=0) throw new CmdDebugFault("abi_unsupported","none",0);
        }
        public override uint ProcessId(CmdOriginalProcess process) {
            uint pid=GetProcessId(process.Value);Error=pid==0?Marshal.GetLastWin32Error():0;return pid;
        }
        public override bool ProcessTimes(CmdOriginalProcess process,out ulong creation) {
            CmdFileTime created,exit,kernel,user;bool ok=Result(GetProcessTimes(process.Value,out created,out exit,out kernel,out user));
            creation=ok?((ulong)created.High<<32)|created.Low:0;return ok;
        }
        public override bool Machines(CmdOriginalProcess process,out ushort machine,out ushort native) {
            return Result(IsWow64Process2(process.Value,out machine,out native));
        }
        public override bool SystemDirectory(out string path) {
            var buffer=new StringBuilder(2048);uint length=GetSystemDirectoryW(buffer,2048);Error=length==0?Marshal.GetLastWin32Error():0;
            bool ok=length>0 && length<2048;path=ok?buffer.ToString():null;return ok;
        }
        public override bool Attach(uint pid) { return Result(DebugActiveProcess(pid)); }
        public override bool Wait(uint milliseconds,out CmdDebugEvent value) {
            CmdEventLayout raw;bool ok=Result(WaitForDebugEvent(out raw,milliseconds));value=null;if(!ok) return false;
            value=new CmdDebugEvent();value.Code=raw.Code;value.Pid=raw.Pid;value.Tid=raw.Tid;
            if(raw.Code==1) { value.ExceptionCode=raw.ExceptionCode;value.ExceptionFlags=raw.ExceptionFlags;value.Address=raw.ExceptionAddress;value.FirstChance=raw.FirstChance; }
            if(raw.Code==2) value.Thread=raw.NewThread;
            if(raw.Code==3) { value.File=raw.File;value.Process=raw.Process;value.Thread=raw.Thread;value.Base=raw.CreateBase; }
            if(raw.Code==4 || raw.Code==5) value.ExitCode=raw.Exit;
            if(raw.Code==6) { value.File=raw.File;value.Base=raw.LoadBase; }
            if(raw.Code==7) value.Base=raw.UnloadBase;
            return true;
        }
        public override bool Continue(CmdDebugEvent value,uint disposition) { return Result(ContinueDebugEvent(value.Pid,value.Tid,disposition)); }
        public override bool Read(CmdOriginalProcess process,ulong address,byte[] bytes,out ulong count) {
            UIntPtr actual;
            bool ok=Result(ReadProcessMemory(process.Value,Pointer(address),bytes,new UIntPtr((uint)bytes.Length),out actual));
            count=actual.ToUInt64();return ok;
        }
        public override bool WriteByte(CmdOriginalProcess process,ulong address,byte value,out ulong count) {
            UIntPtr actual;bool ok=Result(WriteProcessMemory(process.Value,Pointer(address),new byte[]{value},(UIntPtr)1,out actual));count=actual.ToUInt64();return ok;
        }
        public override bool FlushByte(CmdOriginalProcess process,ulong address) { return Result(FlushInstructionCache(process.Value,Pointer(address),(UIntPtr)1)); }
        public override bool GetContext(CmdBorrowedThread thread,out CmdDebugContext context) {
            context=null;var initial=new CmdDebugContext();
            using(var buffer=new CmdContextBuffer()) {
                Marshal.Copy(initial.Raw,0,buffer.Aligned,1232);
                if(!Result(GetThreadContext(thread.Value,buffer.Aligned))) return false;
                Marshal.Copy(buffer.Aligned,initial.Raw,0,1232);context=initial;return true;
            }
        }
        public override bool SetContext(CmdBorrowedThread thread,CmdDebugContext context) {
            if(context.U32(48)!=0x00100003) throw new CmdDebugFault("context_failed","SetThreadContext",0);
            using(var buffer=new CmdContextBuffer()) {
                Marshal.Copy(context.Raw,0,buffer.Aligned,1232);return Result(SetThreadContext(thread.Value,buffer.Aligned));
            }
        }
        public override uint Suspend(CmdBorrowedThread thread) { return Count(SuspendThread(thread.Value)); }
        public override uint ResumePeer(CmdBorrowedThread thread) { return Count(ResumeThread(thread.Value)); }
        public override uint ResumeMain(CmdOriginalThread thread) { return Count(ResumeThread(thread.Value)); }
        public override bool ImagePath(CmdImageFile file,out string path) {
            var buffer=new StringBuilder(2048);uint length=GetFinalPathNameByHandleW(file.Value,buffer,2048,0);Error=length==0?Marshal.GetLastWin32Error():0;
            bool ok=length>0 && length<2048;path=ok?buffer.ToString():null;return ok;
        }
        public override bool Duplicate(CmdOriginalProcess process,ulong target,out CmdDuplicate duplicate) {
            IntPtr output;bool ok=Result(DuplicateHandle(process.Value,Pointer(target),GetCurrentProcess(),out output,0,false,2));
            // The session must reject protected broker-table aliases before adopting this candidate.
            duplicate=ok?new CmdDuplicate(output):default(CmdDuplicate);return ok;
        }
        public override bool FileInfo(CmdDuplicate file,out CmdFileIdentity identity) {
            CmdFileInfoLayout raw;bool ok=Result(GetFileInformationByHandle(file.Value,out raw));identity=new CmdFileIdentity();
            if(ok) { identity.Attributes=raw.Attributes;identity.Volume=raw.Volume;identity.High=raw.High;identity.Low=raw.Low; }return ok;
        }
        public override bool CloseImage(CmdImageFile file) { return Result(CloseHandle(file.Value)); }
        public override bool CloseDuplicate(CmdDuplicate file) { return Result(CloseHandle(file.Value)); }
        public override uint WaitProcess(CmdOriginalProcess process,uint milliseconds) { return Count(WaitForSingleObject(process.Value,milliseconds)); }
        public override bool ExitCode(CmdOriginalProcess process,out uint exit) { return Result(GetExitCodeProcess(process.Value,out exit)); }
        public override bool Terminate(CmdOriginalProcess process) { return Result(TerminateProcess(process.Value,91)); }
        // All BOOL returns are explicitly four-byte Win32 BOOL; SIZE_T is UIntPtr.
        [DllImport("kernel32.dll",EntryPoint="GetProcessId",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint GetProcessId(IntPtr process);
        [DllImport("kernel32.dll",EntryPoint="GetProcessTimes",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetProcessTimes(IntPtr process,out CmdFileTime creation,out CmdFileTime exit,out CmdFileTime kernel,out CmdFileTime user);
        [DllImport("kernel32.dll",EntryPoint="IsWow64Process2",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool IsWow64Process2(IntPtr process,out ushort machine,out ushort native);
        [DllImport("kernel32.dll",EntryPoint="GetSystemDirectoryW",ExactSpelling=true,CharSet=CharSet.Unicode,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint GetSystemDirectoryW(StringBuilder buffer,uint size);
        [DllImport("kernel32.dll",EntryPoint="DebugActiveProcess",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool DebugActiveProcess(uint pid);
        [DllImport("kernel32.dll",EntryPoint="WaitForDebugEvent",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool WaitForDebugEvent(out CmdEventLayout value,uint milliseconds);
        [DllImport("kernel32.dll",EntryPoint="ContinueDebugEvent",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool ContinueDebugEvent(uint pid,uint tid,uint disposition);
        [DllImport("kernel32.dll",EntryPoint="ReadProcessMemory",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,[Out] byte[] buffer,UIntPtr count,out UIntPtr actual);
        [DllImport("kernel32.dll",EntryPoint="WriteProcessMemory",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool WriteProcessMemory(IntPtr process,IntPtr address,byte[] buffer,UIntPtr count,out UIntPtr actual);
        [DllImport("kernel32.dll",EntryPoint="FlushInstructionCache",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr count);
        [DllImport("kernel32.dll",EntryPoint="GetThreadContext",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetThreadContext(IntPtr thread,IntPtr context);
        [DllImport("kernel32.dll",EntryPoint="SetThreadContext",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool SetThreadContext(IntPtr thread,IntPtr context);
        [DllImport("kernel32.dll",EntryPoint="SuspendThread",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint SuspendThread(IntPtr thread);
        [DllImport("kernel32.dll",EntryPoint="ResumeThread",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll",EntryPoint="GetFinalPathNameByHandleW",ExactSpelling=true,CharSet=CharSet.Unicode,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint GetFinalPathNameByHandleW(IntPtr file,StringBuilder buffer,uint size,uint flags);
        [DllImport("kernel32.dll",EntryPoint="DuplicateHandle",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool DuplicateHandle(IntPtr source,IntPtr target,IntPtr destination,out IntPtr duplicate,uint access,[MarshalAs(UnmanagedType.Bool)] bool inherit,uint options);
        [DllImport("kernel32.dll",EntryPoint="GetCurrentProcess",ExactSpelling=true,CallingConvention=CallingConvention.Winapi)] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll",EntryPoint="GetFileInformationByHandle",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetFileInformationByHandle(IntPtr file,out CmdFileInfoLayout info);
        [DllImport("kernel32.dll",EntryPoint="CloseHandle",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll",EntryPoint="WaitForSingleObject",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)] static extern uint WaitForSingleObject(IntPtr process,uint milliseconds);
        [DllImport("kernel32.dll",EntryPoint="GetExitCodeProcess",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetExitCodeProcess(IntPtr process,out uint exit);
        [DllImport("kernel32.dll",EntryPoint="TerminateProcess",ExactSpelling=true,CallingConvention=CallingConvention.Winapi,SetLastError=true)]
        [return:MarshalAs(UnmanagedType.Bool)] static extern bool TerminateProcess(IntPtr process,uint code);
    }
    sealed class CmdRemoteReader {
        readonly CmdDebugApi api; readonly CmdOriginalProcess process;
        public int BytesRead { get; private set; }
        public CmdRemoteReader(CmdDebugApi value,CmdOriginalProcess original) { api=value;process=original; }
        public static ulong Add(ulong address,ulong delta) {
            if(address==0 || delta>UInt64.MaxValue-address) throw new CmdDebugFault("read_failed","ReadProcessMemory",0);
            return address+delta;
        }
        public byte[] Read(ulong address,int count) {
            if(count<=0 || count>1048576-BytesRead) throw new CmdDebugFault("read_limit","ReadProcessMemory",0);
            Add(address,(ulong)count);
            // Reserve the whole request before calling; failed or short reads never restore the budget.
            BytesRead+=count;var bytes=new byte[count];ulong actual;
            if(!api.Read(process,address,bytes,out actual) || actual!=(ulong)count)
                throw new CmdDebugFault("read_failed","ReadProcessMemory",api.Error);
            return bytes;
        }
    }
    struct CmdDebugSection { public uint Rva,Size; public bool Executable; }
    sealed class CmdDebugModule {
        public ulong Base; public uint Size,ExportRva,ExportSize;
        public readonly List<CmdDebugSection> Sections=new List<CmdDebugSection>();
        public bool Executable(ulong address) { return ExecutableRange(address,1); }
        public bool ExecutableRange(ulong address,uint count) {
            if(address<Base || address-Base>=Size) return false;
            ulong rva=address-Base;
            foreach(var section in Sections)
                if(section.Executable && rva>=section.Rva && rva-section.Rva<section.Size && count<=section.Size-(rva-section.Rva)) return true;
            return false;
        }
    }
    static class CmdDebugPe {
        static void Require(bool condition) { if(!condition) throw new CmdDebugFault("pe_invalid","none",0); }
        static bool Range(uint rva,uint size,uint image) { return rva<=image && size<=image-rva; }
        public static CmdDebugModule Parse(CmdRemoteReader reader,ulong address) {
            byte[] dos=reader.Read(address,64);
            Require(CmdU16(dos,0)==0x5a4d);
            uint pe=CmdU32(dos,60);
            Require(pe>=64 && pe<=65536);
            byte[] header=reader.Read(CmdRemoteReader.Add(address,pe),24);
            Require(CmdU32(header,0)==0x4550 && CmdU16(header,4)==0x8664);
            int sections=CmdU16(header,6),optionalSize=CmdU16(header,20);
            Require(sections>=1 && sections<=96 && optionalSize>=112 && optionalSize<=4096);
            byte[] optional=reader.Read(CmdRemoteReader.Add(address,pe+24),optionalSize);
            Require(CmdU16(optional,0)==0x20b);
            uint size=CmdU32(optional,56),headers=CmdU32(optional,60),directories=CmdU32(optional,108);
            Require(size>0 && headers>0 && headers<=size && directories<=(uint)(optionalSize-112)/8);
            ulong sectionOffset=(ulong)pe+24+(uint)optionalSize;uint sectionBytes=(uint)sections*40;
            Require(sectionOffset<=headers && sectionBytes<=headers-sectionOffset);
            CmdRemoteReader.Add(address,size);
            var module=new CmdDebugModule();
            module.Base=address;module.Size=size;
            if(directories>0) {
                module.ExportRva=CmdU32(optional,112);
                module.ExportSize=CmdU32(optional,116);
            }
            Require((module.ExportRva==0)==(module.ExportSize==0) && Range(module.ExportRva,module.ExportSize,size));
            byte[] table=reader.Read(CmdRemoteReader.Add(address,sectionOffset),(int)sectionBytes);
            for(int index=0;index<sections;index++) {
                int offset=index*40;uint rva=CmdU32(table,offset+12),length=Math.Max(CmdU32(table,offset+8),CmdU32(table,offset+16));
                Require(Range(rva,length,size));
                if(length==0) continue;
                Require(rva>=headers);
                foreach(var prior in module.Sections)
                    Require((ulong)rva+length<=prior.Rva || (ulong)prior.Rva+prior.Size<=rva);
                module.Sections.Add(new CmdDebugSection { Rva=rva,Size=length,Executable=(CmdU32(table,offset+36)&0x20000000)!=0 });
            }
            return module;
        }
        static int ExportOffset(CmdDebugModule module,uint rva,uint count) {
            Require(rva>=module.ExportRva && count<=module.ExportSize && rva-module.ExportRva<=module.ExportSize-count);
            return (int)(rva-module.ExportRva);
        }
        static string ExportName(byte[] block,int offset) {
            int end=offset,limit=Math.Min(block.Length,offset+8192);
            while(end<limit && block[end]!=0) { Require(block[end]<128);end++; }
            Require(end<limit && end>offset);
            return Encoding.ASCII.GetString(block,offset,end-offset);
        }
        public static ulong[] ResolveNtdll(CmdRemoteReader reader,CmdDebugModule module) {
            Require(module.ExportRva!=0 && module.ExportSize>=40 && module.ExportSize<=524288);
            byte[] block=reader.Read(CmdRemoteReader.Add(module.Base,module.ExportRva),(int)module.ExportSize);
            Require(ExportName(block,ExportOffset(module,CmdU32(block,12),1))=="ntdll.dll");
            uint functions=CmdU32(block,20),names=CmdU32(block,24);
            Require(functions>0 && functions<=8192 && names>0 && names<=8192);
            int functionTable=ExportOffset(module,CmdU32(block,28),functions*4);
            int nameTable=ExportOffset(module,CmdU32(block,32),names*4),ordinalTable=ExportOffset(module,CmdU32(block,36),names*2);
            string[] wanted={"NtCreateFile","NtOpenFile","DbgBreakPoint"};var result=new ulong[3];
            for(int index=0;index<(int)names;index++) {
                string name=ExportName(block,ExportOffset(module,CmdU32(block,nameTable+index*4),1));
                uint ordinal=CmdU16(block,ordinalTable+index*2);
                Require(ordinal<functions);
                for(int target=0;target<wanted.Length;target++) if(name==wanted[target]) {
                    Require(result[target]==0);
                    uint rva=CmdU32(block,functionTable+(int)ordinal*4);
                    Require(rva!=0 && Range(rva,target<2?3U:1U,module.Size) &&
                        !(rva>=module.ExportRva && rva-module.ExportRva<module.ExportSize));
                    ulong entry=CmdRemoteReader.Add(module.Base,rva);
                    Require(module.ExecutableRange(entry,target<2?3U:1U));
                    result[target]=entry;
                }
            }
            Require(result[0]!=0 && result[1]!=0 && result[2]!=0 && result[0]!=result[1] && result[0]!=result[2] && result[1]!=result[2]);
            for(int target=0;target<3;target++) {
                byte[] stub=reader.Read(result[target],target<2?3:1);
                if(target<2?stub[0]!=0x4c || stub[1]!=0x8b || stub[2]!=0xd1:stub[0]!=0xcc)
                    throw new CmdDebugFault("stub_unsupported","none",0);
            }
            return result;
        }
    }
}
