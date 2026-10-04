// Pure fake-native contracts. No debug process, Windows API, filesystem or network access.
using System;
using System.Collections.Generic;
using System.Text;

public static partial class BrokerDirectLauncher {
    static void CmdTestAssert(bool condition,string label) {
        if(!condition) throw new InvalidOperationException("cmd debug contract: "+label);
    }
    static void CmdTestReject(Action action,string label) {
        bool rejected=false;try { action(); } catch(CmdDebugFault) { rejected=true; }
        CmdTestAssert(rejected,label);
    }
    static void CmdTestPut(byte[] bytes,int offset,ulong value,int width) {
        for(int i=0;i<width;i++) bytes[offset+i]=(byte)(value>>(i*8));
    }
    static CmdDebugContext CmdTestContext(ulong rip,ulong rsp) {
        var context=new CmdDebugContext();
        CmdTestPut(context.Raw,68,0x202,4);CmdTestPut(context.Raw,248,rip,8);CmdTestPut(context.Raw,152,rsp,8);
        CmdTestPut(context.Raw,128,0x710000,8);CmdTestPut(context.Raw,136,0xfedcba9880120089,8);
        CmdTestPut(context.Raw,184,0x720000,8);CmdTestPut(context.Raw,192,0xdead0000,8);
        CmdTestPut(context.Raw,200,0x12345678,8);return context;
    }
    static byte[] CmdTestImage() {
        var image=new byte[0x4000];CmdTestPut(image,0,0x5a4d,2);CmdTestPut(image,60,0x80,4);
        CmdTestPut(image,0x80,0x4550,4);CmdTestPut(image,0x84,0x8664,2);CmdTestPut(image,0x86,1,2);
        CmdTestPut(image,0x94,240,2);CmdTestPut(image,0x98,0x20b,2);
        CmdTestPut(image,0x98+56,0x4000,4);CmdTestPut(image,0x98+60,0x400,4);
        CmdTestPut(image,0x98+108,16,4);CmdTestPut(image,0x98+112,0x400,4);CmdTestPut(image,0x98+116,0x400,4);
        CmdTestPut(image,0x188+8,0x2000,4);CmdTestPut(image,0x188+12,0x1000,4);CmdTestPut(image,0x188+36,0x60000020,4);
        CmdTestPut(image,0x40c,0x450,4);CmdTestPut(image,0x414,3,4);CmdTestPut(image,0x418,3,4);
        CmdTestPut(image,0x41c,0x480,4);CmdTestPut(image,0x420,0x490,4);CmdTestPut(image,0x424,0x4a0,4);
        Array.Copy(Encoding.ASCII.GetBytes("ntdll.dll\0"),0,image,0x450,10);
        string[] names={"NtCreateFile","NtOpenFile","DbgBreakPoint"};int text=0x500;
        for(int i=0;i<3;i++) {
            CmdTestPut(image,0x480+i*4,(ulong)(0x1000+i*0x20),4);CmdTestPut(image,0x490+i*4,(ulong)text,4);
            CmdTestPut(image,0x4a0+i*2,(ulong)i,2);byte[] name=Encoding.ASCII.GetBytes(names[i]+"\0");
            Array.Copy(name,0,image,text,name.Length);text+=name.Length;
        }
        foreach(int entry in new int[]{0x1000,0x1020}) { image[entry]=0x4c;image[entry+1]=0x8b;image[entry+2]=0xd1; }
        image[0x1040]=0xcc;image[0x1100]=0x90;return image;
    }
    sealed class CmdFakeApi:CmdDebugApi {
        public const ulong Ntdll=0x100000,Main=0x400000,Stack=0x700000,Output=0x710000,Attributes=0x720000,Name=0x730000,Text=0x740000;
        public readonly QualificationSubject Subject=new QualificationSubject();
        public readonly PilotCaseReceipt Row;
        public readonly List<CmdDebugEvent> Events=new List<CmdDebugEvent>();
        public readonly Dictionary<CmdDebugEvent,CmdDebugContext> EventContexts=new Dictionary<CmdDebugEvent,CmdDebugContext>();
        public readonly Dictionary<ulong,byte[]> Memory=new Dictionary<ulong,byte[]>();
        public readonly Dictionary<IntPtr,uint> Suspends=new Dictionary<IntPtr,uint>();
        public readonly List<string> Calls=new List<string>(),Violations=new List<string>();
        public readonly Dictionary<IntPtr,bool> Closed=new Dictionary<IntPtr,bool>(),Owned=new Dictionary<IntPtr,bool>();
        public readonly Dictionary<IntPtr,bool> IssuedImages=new Dictionary<IntPtr,bool>();
        readonly Dictionary<IntPtr,CmdDebugContext> contexts=new Dictionary<IntPtr,CmdDebugContext>();
        readonly Dictionary<uint,IntPtr> live=new Dictionary<uint,IntPtr>();
        readonly Dictionary<CmdDebugEvent,bool> continued=new Dictionary<CmdDebugEvent,bool>();
        public CmdDebugEvent Pending;
        public CmdContextFake ContextCase;
        public int FailAt,CallCount,PointerWidth=8,ResumeCount,TerminateCount,DuplicateCount,PeerReleases,OutputReads,EntrySeen;
        public string FailName="";public bool ThrowFault,Terminated,ExitContinued,Signal=true,NoExit,WrongIdentity,ShortWrite,ShortRead,PartialSetFailure,BadReadback,BadSet;
        public bool StepFirst,AlwaysNonmatch;public string NonmatchText=@"\??\C:\different.cmd",FailedCall="";public int FailedIndex;
        public bool WrongStepR10,WrongStepRip,WrongStepOther,ResumeMismatch;
        public uint MainPrevious=1,TargetPid=41,ExitValue=1,FileAttributes=0x80,ReturnFlags;public ushort Machine,NativeMachine=0x8664;
        public ulong Creation=12345,DuplicateValue=301,TargetFileValue=0x777;public long Clock;
        public override long NowMilliseconds { get { return Clock; } }
        public override int PointerSize { get { return PointerWidth; } }
        public CmdFakeApi(bool step,bool success,bool open) {
            StepFirst=step;Subject.ProfileCreated=true;
            Row=PilotObservationRow("cmd-relative-batch-exit23");Row.Fatal=false;Row.PositivePassed=false;
            Row.CmdRelativeBatchExit23Observed=false;Subject.Receipt=Row.Launcher;
            Subject.Workspace=Row.Launcher.Identities["pilot_cmd_observation_cwd"];
            Subject.Process=new PROCESS_INFORMATION { process=new IntPtr(11),thread=new IntPtr(12),pid=41,tid=51 };
            Subject.Job=new IntPtr(13);Subject.Receipt.Resumed=false;Subject.Receipt.Exit=UInt32.MaxValue;
            Subject.Receipt.Identities["pilot_cmd_batch_source"]="7:0:15";
            Memory[Ntdll]=CmdTestImage();Memory[Main]=CmdTestImage();Memory[Stack]=new byte[0x100];Memory[Output]=new byte[8];
            Memory[Attributes]=new byte[48];Memory[Name]=new byte[16];
            SetName(@"\??\"+Subject.Workspace+@"\direct.cmd");
            CmdTestPut(Memory[Attributes],0,48,4);CmdTestPut(Memory[Attributes],16,Name,8);CmdTestPut(Memory[Attributes],24,0x40,4);
            CmdTestPut(Memory[Attributes],32,0xdead1000,8);CmdTestPut(Memory[Attributes],40,0xdead2000,8);
            CmdTestPut(Memory[Stack],0,Main+0x1100,8);CmdTestPut(Memory[Stack],0x28,0xaabbccdd00000003,8);
            CmdTestPut(Memory[Stack],0x30,0xaabbccdd00000080,8);CmdTestPut(Memory[Stack],0x38,0xaabbccdd00000007,8);
            CmdTestPut(Memory[Stack],0x40,0xaabbccdd00000001,8);CmdTestPut(Memory[Stack],0x48,0xaabbccdd00000060,8);
            CmdTestPut(Memory[Output],0,0x777,8);
            Events.Add(new CmdDebugEvent { Code=3,Pid=41,Tid=51,File=new IntPtr(201),Process=new IntPtr(101),Thread=new IntPtr(102),Base=Main });
            Events.Add(new CmdDebugEvent { Code=6,Pid=41,Tid=51,File=new IntPtr(202),Base=Ntdll });
            Trap(Ntdll+0x1040,51,CmdTestContext(Ntdll+0x1041,Stack));
            ulong entry=Ntdll+(open?0x1020UL:0x1000UL);
            if(step) {
                Trap(entry,51,CmdTestContext(entry+1,Stack));
                Events.Add(new CmdDebugEvent { Code=1,Pid=41,Tid=51,ExceptionCode=0x80000004,FirstChance=1,Address=entry+3 });
            }
            Trap(entry,51,CmdTestContext(entry+1,Stack));
            var returned=CmdTestContext(Main+0x1101,Stack+8);
            CmdTestPut(returned.Raw,120,success?0xabcdef0000000000:0xabcdef00c0000022,8);
            Trap(Main+0x1100,51,returned);Events.Add(Exit());
        }
        public void SetName(string value) {
            Memory[Text]=Encoding.Unicode.GetBytes(value);CmdTestPut(Memory[Name],0,(ulong)Memory[Text].Length,2);
            CmdTestPut(Memory[Name],2,(ulong)Memory[Text].Length,2);CmdTestPut(Memory[Name],8,Text,8);
        }
        public CmdDebugEvent Exit() { return new CmdDebugEvent { Code=5,Pid=41,Tid=51,ExitCode=ExitValue }; }
        public void Trap(ulong address,uint tid,CmdDebugContext context) {
            var value=new CmdDebugEvent { Code=1,Pid=41,Tid=tid,ExceptionCode=0x80000003,FirstChance=1,Address=address };
            Events.Add(value);EventContexts[value]=context;
        }
        void Require(bool condition,string label) { if(!condition) { Violations.Add(label);throw new InvalidOperationException(label); } }
        bool Call(string name) {
            Calls.Add(name);CallCount++;Error=0;
            if(CallCount!=FailAt && name!=FailName) return true;
            FailedCall=name;FailedIndex=CallCount;Error=5;if(ThrowFault) throw new InvalidOperationException("secret-path-and-exception",new Exception("secret-inner"));return false;
        }
        void Process(CmdOriginalProcess process) { Require(process.Value==Subject.Process.process,"original process handle only"); }
        void Instrument() { Require(!Terminated,"instrumentation after termination"); }
        public override uint ProcessId(CmdOriginalProcess process) { Process(process);return Call("GetProcessId")?TargetPid:0; }
        public override bool ProcessTimes(CmdOriginalProcess process,out ulong creation) { Process(process);creation=Creation;return Call("GetProcessTimes"); }
        public override bool Machines(CmdOriginalProcess process,out ushort machine,out ushort native) {
            Process(process);machine=Machine;native=NativeMachine;return Call("IsWow64Process2");
        }
        public override bool SystemDirectory(out string path) { path=@"C:\Windows\System32";return Call("GetSystemDirectoryW"); }
        public override bool Attach(uint pid) { Require(pid==41,"exact attach PID");return Call("DebugActiveProcess"); }
        public override bool Wait(uint milliseconds,out CmdDebugEvent value) {
            Require(Pending==null,"one pending event");Require(milliseconds<=100,"bounded event wait");value=null;
            if(!Call("WaitForDebugEvent")) return false;
            if(Events.Count==0) { Clock+=milliseconds;Error=121;return false; }
            value=Events[0];Events.RemoveAt(0);Pending=value;
            if(value.Pid==41 && (value.Code==3 || value.Code==6) && (value.File==new IntPtr(201) || value.File==new IntPtr(202))) {
                Require(!IssuedImages.ContainsKey(value.File),"image issued once");IssuedImages.Add(value.File,false);
            }
            if(value.Code==3 || value.Code==2) { live[value.Tid]=value.Thread;contexts[value.Thread]=CmdTestContext(Main+0x1100,Stack); }
            CmdDebugContext context;if(EventContexts.TryGetValue(value,out context) && live.ContainsKey(value.Tid)) contexts[live[value.Tid]]=context.Copy();
            if(value.Code==1 && value.ExceptionCode==0x80000004 && live.ContainsKey(value.Tid)) {
                context=contexts[live[value.Tid]];
                if(WrongStepR10) CmdTestPut(context.Raw,200,0x55,8);
                if(WrongStepRip) CmdTestPut(context.Raw,248,value.Address+1,8);
                if(WrongStepOther) CmdTestPut(context.Raw,136,0x55,8);
            }
            // The first synthetic entry is deliberately a nonmatch, the next is exact.
            if(StepFirst && value.Code==1 && (value.Address==Ntdll+0x1000 || value.Address==Ntdll+0x1020) && (++EntrySeen==1 || AlwaysNonmatch))
                SetName(NonmatchText);
            else if(value.Code==1 && value.ExceptionCode==0x80000004) SetName(@"\??\"+Subject.Workspace+@"\direct.cmd");
            return true;
        }
        public override bool Continue(CmdDebugEvent value,uint disposition) {
            Require(Object.ReferenceEquals(Pending,value) && !continued.ContainsKey(value),"continue exact event once");continued.Add(value,true);
            bool owned=value.ExceptionCode==0x80000003 || value.ExceptionCode==0x80000004;
            if(value.Code==1 && !owned) Require(disposition==0x80010001,"ordinary exception must remain unhandled");
            Require(value.Pid==41,"never continue foreign PID");Require(disposition==0x10002 || disposition==0x80010001,"fixed disposition");
            if(!Call("ContinueDebugEvent")) return false;
            if(!Terminated && value.Code==1 && live.ContainsKey(value.Tid)) {
                var context=contexts[live[value.Tid]];
                if((context.U32(68)&0x100)!=0 && (context.U64(248)==Ntdll+0x1000 || context.U64(248)==Ntdll+0x1020)) {
                    CmdTestPut(context.Raw,200,context.U64(128),8);CmdTestPut(context.Raw,248,context.U64(248)+3,8);
                }
            }
            if(value.Code==4) { contexts.Remove(live[value.Tid]);live.Remove(value.Tid); }
            if(value.Code==5) { ExitContinued=true;live.Clear();contexts.Clear(); }
            Pending=null;return true;
        }
        public override bool Read(CmdOriginalProcess process,ulong address,byte[] bytes,out ulong count) {
            Process(process);Instrument();count=0;if(address==Output) OutputReads++;if(!Call("ReadProcessMemory")) return false;
            foreach(var block in Memory) if(address>=block.Key && address-block.Key<=(ulong)block.Value.Length && (ulong)bytes.Length<=(ulong)block.Value.Length-(address-block.Key)) {
                Array.Copy(block.Value,(int)(address-block.Key),bytes,0,bytes.Length);count=ShortRead?(ulong)bytes.Length-1:(ulong)bytes.Length;
                if(BadReadback && bytes.Length==1 && Calls.Contains("WriteProcessMemory")) bytes[0]^=1;return true;
            }
            Require(address<0xdead0000 || address>=0xdead3000,"no pointed-to IO/status/security read");Error=998;return false;
        }
        public override bool WriteByte(CmdOriginalProcess process,ulong address,byte value,out ulong count) {
            Process(process);Instrument();Require(Pending!=null,"patch only while stopped");count=0;
            Require(address==Ntdll+0x1000 || address==Ntdll+0x1020 || address==Main+0x1100,"fixed patch slots");
            if(!Call("WriteProcessMemory")) return false;
            ulong block=address>=Main?Main:Ntdll;Memory[block][(int)(address-block)]=value;count=ShortWrite?0UL:1UL;return true;
        }
        public override bool FlushByte(CmdOriginalProcess process,ulong address) { Process(process);Instrument();return Call("FlushInstructionCache"); }
        public override bool GetContext(CmdBorrowedThread thread,out CmdDebugContext context) {
            Instrument();Require(Pending!=null && live.ContainsKey(thread.Tid) && live[thread.Tid]==thread.Value,"live stopped context owner");
            context=null;if(!Call("GetThreadContext")) return false;context=contexts[thread.Value].Copy();
            if(ContextCase!=null) {bool ok=ContextCase.Get(this,ref context);Error=ContextCase.Error;return ok;}
            return true;
        }
        public override bool SetContext(CmdBorrowedThread thread,CmdDebugContext context) {
            Instrument();var fresh=contexts[thread.Value];var allowed=fresh.WithRipTf(context.U64(248),(context.U32(68)&0x100)!=0);
            Require(Pending!=null && context.SameRequested(allowed),"fresh context preserves every other requested register");
            if(Pending.Code==1 && Pending.Address==Main+0x1100) {
                Require((context.U32(68)&0x100)==(fresh.U32(68)&0x100),"return correction cannot change fresh TF");
                ReturnFlags=context.U32(68);
            }
            if(!Call("SetThreadContext")) return false;
            if(ContextCase!=null && !ContextCase.Set(this)) {Error=ContextCase.Error;return false;}
            contexts[thread.Value]=context.Copy();
            if(PartialSetFailure) {Error=5;return false;}
            if(BadSet) CmdTestPut(contexts[thread.Value].Raw,136,0x55,8);return true;
        }
        public override uint Suspend(CmdBorrowedThread thread) {
            Instrument();Require(Pending!=null && live.ContainsKey(thread.Tid) && live[thread.Tid]==thread.Value && thread.Tid!=51,"live peer only");
            if(!Call("SuspendThread")) return UInt32.MaxValue;
            uint previous;Suspends.TryGetValue(thread.Value,out previous);Suspends[thread.Value]=previous+1;
            Require(!Owned.ContainsKey(thread.Value),"one owned peer increment");Owned.Add(thread.Value,true);return previous;
        }
        public override uint ResumePeer(CmdBorrowedThread thread) {
            Instrument();Require(Suspends.ContainsKey(thread.Value) && Suspends[thread.Value]>0 && Owned.Remove(thread.Value),"owned increment only");
            PeerReleases++;if(!Call("ResumeThread.peer")) return UInt32.MaxValue;
            uint previous=Suspends[thread.Value];Suspends[thread.Value]=previous-1;return ResumeMismatch?previous+1:previous;
        }
        public override uint ResumeMain(CmdOriginalThread thread) {
            Require(thread.Value==Subject.Process.thread && ++ResumeCount==1,"original resume once");
            Require(Pending!=null && Memory[Ntdll][0x1000]==0xcc && Memory[Ntdll][0x1020]==0xcc,"both entries ready before original resume");
            return Call("ResumeThread.main")?MainPrevious:UInt32.MaxValue;
        }
        public override bool ImagePath(CmdImageFile file,out string path) {
            Require(file.Value==new IntPtr(201) || file.Value==new IntPtr(202),"supplied image handle only");
            path=file.Value==new IntPtr(202)?@"\\?\C:\Windows\System32\ntdll.dll":@"C:\synthetic\cmd.exe";return Call("GetFinalPathNameByHandleW");
        }
        public override bool Duplicate(CmdOriginalProcess process,ulong target,out CmdDuplicate duplicate) {
            Process(process);Require(target==TargetFileValue,"saved output handle only");DuplicateCount++;
            duplicate=new CmdDuplicate(new IntPtr((long)DuplicateValue));return Call("DuplicateHandle");
        }
        public override bool FileInfo(CmdDuplicate file,out CmdFileIdentity identity) {
            Require(file.Value==new IntPtr(301),"broker duplicate metadata only");
            identity=new CmdFileIdentity { Attributes=FileAttributes,Volume=7,High=0,Low=WrongIdentity?999U:15U };return Call("GetFileInformationByHandle");
        }
        bool Close(IntPtr handle,string kind) {
            Require((kind=="image" && (handle==new IntPtr(201) || handle==new IntPtr(202))) || (kind=="duplicate" && handle==new IntPtr(301)),"never close original, borrowed or target handles");
            if(kind=="image") Require(IssuedImages.ContainsKey(handle),"close only an issued image");
            Require(!Closed.ContainsKey(handle),"close attempt once");Closed.Add(handle,true);
            bool closed=Call("CloseHandle."+kind);if(kind=="image" && closed) IssuedImages[handle]=true;return closed;
        }
        public override bool CloseImage(CmdImageFile file) { return Close(file.Value,"image"); }
        public override bool CloseDuplicate(CmdDuplicate file) { return Close(file.Value,"duplicate"); }
        public override uint WaitProcess(CmdOriginalProcess process,uint milliseconds) {
            Process(process);Require(milliseconds<=100,"bounded terminal wait");Clock+=milliseconds;
            if(!Call("WaitForSingleObject")) return UInt32.MaxValue;return Signal?0U:258U;
        }
        public override bool ExitCode(CmdOriginalProcess process,out uint exit) { Process(process);exit=ExitValue;return Call("GetExitCodeProcess"); }
        public override bool Terminate(CmdOriginalProcess process) {
            Process(process);Require(++TerminateCount==1,"terminate once");if(!Call("TerminateProcess")) return false;
            Terminated=true;Events.Clear();if(!NoExit) Events.Add(Exit());return true;
        }
        public CmdDebugSession Observe() {
            var session=new CmdDebugSession(Subject,this);
            try {session.Observe();return session;} finally {CmdTestClearRetained(session);}
        }
        public long Number(string key) { return Subject.Receipt.Numbers["cmd_debug_"+key]; }
        public string Identity(string key) { return Subject.Receipt.Identities["cmd_debug_"+key]; }
        public void CheckSafety(CmdDebugSession session) {
            CmdTestAssert(Violations.Count==0,Violations.Count==0?"safe calls":Violations[0]);
            CmdTestAssert(TerminateCount<=1 && ResumeCount<=1,"bounded destructive calls");
            foreach(var image in IssuedImages) CmdTestAssert(image.Value ||
                (!session.MayCallOriginalCleanup && Identity("cleanup")=="retained_fatal"),"every issued image closes once or remains explicitly retained");
            if(session.MayCallOriginalCleanup && Number("attach_succeeded")==1)
                CmdTestAssert(ExitContinued && Number("process_signaled")==1,"handback requires continued EXIT plus signal");
            if(Number("attach_succeeded")==1 && (FailedCall=="GetProcessId" || FailedCall=="GetProcessTimes"))
                CmdTestAssert(!session.MayCallOriginalCleanup,"uncertain identity must retain without retry");
            if(FailedCall=="WaitForDebugEvent") for(int i=FailedIndex;i<Calls.Count;i++)
                CmdTestAssert(Calls[i]!="WaitForDebugEvent","uncertain wait is never retried");
            foreach(var pair in Subject.Receipt.Identities) if(pair.Key.StartsWith("cmd_debug_",StringComparison.Ordinal))
                CmdTestAssert(pair.Value.IndexOf("secret",StringComparison.Ordinal)<0,"fixed error sanitization");
        }
    }
    static void CmdTestClearRetained(CmdDebugSession session) {
        if(retainedCmdDebug==null) return;
        CmdTestAssert(Object.ReferenceEquals(retainedCmdDebug,session),"never discard another retained session");
        retainedCmdDebug=null;
    }
    static ulong[] CmdTestResolve(CmdFakeApi fake) {
        var reader=new CmdRemoteReader(fake,new CmdOriginalProcess(fake.Subject.Process.process));
        return CmdDebugPe.ResolveNtdll(reader,CmdDebugPe.Parse(reader,CmdFakeApi.Ntdll));
    }
    static void CmdTestAbiAndParser() {
        CmdDebugNative.AssertAbi();using(var buffer=new CmdContextBuffer()) CmdTestAssert((buffer.Aligned.ToInt64()&15)==0,"aligned context");
        var before=CmdTestContext(CmdFakeApi.Ntdll+0x1001,CmdFakeApi.Stack);
        var after=before.WithRipTf(CmdFakeApi.Ntdll+0x1003,true);CmdTestPut(after.Raw,200,before.U64(128),8);
        CmdTestAssert(after.MatchesAfterMov(before),"MOV permits fresh R10=RCX and exact RIP delta");
        var wrong=after.Copy();CmdTestPut(wrong.Raw,200,before.U64(200),8);
        CmdTestAssert(!wrong.MatchesAfterMov(before),"old R10 snapshot rejected");
        CmdTestPut(wrong.Raw,200,before.U64(128),8);CmdTestPut(wrong.Raw,136,0,8);
        CmdTestAssert(!wrong.MatchesAfterMov(before),"unexpected integer delta rejected");
        var fake=new CmdFakeApi(false,false,false);var exports=CmdTestResolve(fake);
        CmdTestAssert(exports[0]==CmdFakeApi.Ntdll+0x1000 && exports[1]==CmdFakeApi.Ntdll+0x1020 && exports[2]==CmdFakeApi.Ntdll+0x1040,"same PE parser resolves exact exports");
        foreach(Action<byte[]> mutate in new Action<byte[]>[]{
            x=>x[0]=0,x=>CmdTestPut(x,60,UInt32.MaxValue,4),x=>CmdTestPut(x,0x84,0xaa64,2),x=>CmdTestPut(x,0x98,0x10b,2),
            x=>CmdTestPut(x,0x86,97,2),x=>CmdTestPut(x,0x98+60,0x100,4),x=>CmdTestPut(x,0x98+108,17,4),
            x=>CmdTestPut(x,0x98+112,UInt32.MaxValue,4),x=>CmdTestPut(x,0x98+116,524289,4),
            x=>CmdTestPut(x,0x188+12,0x3000,4),x=>CmdTestPut(x,0x188+36,0,4),x=>x[0x450]=(byte)'X',
            x=>CmdTestPut(x,0x418,8193,4),x=>CmdTestPut(x,0x4a0,3,2),x=>CmdTestPut(x,0x480,0x500,4),
            x=>CmdTestPut(x,0x484,0x1000,4),x=>CmdTestPut(x,0x494,0x500,4),x=>x[0x1000]=0x90,x=>x[0x1040]=0x90}) {
            fake=new CmdFakeApi(false,false,false);mutate(fake.Memory[CmdFakeApi.Ntdll]);var current=fake;
            CmdTestReject(()=>CmdTestResolve(current),"malformed/forwarded/duplicate/unsupported image rejected");
        }
        CmdTestReject(()=>CmdRemoteReader.Add(UInt64.MaxValue,1),"checked pointer overflow");
        CmdTestReject(()=>CmdRemoteReader.Add(0,8),"null remote pointer");
        fake=new CmdFakeApi(false,false,false);fake.Memory[0x900000]=new byte[1048576];
        var bounded=new CmdRemoteReader(fake,new CmdOriginalProcess(fake.Subject.Process.process));bounded.Read(0x900000,1048576);
        CmdTestReject(()=>bounded.Read(0x900000,1),"aggregate remote-read budget");
    }
    static CmdDebugSession CmdTestRun(CmdFakeApi fake,bool failed,string label) {
        var session=fake.Observe();fake.CheckSafety(session);CmdTestAssert(session.Failed==failed,label);return session;
    }
    static void CmdTestPairs() {
        foreach(bool step in new bool[]{false,true}) foreach(bool success in new bool[]{false,true}) foreach(bool open in new bool[]{false,true}) {
            var fake=new CmdFakeApi(step,success,open);var session=CmdTestRun(fake,false,"paired baseline");
            CmdTestAssert(session.MayCallOriginalCleanup && fake.Number("pair_complete")==1,"complete pair and safe handback");
            CmdTestAssert(fake.Number("entries_ready_before_resume")==1 && fake.Number("attach_break_seen")==1,"bootstrap then exact attach breakpoint");
            CmdTestAssert(fake.Number("ntstatus_u32")== (success?0:0xc0000022L),"only RAX low32 has meaning");
            CmdTestAssert(fake.Identity("result")== (success?"matched_open_succeeded":"matched_open_failed"),"one operation outcome");
            CmdTestAssert(fake.Identity("open_api")== (open?"NtOpenFile":"NtCreateFile"),"paired API");
            CmdTestAssert(fake.Number("desired_access")==0x80120089L && fake.Number("share_access")== (open?3:7),"native argument slots and low32 masks");
            CmdTestAssert(fake.Number("file_attributes")== (open?-1:0x80) && fake.Number("create_disposition")== (open?-1:1) && fake.Number("open_options")== (open?0x80:0x60),"Nt argument variants");
            CmdTestAssert(fake.DuplicateCount==(success?1:0) && fake.OutputReads==(success?1:0),"undefined failed-output handle is not inspected");
            CmdTestAssert(fake.Number("active_patches_at_exit")==0 && fake.Number("owned_suspends_at_exit")==0,"natural completion leaves no instrumentation");
            int numbers=0,identities=0;
            foreach(string key in fake.Subject.Receipt.Numbers.Keys) if(key.StartsWith("cmd_debug_",StringComparison.Ordinal)) numbers++;
            foreach(string key in fake.Subject.Receipt.Identities.Keys) if(key.StartsWith("cmd_debug_",StringComparison.Ordinal)) identities++;
            CmdTestAssert(numbers==36 && identities==6,"frozen receipt key cardinality");
        }
        var returnTf=new CmdFakeApi(false,false,false);CmdTestPut(returnTf.EventContexts[returnTf.Events[4]].Raw,68,0x302,4);
        CmdTestRun(returnTf,false,"fresh return TF=1 is preserved while correcting only RIP");
        CmdTestAssert(returnTf.ReturnFlags==0x302 && returnTf.Number("pair_complete")==1,"return TF preservation is exercised");
        var alias=new CmdFakeApi(false,true,false);alias.TargetFileValue=301;CmdTestPut(alias.Memory[CmdFakeApi.Output],0,301,8);
        CmdTestRun(alias,false,"same numeric value in target and broker namespaces is not ownership");
        var insensitive=new CmdFakeApi(false,false,false);
        insensitive.SetName((@"\??\"+insensitive.Subject.Workspace+@"\direct.cmd").ToUpperInvariant());
        CmdTestRun(insensitive,false,"OBJ_CASE_INSENSITIVE is honored without path normalization");
        var sensitive=new CmdFakeApi(false,false,false);sensitive.SetName((@"\??\"+sensitive.Subject.Workspace+@"\direct.cmd").ToUpperInvariant());
        CmdTestPut(sensitive.Memory[CmdFakeApi.Attributes],24,0,4);CmdTestRun(sensitive,true,"case-sensitive name mismatch remains inconclusive");
        var pending=new CmdFakeApi(false,true,false);CmdTestPut(pending.EventContexts[pending.Events[4]].Raw,120,0xfeed000000000103,8);
        CmdTestRun(pending,true,"pending never success");CmdTestAssert(pending.Number("pair_complete")==0 && pending.DuplicateCount==0 && pending.OutputReads==0,"pending never reads output or IO_STATUS_BLOCK");
        CmdTestAssert(pending.Identity("result")=="observed_pending","pending outcome is explicit");
    }
    static void CmdTestPeers() {
        foreach(int count in new int[]{0,1,3}) {
            var fake=new CmdFakeApi(true,false,false);
            for(int i=0;i<count;i++) {
                var handle=new IntPtr(110+i);fake.Events.Insert(1+i,new CmdDebugEvent { Code=2,Pid=41,Tid=(uint)(61+i),Thread=handle });
                fake.Suspends[handle]=(uint)i;
            }
            // CREATE_THREAD during StepOne must be suspended before it reaches user mode.
            fake.Events.Insert(4+count,new CmdDebugEvent { Code=2,Pid=41,Tid=71,Thread=new IntPtr(120) });
            CmdTestRun(fake,false,"peer-owned step completion");
            for(int i=0;i<count;i++) CmdTestAssert(fake.Suspends[new IntPtr(110+i)]==(uint)i,"preexisting suspend count preserved");
            CmdTestAssert(fake.PeerReleases==count+1 && fake.Owned.Count==0,"exactly acquired peer increments released once");
        }
        var reused=new CmdFakeApi(true,false,false);
        reused.Events.Insert(1,new CmdDebugEvent {Code=2,Pid=41,Tid=61,Thread=new IntPtr(111)});
        reused.Events.Insert(2,new CmdDebugEvent {Code=4,Pid=41,Tid=61});
        reused.Events.Insert(3,new CmdDebugEvent {Code=2,Pid=41,Tid=61,Thread=new IntPtr(112)});
        CmdTestRun(reused,false,"clean TID reuse gets a new handle generation");
        CmdTestAssert(!reused.Suspends.ContainsKey(new IntPtr(111)) && reused.Suspends[new IntPtr(112)]==0,"old generation never suspended or resumed");
        foreach(Action<CmdFakeApi> mutate in new Action<CmdFakeApi>[] {
            x=>x.WrongStepR10=true,x=>x.WrongStepRip=true,x=>x.WrongStepOther=true,x=>x.ResumeMismatch=true,
            x=>{x.Events[4].Tid=61;x.Events.Insert(1,new CmdDebugEvent {Code=2,Pid=41,Tid=61,Thread=new IntPtr(111)});},x=>x.Events[4].ExceptionCode=0x80000003,
            x=>x.Events.Insert(4,new CmdDebugEvent { Code=4,Pid=41,Tid=51 }),
            x=>{x.Events.Insert(1,new CmdDebugEvent { Code=2,Pid=41,Tid=61,Thread=new IntPtr(111) });
                x.Events.Insert(5,new CmdDebugEvent { Code=4,Pid=41,Tid=61 });
                x.Events.Insert(6,new CmdDebugEvent { Code=2,Pid=41,Tid=61,Thread=new IntPtr(112) });}}) {
            var fake=new CmdFakeApi(true,false,false);mutate(fake);
            if(fake.ResumeMismatch) fake.Events.Insert(1,new CmdDebugEvent { Code=2,Pid=41,Tid=62,Thread=new IntPtr(113) });
            CmdTestRun(fake,true,"ambiguous step ownership rejected");
        }
    }
    static void CmdTestFailuresAndHandback() {
        foreach(bool aliasedThread in new bool[]{false,true}) foreach(int closeMode in new int[]{0,1,2}) {
            var early=new CmdFakeApi(false,false,false);
            if(aliasedThread) early.Events[0].Thread=early.Subject.Process.thread;else early.Events[0].Tid=52;
            if(closeMode!=0) {early.FailName="CloseHandle.image";early.ThrowFault=closeMode==2;}
            var session=CmdTestRun(early,true,"early CREATE fault accounts for its issued image");
            CmdTestAssert(early.IssuedImages.Count==1 && early.Closed.ContainsKey(new IntPtr(201)),"early fault attempts the valid image close");
            CmdTestAssert(early.IssuedImages[new IntPtr(201)]==(closeMode==0),"image close confirmation reflects native outcome");
            int attempts=0;foreach(string call in early.Calls) if(call=="CloseHandle.image") attempts++;
            CmdTestAssert(attempts==1,"false or exceptional image close is never retried");
            if(closeMode!=0) CmdTestAssert(!session.MayCallOriginalCleanup && early.Identity("cleanup")=="retained_fatal" &&
                !early.Calls.Contains("ContinueDebugEvent"),"uncertain early image close retains before any continuation");
        }
        foreach(Action<CmdFakeApi> mutate in new Action<CmdFakeApi>[] {
            x=>x.PointerWidth=4,x=>x.Machine=0x14c,x=>x.NativeMachine=0xaa64,x=>x.TargetPid=42,
            x=>x.MainPrevious=0,x=>x.MainPrevious=2,x=>x.ShortWrite=true,x=>x.ShortRead=true,
            x=>x.PartialSetFailure=true,x=>x.BadReadback=true,x=>x.BadSet=true,x=>x.FileAttributes=0x10,x=>x.FileAttributes=0x400,
            x=>x.WrongIdentity=true,x=>x.DuplicateValue=11,x=>x.DuplicateValue=102,
            x=>CmdTestPut(x.Memory[CmdFakeApi.Output],0,0,8),x=>CmdTestPut(x.Memory[CmdFakeApi.Output],0,UInt64.MaxValue,8),
            x=>x.Events[0].Tid=52,x=>x.Events[0].Process=x.Subject.Process.process,
            x=>x.Events[2].Address++,x=>x.Events[2].FirstChance=0,x=>x.Events[3].Pid=42,
            x=>x.Events.RemoveAt(2),x=>{x.Events[4].Tid=61;x.Events.Insert(1,new CmdDebugEvent {Code=2,Pid=41,Tid=61,Thread=new IntPtr(111)});},
            x=>CmdTestPut(x.EventContexts[x.Events[4]].Raw,152,CmdFakeApi.Stack+16,8),
            x=>CmdTestPut(x.EventContexts[x.Events[3]].Raw,68,0x302,4),x=>x.Memory[CmdFakeApi.Main][0x1100]=0xcc,
            x=>CmdTestPut(x.Memory[CmdFakeApi.Stack],0,CmdFakeApi.Ntdll+0x1000,8),
            x=>CmdTestPut(x.Memory[CmdFakeApi.Stack],0,0,8),x=>CmdTestPut(x.EventContexts[x.Events[3]].Raw,152,UInt64.MaxValue-3,8),
            x=>x.Events.Insert(4,new CmdDebugEvent { Code=4,Pid=41,Tid=51 }),x=>x.Events.RemoveAt(4),x=>x.Signal=false,
            x=>{x.Events.Clear();x.NoExit=true;},x=>{x.Events.RemoveAt(1);x.Events.RemoveRange(1,x.Events.Count-1);}}) {
            var fake=new CmdFakeApi(false,true,false);mutate(fake);CmdTestRun(fake,true,"finite protocol fault");
        }
        foreach(string name in new string[]{"DuplicateHandle","GetFileInformationByHandle","CloseHandle.duplicate","CloseHandle.image","TerminateProcess"}) {
            var fake=new CmdFakeApi(false,true,false);fake.FailName=name;
            if(name=="TerminateProcess") fake.Events[2].Address++;
            CmdTestRun(fake,true,"owned resource/native failure");
        }
        var uncertain=new CmdFakeApi(false,false,false);uncertain.FailName="DebugActiveProcess";uncertain.ThrowFault=true;
        var retained=CmdTestRun(uncertain,true,"attach outcome unknown");CmdTestAssert(!retained.MayCallOriginalCleanup,"attach exception never means unattached");
        var failedAttach=new CmdFakeApi(false,false,false);failedAttach.FailName="DebugActiveProcess";
        CmdTestAssert(CmdTestRun(failedAttach,true,"documented failed attach").MayCallOriginalCleanup,"documented false attach permits original cleanup");
        var continueFailure=new CmdFakeApi(false,false,false);continueFailure.FailName="ContinueDebugEvent";
        CmdTestAssert(!CmdTestRun(continueFailure,true,"uncertain continuation").MayCallOriginalCleanup,"signal alone cannot replace EXIT continuation");
        var earlyExit=new CmdFakeApi(false,false,false);earlyExit.Events.RemoveRange(2,earlyExit.Events.Count-3);
        var safeExit=CmdTestRun(earlyExit,true,"unpaired exit incomplete");
        CmdTestAssert(safeExit.MayCallOriginalCleanup && earlyExit.TerminateCount==0 && earlyExit.Number("active_patches_at_exit")==2,"pending EXIT bypasses termination and preserves patch facts");
        foreach(Action<CmdFakeApi> mutate in new Action<CmdFakeApi>[] {
            x=>CmdTestPut(x.Memory[CmdFakeApi.Attributes],8,123,8),x=>CmdTestPut(x.Memory[CmdFakeApi.Name],0,3,2),
            x=>CmdTestPut(x.Memory[CmdFakeApi.Name],2,2,2),x=>CmdTestPut(x.Memory[CmdFakeApi.Name],0,8194,2),
            x=>x.SetName("relative.cmd"),x=>x.SetName("\0"),x=>{x.SetName("x");x.Memory[CmdFakeApi.Text]=new byte[]{0,0xd8};}}) {
            var fake=new CmdFakeApi(false,false,false);mutate(fake);CmdTestRun(fake,true,"unsupported name remains incomplete");
            CmdTestAssert(fake.Number("pair_complete")==0,"unsupported name never binds call");
        }
    }
    static void CmdTestBoundsAndEvents() {
        var threads=new CmdFakeApi(false,false,false);
        for(int i=0;i<32;i++) threads.Events.Insert(1+i,new CmdDebugEvent {Code=2,Pid=41,Tid=(uint)(100+i),Thread=new IntPtr(1000+i)});
        CmdTestRun(threads,true,"live thread bound");CmdTestAssert(threads.Identity("error")=="thread_limit","thread-limit code");
        var modules=new CmdFakeApi(false,false,false);
        for(int i=0;i<128;i++) {
            ulong address=0x1000000+(ulong)i*0x10000;modules.Memory[address]=CmdTestImage();
            modules.Events.Insert(1+i,new CmdDebugEvent {Code=6,Pid=41,Tid=51,Base=address});
        }
        CmdTestRun(modules,true,"module bound");CmdTestAssert(modules.Identity("error")=="module_limit","module-limit code");
        var events=new CmdFakeApi(false,false,false);
        for(int i=0;i<4096;i++) events.Events.Insert(1,new CmdDebugEvent {Code=8,Pid=41,Tid=51});
        CmdTestRun(events,true,"operational event bound");CmdTestAssert(events.Identity("error")=="event_limit","event-limit code");
        foreach(bool largeName in new bool[]{false,true}) {
            var entries=new CmdFakeApi(true,false,false);entries.AlwaysNonmatch=true;
            if(largeName) entries.NonmatchText=new string('x',4096);
            entries.Events.RemoveRange(3,entries.Events.Count-3);
            for(int i=0;i<129;i++) {
                entries.Trap(CmdFakeApi.Ntdll+0x1000,51,CmdTestContext(CmdFakeApi.Ntdll+0x1001,CmdFakeApi.Stack));
                entries.Events.Add(new CmdDebugEvent {Code=1,Pid=41,Tid=51,ExceptionCode=0x80000004,FirstChance=1,Address=CmdFakeApi.Ntdll+0x1003});
            }
            CmdTestRun(entries,true,"entry/read budget");CmdTestAssert(entries.Identity("error")== (largeName?"read_limit":"entry_limit"),"finite budget error");
        }
        foreach(uint chance in new uint[]{0,1}) {
            var ordinary=new CmdFakeApi(false,false,false);
            ordinary.Events.Insert(3,new CmdDebugEvent {Code=1,Pid=41,Tid=51,ExceptionCode=0xc0000005,FirstChance=chance});
            CmdTestRun(ordinary,false,"ordinary exception passes through to application");
        }
        var delayed=new CmdFakeApi(false,false,false);delayed.Events.Insert(1,new CmdDebugEvent {Code=8,Pid=41,Tid=51});
        CmdTestRun(delayed,false,"readiness waits for delayed ntdll LOAD");
    }
    static void CmdTestFaultSweep() {
        foreach(bool step in new bool[]{false,true}) {
            var baseline=new CmdFakeApi(step,true,false);
            if(step) baseline.Events.Insert(1,new CmdDebugEvent { Code=2,Pid=41,Tid=61,Thread=new IntPtr(111) });
            CmdTestRun(baseline,false,"fault-sweep baseline");int count=baseline.CallCount;
            for(int call=1;call<=count;call++) foreach(bool throws in new bool[]{false,true}) {
                var fake=new CmdFakeApi(step,true,false);fake.FailAt=call;fake.ThrowFault=throws;
                if(step) fake.Events.Insert(1,new CmdDebugEvent { Code=2,Pid=41,Tid=61,Thread=new IntPtr(111) });
                var session=CmdTestRun(fake,true,"native failure at every baseline/step state");
                CmdTestAssert(fake.CallCount>=call,"fault reached");
                if(fake.Identity("cleanup")=="retained_fatal") CmdTestAssert(!session.MayCallOriginalCleanup,"retained state cannot reach legacy cleanup");
            }
        }
    }
    static void CmdTestPreclassifierGate() {
        foreach(Action<CmdFakeApi> mutate in new Action<CmdFakeApi>[] {
            x=>{},x=>x.Row.Launcher.Exit=23,x=>x.Row.Launcher.Exit=0,x=>x.Row.Launcher.Exit=42,
            x=>x.Row.Launcher.Numbers["pilot_cmd_observation_stdout_matches"]=0,
            x=>x.Row.Launcher.Numbers["pilot_cmd_observation_stderr_empty"]=0,
            x=>x.Row.Launcher.Numbers.Remove("pilot_cmd_observation_raw_complete"),
            x=>x.Row.Launcher.Numbers["cmd_debug_pair_complete"]=0}) {
            var fake=new CmdFakeApi(false,false,false);var session=CmdTestRun(fake,false,"gate baseline");
            fake.Row.Launcher.Exit=1;mutate(fake);bool rejected=false,classifier=false,resolved=false;
            try { RequireCmdDebugComparable(session,fake.Row);classifier=true;resolved=true; }
            catch(InvalidOperationException failure) {
                rejected=true;CmdTestAssert(failure.InnerException==null && failure.Message=="cmd_debug_incomplete","gate throws only fixed literal");
            }
            bool expected=fake.Row.Launcher.Exit!=1 || !fake.Row.Launcher.Numbers.ContainsKey("pilot_cmd_observation_raw_complete") ||
                fake.Row.Launcher.Numbers["pilot_cmd_observation_stdout_matches"]!=1 || fake.Row.Launcher.Numbers["pilot_cmd_observation_stderr_empty"]!=1 || fake.Number("pair_complete")!=1;
            CmdTestAssert(rejected==expected,"perturbation gate outcome");
            if(expected) CmdTestAssert(fake.Row.Fatal && !fake.Row.PositivePassed && !classifier && !resolved,"fatal precedes classifier and resolution");
        }
    }
    public static void RunCmdDebugContractTests() {
        CmdTestAssert(retainedCmdDebug==null,"test entry cannot discard a live retained session");
        var guardFake=new CmdFakeApi(false,false,false);var guarded=new CmdDebugSession(guardFake.Subject,guardFake);
        retainedCmdDebug=guarded;bool rejected=false;
        try {CmdTestClearRetained(null);} catch(InvalidOperationException) {rejected=true;}
        finally {CmdTestAssert(Object.ReferenceEquals(retainedCmdDebug,guarded),"foreign retained slot survives guard");CmdTestClearRetained(guarded);}
        CmdTestAssert(rejected,"retention reset guard is nonvacuous");
        CmdTestAbiAndParser();CmdTestPairs();CmdTestPeers();CmdTestFailuresAndHandback();CmdTestBoundsAndEvents();CmdTestFaultSweep();CmdTestPreclassifierGate();
        CmdTestContextContracts();
    }
}
