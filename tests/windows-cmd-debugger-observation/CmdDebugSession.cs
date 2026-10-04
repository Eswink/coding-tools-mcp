// One original own-child open observation. No production authority or live detach.
using System;
using System.Collections.Generic;
using System.Text;

public static partial class BrokerDirectLauncher {
    static CmdDebugSession retainedCmdDebug;
    sealed class CmdDebugSession {
        enum Phase {NotAttached,Bootstrap,Watching,StepOne,AwaitReturn,DrainExit,AbortDrain,Exited,RetainedFatal}
        enum ImageOwnership {None,Owned,Attempted,Closed,Unknown}
        sealed class ThreadSlot {
            public CmdBorrowedThread Handle;
            public bool IncrementOwned,ReleaseAttempted;
            public uint Previous;
        }
        sealed class Patch {
            public ulong Address;
            public byte Original;
            public bool Active,Uncertain;
        }
        static readonly string[] NumericKeys=("pid main_tid creation_filetime attach_attempted attach_succeeded attach_break_seen "+
            "entries_ready_before_resume event_count cleanup_event_count thread_peak module_peak entry_hits unsupported_names read_bytes "+
            "write_attempts matched_tid pair_complete desired_access object_attributes share_access file_attributes create_disposition "+
            "open_options ntstatus_u32 object_identity_matched active_patches_at_exit owned_suspends_at_exit exit_event_seen "+
            "exit_event_continued process_signaled terminal_exit_u32 abort_terminate_attempted abort_terminate_error native_error elapsed_ms").Split(' ');
        readonly QualificationSubject subject;
        readonly DirectReceipt receipt;
        readonly CmdDebugApi api;
        readonly CmdOriginalProcess process;
        readonly CmdOriginalThread main;
        readonly CmdRemoteReader reader;
        readonly Dictionary<uint,ThreadSlot> threads=new Dictionary<uint,ThreadSlot>();
        readonly Dictionary<ulong,CmdDebugModule> modules=new Dictionary<ulong,CmdDebugModule>();
        readonly Dictionary<IntPtr,bool> protectedHandles=new Dictionary<IntPtr,bool>();
        readonly List<Patch> patches=new List<Patch>();
        Phase phase=Phase.NotAttached;
        CmdDebugEvent pending;
        ImageOwnership pendingImageState;
        IntPtr pendingImage;
        bool continueAttempted,attached,attachUnknown,created,attachBreak,ready,terminationAttempted,waitUnknown,identityUncertain;
        long started,generation,cleanupEnd;
        ulong creation,breakAddress,entryRsp,outputHandleAddress;
        uint owner;
        CmdDebugContext beforeStep;
        Patch stepping,returnPatch;
        string systemNtdll;
        public bool MayCallOriginalCleanup {get;private set;}
        public bool Failed {get {return receipt.Identities["cmd_debug_error"]!="none";}}
        public CmdDebugSession(QualificationSubject s,CmdDebugApi operations) {
            subject=s;receipt=s.Receipt;api=operations;
            process=new CmdOriginalProcess(s.Process.process);main=new CmdOriginalThread(s.Process.thread);
            reader=new CmdRemoteReader(api,process);MayCallOriginalCleanup=true;
            foreach(string key in NumericKeys) N(key,-1);
            foreach(string key in ("attach_attempted attach_succeeded attach_break_seen entries_ready_before_resume event_count "+
                "cleanup_event_count thread_peak module_peak entry_hits unsupported_names read_bytes write_attempts pair_complete "+
                "active_patches_at_exit owned_suspends_at_exit exit_event_seen exit_event_continued process_signaled abort_terminate_attempted native_error elapsed_ms").Split(' ')) N(key,0);
            I("protocol","own-child-open-v1");I("result","incomplete");I("error","none");I("error_api","none");I("cleanup","not_attached");I("open_api","none");
            foreach(IntPtr h in new IntPtr[]{s.Process.process,s.Process.thread,s.Job,s.SourceToken}) if(h!=IntPtr.Zero) AddProtected(h);
        }
        bool AddProtected(IntPtr handle) {
            if(protectedHandles.ContainsKey(handle)) return false;protectedHandles.Add(handle,true);return true;
        }
        void N(string key,long value) {receipt.Numbers["cmd_debug_"+key]=value;}
        long N(string key) {return receipt.Numbers["cmd_debug_"+key];}
        void I(string key,string value) {receipt.Identities["cmd_debug_"+key]=value;}
        void Require(bool ok,string code,string call) {if(!ok) throw new CmdDebugFault(code,call,api.Error);}
        void Fault(string code) {throw new CmdDebugFault(code,"none",0);}
        void Record(Exception failure) {
            if(Failed) return;
            CmdDebugFault fault=failure as CmdDebugFault;
            I("error",fault==null?"internal_exception":fault.Code);I("error_api",fault==null?"none":fault.Api);
            N("native_error",fault==null?0:fault.NativeError);
        }
        public void Observe() {
            try {
                started=api.NowMilliseconds;
                Require(retainedCmdDebug==null && api.PointerSize==8,"abi_unsupported","none");CmdDebugNative.AssertAbi();
                Require(process.Value!=IntPtr.Zero && process.Value!=new IntPtr(-1) && main.Value!=IntPtr.Zero && main.Value!=new IntPtr(-1) &&
                    process.Value!=main.Value && subject.Job!=IntPtr.Zero && subject.Job!=process.Value && subject.Job!=main.Value &&
                    subject.OwnershipCertain && subject.ProfileCreated && receipt.Created && receipt.Assigned && !receipt.Resumed &&
                    receipt.CreationFlags==0x08080404 && receipt.Kind=="cmd" &&
                    PilotIdentity(receipt,"pilot_case_id","cmd-relative-batch-exit23"),"target_identity","none");
                N("pid",subject.Process.pid);N("main_tid",subject.Process.tid);
                BindIdentity(true);N("creation_filetime",(long)creation);
                ushort machine,native;Require(api.Machines(process,out machine,out native),"native_failed","IsWow64Process2");
                Require(machine==0 && native==0x8664,"abi_unsupported","none");
                string system;Require(api.SystemDirectory(out system),"native_failed","GetSystemDirectoryW");systemNtdll=system+@"\ntdll.dll";
                N("attach_attempted",1);MayCallOriginalCleanup=false;attachUnknown=true;
                bool ok=api.Attach(subject.Process.pid);attachUnknown=false;
                if(!ok) {MayCallOriginalCleanup=true;Require(false,"attach_failed","DebugActiveProcess");}
                attached=true;N("attach_succeeded",1);phase=Phase.Bootstrap;
                while(phase!=Phase.Exited) {Deadline(false);Next(false);if(pending!=null) Handle();}
            } catch(Exception failure) {
                Record(failure);
                try {Abort();} catch(Exception cleanupFailure) {Record(cleanupFailure);Retain();}
            } finally {
                N("read_bytes",reader.BytesRead);
                try {N("elapsed_ms",Math.Max(0,api.NowMilliseconds-started));} catch {N("elapsed_ms",-1);}
                if(phase!=Phase.Exited && (attached || attachUnknown)) Retain();
            }
        }
        void BindIdentity(bool first) {
            identityUncertain=true;
            Require(subject.Process.pid!=0 && api.ProcessId(process)==subject.Process.pid,"target_identity","GetProcessId");
            ulong value;Require(api.ProcessTimes(process,out value) && value>0 && value<=Int64.MaxValue &&
                (first || value==creation),"target_identity","GetProcessTimes");
            if(first) creation=value;identityUncertain=false;
        }
        void Deadline(bool cleanup) {
            long remaining=(cleanup?cleanupEnd:started+30000)-api.NowMilliseconds;
            if(remaining<=0) Fault("deadline");
        }
        void Next(bool cleanup) {
            if(pending!=null) Fault("event_protocol");
            string key=cleanup?"cleanup_event_count":"event_count";
            if(N(key)>=(cleanup?512:4096)) Fault("event_limit");
            long remaining=(cleanup?cleanupEnd:started+30000)-api.NowMilliseconds;
            if(remaining<=0) Fault("deadline");
            CmdDebugEvent e;
            waitUnknown=true;bool ok=api.Wait((uint)Math.Min(remaining,100),out e);waitUnknown=false;
            if(!ok) {Require(api.Error==121,"native_failed","WaitForDebugEvent");return;}
            pending=e;continueAttempted=false;N(key,N(key)+1);
            if(e==null || e.Pid!=subject.Process.pid) Fault("event_protocol");
            AdoptImage(e); // Own the returned file before any dispatch or thread-identity check.
            if(e.Tid==0) Fault("event_protocol");
        }
        void Continue(uint disposition) {
            if(pending==null || continueAttempted) Fault("event_protocol");
            if(pendingImageState!=ImageOwnership.None && pendingImageState!=ImageOwnership.Closed) Fault("close_uncertain");
            continueAttempted=true;
            Require(api.Continue(pending,disposition),"native_failed","ContinueDebugEvent");pending=null;
            pendingImageState=ImageOwnership.None;pendingImage=IntPtr.Zero;
        }
        ThreadSlot Thread(uint tid) {ThreadSlot t;if(!threads.TryGetValue(tid,out t)) {Fault("event_protocol");return null;}return t;}
        void AddThread(CmdDebugEvent e) {
            if(threads.ContainsKey(e.Tid) || e.Thread==IntPtr.Zero || e.Thread==new IntPtr(-1) || !AddProtected(e.Thread)) Fault("event_protocol");
            if(threads.Count>=32) Fault("thread_limit");
            var t=new ThreadSlot();t.Handle=new CmdBorrowedThread(e.Thread,e.Tid,++generation);threads.Add(e.Tid,t);
            N("thread_peak",Math.Max(N("thread_peak"),threads.Count));
            if(phase==Phase.StepOne) Hold(t);
        }
        void Hold(ThreadSlot t) {
            if(t.IncrementOwned || t.ReleaseAttempted) Fault("event_protocol");
            uint previous=api.Suspend(t.Handle);Require(previous!=UInt32.MaxValue,"suspend_failed","SuspendThread");
            t.Previous=previous;t.IncrementOwned=true;
        }
        void ReleasePeers() {
            foreach(ThreadSlot t in threads.Values) if(t.IncrementOwned) {
                if(t.ReleaseAttempted) Fault("event_protocol");t.ReleaseAttempted=true;
                uint previous=api.ResumePeer(t.Handle);t.IncrementOwned=false;
                Require(previous!=UInt32.MaxValue && previous==t.Previous+1,"resume_failed","ResumeThread");t.ReleaseAttempted=false;
            }
        }
        void AdoptImage(CmdDebugEvent e) {
            pendingImageState=ImageOwnership.None;pendingImage=IntPtr.Zero;
            if((e.Code!=3 && e.Code!=6) || e.File==IntPtr.Zero) return;
            pendingImage=e.File;pendingImageState=ImageOwnership.Unknown;
            if(e.File==new IntPtr(-1) || protectedHandles.ContainsKey(e.File) ||
                (e.Code==3 && (e.File==e.Process || e.File==e.Thread))) Fault("close_uncertain");
            pendingImageState=ImageOwnership.Owned;
        }
        void CloseImage(IntPtr value) {
            if(value!=pendingImage) Fault("close_uncertain");
            if(pendingImageState==ImageOwnership.None || pendingImageState==ImageOwnership.Closed) return;
            if(pendingImageState!=ImageOwnership.Owned) Fault("close_uncertain");
            pendingImageState=ImageOwnership.Attempted; // Consume before the call; an uncertain close is never retried.
            Require(api.CloseImage(new CmdImageFile(value)),"close_uncertain","CloseHandle");
            pendingImageState=ImageOwnership.Closed;
        }
        void Image(CmdDebugEvent e) {
            try {
                if(modules.ContainsKey(e.Base)) Fault("module_identity");
                if(modules.Count>=128) Fault("module_limit");
                CmdDebugModule module=CmdDebugPe.Parse(reader,e.Base);modules.Add(e.Base,module);
                N("module_peak",Math.Max(N("module_peak"),modules.Count));
                string path=null;
                if(e.File!=IntPtr.Zero) Require(api.ImagePath(new CmdImageFile(e.File),out path),"native_failed","GetFinalPathNameByHandleW");
                if(path!=null && path.StartsWith(@"\\?\",StringComparison.Ordinal)) path=path.Substring(4);
                if(e.Code==6 && String.Equals(path,systemNtdll,StringComparison.OrdinalIgnoreCase)) {
                    if(ready || patches.Count!=0) Fault("module_identity");
                    ulong[] exports=CmdDebugPe.ResolveNtdll(reader,module);breakAddress=exports[2];
                    patches.Add(new Patch{Address=exports[0],Original=0x4c});patches.Add(new Patch{Address=exports[1],Original=0x4c});
                    foreach(Patch p in patches) PatchByte(p,true);
                    N("entries_ready_before_resume",1);ready=true;
                    receipt.Stage="resume_verified_target";uint previous=api.ResumeMain(main);receipt.Numbers["resume_previous_count"]=previous;
                    Require(previous==1,"resume_failed","ResumeThread");receipt.Resumed=true;phase=Phase.Watching;
                }
            } finally {CloseImage(e.File);}
        }
        void Handle() {
            CmdDebugEvent e=pending;
            if(!created && e.Code!=3) Fault("event_protocol");
            switch(e.Code) {
                case 3:
                    if(created || e.Tid!=subject.Process.tid || e.Process==IntPtr.Zero || e.Process==new IntPtr(-1) || !AddProtected(e.Process)) Fault("target_identity");
                    BindIdentity(false);
                    AddThread(e);created=true;Image(e);Continue(0x10002);break;
                case 2: AddThread(e);Continue(0x10002);break;
                case 6: Image(e);Continue(0x10002);break;
                case 7:
                    CmdDebugModule removed;if(!modules.TryGetValue(e.Base,out removed)) Fault("module_identity");
                    foreach(Patch p in patches) if((p.Active || p.Uncertain) && p.Address>=removed.Base && p.Address-removed.Base<removed.Size) Fault("event_protocol");
                    modules.Remove(e.Base);Continue(0x10002);break;
                case 4:
                    ThreadSlot gone=Thread(e.Tid);
                    if(gone.IncrementOwned || gone.ReleaseAttempted || ((phase==Phase.StepOne || phase==Phase.AwaitReturn) && owner==e.Tid)) Fault("return_ambiguous");
                    Continue(0x10002);threads.Remove(e.Tid);protectedHandles.Remove(gone.Handle.Value);break;
                case 5: Exit(false);break;
                case 8: Continue(0x10002);break; // Never dereference target debug strings.
                case 1: ExceptionEvent(e);break;
                default: Fault("event_protocol");break;
            }
        }
        CmdDebugContext Context(ThreadSlot t) {
            CmdDebugContext c;Require(api.GetContext(t.Handle,out c),"context_failed","GetThreadContext");return c;
        }
        void SetContext(ThreadSlot t,CmdDebugContext c) {
            Require(api.SetContext(t.Handle,c),"context_failed","SetThreadContext");
            Require(Context(t).SameRequested(c),"context_failed","GetThreadContext");
        }
        void PatchByte(Patch p,bool arm) {
            if(p.Uncertain || p.Active==arm || reader.Read(p.Address,1)[0]!=(arm?p.Original:(byte)0xcc)) Fault("patch_failed");
            if(N("write_attempts")>=264) Fault("write_limit");N("write_attempts",N("write_attempts")+1);p.Uncertain=true;
            ulong count;Require(api.WriteByte(process,p.Address,arm?(byte)0xcc:p.Original,out count) && count==1,"patch_failed","WriteProcessMemory");
            Require(api.FlushByte(process,p.Address),"patch_failed","FlushInstructionCache");
            Require(reader.Read(p.Address,1)[0]==(arm?(byte)0xcc:p.Original),"patch_failed","ReadProcessMemory");p.Active=arm;p.Uncertain=false;
        }
        void ExceptionEvent(CmdDebugEvent e) {
            if(phase!=Phase.StepOne && e.ExceptionCode!=0x80000003) {Continue(0x80010001);return;}
            ThreadSlot t=Thread(e.Tid);CmdDebugContext c=Context(t);
            if(phase==Phase.StepOne) {
                if(e.Tid!=owner || e.ExceptionCode!=0x80000004 || e.FirstChance!=1 || !c.MatchesAfterMov(beforeStep)) Fault("context_failed");
                PatchByte(stepping,true);SetContext(t,c.WithRipTf(c.U64(248),false));ReleasePeers();stepping=null;beforeStep=null;
                phase=Phase.Watching;Continue(0x10002);return;
            }
            if(e.ExceptionCode==0x80000003 && e.Address==breakAddress && !attachBreak && e.FirstChance==1 && c.U64(248)==CmdRemoteReader.Add(breakAddress,1)) {
                attachBreak=true;N("attach_break_seen",1);Continue(0x10002);return;
            }
            if(e.ExceptionCode!=0x80000003) {Continue(0x80010001);return;}
            if(e.FirstChance!=1 || c.U64(248)!=CmdRemoteReader.Add(e.Address,1)) Fault("event_protocol");
            if(phase==Phase.AwaitReturn && returnPatch!=null && returnPatch.Active && e.Address==returnPatch.Address) {
                if(e.Tid!=owner || c.U64(152)!=CmdRemoteReader.Add(entryRsp,8)) Fault("return_ambiguous");
                Return(t,c);return;
            }
            if(phase!=Phase.Watching) Fault("event_protocol");
            Patch hit=null;foreach(Patch p in patches) if(p.Active && p.Address==e.Address) hit=p;
            if(hit==null) Fault("event_protocol");
            if(N("entry_hits")>=128) Fault("entry_limit");N("entry_hits",N("entry_hits")+1);
            if((c.U32(68)&0x100)!=0) Fault("context_failed");
            bool match=Match(c,hit==patches[0]);
            if(match) {
                if(!attachBreak) Fault("bootstrap_incomplete");
                MatchEntry(t,c,hit);return;
            }
            owner=e.Tid;beforeStep=c;stepping=hit;
            foreach(ThreadSlot peer in threads.Values) if(peer.Handle.Tid!=owner) Hold(peer);
            PatchByte(hit,false);SetContext(t,c.WithRipTf(hit.Address,true));phase=Phase.StepOne;Continue(0x10002);
        }
        bool Match(CmdDebugContext c,bool create) {
            byte[] attributes=reader.Read(c.U64(184),48);
            if(CmdU32(attributes,0)!=48 || CmdU64(attributes,8)!=0) {N("unsupported_names",N("unsupported_names")+1);return false;}
            byte[] name=reader.Read(CmdU64(attributes,16),16);int length=CmdU16(name,0);
            if(length==0 || (length&1)!=0 || length>8192 || length>CmdU16(name,2)) {N("unsupported_names",N("unsupported_names")+1);return false;}
            string text;
            try {text=new UnicodeEncoding(false,false,true).GetString(reader.Read(CmdU64(name,8),length));}
            catch(DecoderFallbackException) {N("unsupported_names",N("unsupported_names")+1);return false;}
            if(text.IndexOf('\0')>=0) {N("unsupported_names",N("unsupported_names")+1);return false;}
            uint flags=CmdU32(attributes,24);
            if(!String.Equals(text,@"\??\"+subject.Workspace+@"\direct.cmd",(flags&0x40)!=0?StringComparison.OrdinalIgnoreCase:StringComparison.Ordinal)) return false;
            byte[] stack=reader.Read(c.U64(152),create?0x60:0x38);
            I("open_api",create?"NtCreateFile":"NtOpenFile");N("desired_access",(long)(c.U64(136)&UInt32.MaxValue));N("object_attributes",flags);
            N("share_access",CmdU32(stack,create?0x38:0x28));N("open_options",CmdU32(stack,create?0x48:0x30));
            if(create) {N("file_attributes",CmdU32(stack,0x30));N("create_disposition",CmdU32(stack,0x40));}
            return true;
        }
        void MatchEntry(ThreadSlot t,CmdDebugContext c,Patch hit) {
            entryRsp=c.U64(152);ulong address=CmdU64(reader.Read(entryRsp,8),0);CmdRemoteReader.Add(entryRsp,8);
            bool executable=false;foreach(CmdDebugModule m in modules.Values) executable=m.Executable(address)||executable;
            if(!executable) Fault("return_ambiguous");foreach(Patch p in patches) if(p.Address==address) Fault("return_ambiguous");
            byte original=reader.Read(address,1)[0];if(original==0xcc) Fault("return_ambiguous");
            owner=t.Handle.Tid;outputHandleAddress=c.U64(128);N("matched_tid",owner);
            foreach(Patch p in patches) PatchByte(p,false);
            returnPatch=new Patch{Address=address,Original=original};patches.Add(returnPatch);PatchByte(returnPatch,true);
            SetContext(t,c.WithRipTf(hit.Address,false));phase=Phase.AwaitReturn;Continue(0x10002);
        }
        void Return(ThreadSlot t,CmdDebugContext c) {
            uint status=(uint)(c.U64(120)&UInt32.MaxValue);N("ntstatus_u32",status);
            if(status==0x103) {I("result","observed_pending");Fault("pending_io");}
            if((status&0x80000000)!=0) I("result","matched_open_failed");
            else {
                ulong target=CmdU64(reader.Read(outputHandleAddress,8),0);
                if(target==0 || unchecked((long)target)<0) Fault("object_mismatch");
                CmdDuplicate candidate;Require(api.Duplicate(process,target,out candidate),"native_failed","DuplicateHandle");
                if(candidate.Value==IntPtr.Zero || candidate.Value==new IntPtr(-1) || protectedHandles.ContainsKey(candidate.Value)) Fault("close_uncertain");
                try {
                    CmdFileIdentity info;Require(api.FileInfo(candidate,out info),"native_failed","GetFileInformationByHandle");
                    bool same=(info.Attributes&0x410)==0 && PilotIdentity(receipt,"pilot_cmd_batch_source",info.Volume+":"+info.High+":"+info.Low);
                    N("object_identity_matched",same?1:0);if(!same) Fault("object_mismatch");
                } finally {Require(api.CloseDuplicate(candidate),"close_uncertain","CloseHandle");}
                I("result","matched_open_succeeded");
            }
            PatchByte(returnPatch,false);SetContext(t,c.WithRipTf(returnPatch.Address,(c.U32(68)&0x100)!=0));N("pair_complete",1);
            phase=Phase.DrainExit;Continue(0x10002);
        }
        void Exit(bool cleanup) {
            uint debugExit=pending.ExitCode;N("exit_event_seen",1);
            int active=0,held=0;foreach(Patch p in patches) if(p.Active || p.Uncertain) active++;
            foreach(ThreadSlot t in threads.Values) if(t.IncrementOwned || t.ReleaseAttempted) held++;
            N("active_patches_at_exit",active);N("owned_suspends_at_exit",held);
            Continue(0x10002);N("exit_event_continued",1);
            if(!cleanup) cleanupEnd=Math.Min(started+35000,api.NowMilliseconds+5000);
            long remaining=cleanupEnd-api.NowMilliseconds;if(remaining<=0) Fault("exit_unconfirmed");
            uint wait;
            do {
                remaining=cleanupEnd-api.NowMilliseconds;if(remaining<=0) Fault("exit_unconfirmed");
                wait=api.WaitProcess(process,(uint)Math.Min(remaining,100));receipt.Wait=wait;
                Require(wait==0 || wait==258,"exit_unconfirmed","WaitForSingleObject");
            } while(wait==258);
            N("process_signaled",1);
            uint exit;Require(api.ExitCode(process,out exit),"exit_unconfirmed","GetExitCodeProcess");
            Require(exit==debugExit,"target_identity","GetExitCodeProcess");BindIdentity(false);
            receipt.Exit=exit;receipt.Numbers["pilot_exit_query_success"]=1;N("terminal_exit_u32",exit);
            phase=Phase.Exited;attached=false;MayCallOriginalCleanup=true;I("cleanup","exit_confirmed");
            if(!cleanup && N("pair_complete")==0) {
                I("result",N("matched_tid")==-1?"no_match":"incomplete");Fault(N("matched_tid")==-1?"unsupported_match":"return_ambiguous");
            }
            if(!cleanup && (held!=0 || (N("pair_complete")==1 && active!=0))) Fault("event_protocol");
        }
        void Abort() {
            if(phase==Phase.Exited || (!attached && !attachUnknown)) return;
            if(N("exit_event_seen")==1 || pendingImageState==ImageOwnership.Attempted || pendingImageState==ImageOwnership.Unknown) {Retain();return;}
            if(attachUnknown || identityUncertain || (pending!=null && (pending.Pid!=subject.Process.pid || continueAttempted))) {Retain();return;}
            phase=Phase.AbortDrain;cleanupEnd=Math.Min(started+35000,api.NowMilliseconds+5000);
            if(pending!=null && pending.Code==5) {Exit(true);return;}
            if(terminationAttempted) {Retain();return;}terminationAttempted=true;N("abort_terminate_attempted",1);
            bool terminated=api.Terminate(process);N("abort_terminate_error",terminated?0:api.Error);
            if(!terminated || waitUnknown || receipt.Identities["cmd_debug_error_api"]=="WaitForDebugEvent") {Retain();return;}
            if(pending!=null) {
                if(pending.Code==3 || pending.Code==6) CloseImage(pending.File);
                Continue(pending.Code==1?0x80010001u:0x10002u);
            }
            while(phase!=Phase.Exited) {
                Deadline(true);Next(true);if(pending==null) continue;
                if(pending.Code==5) {Exit(true);return;}
                if(pending.Code==3 || pending.Code==6) CloseImage(pending.File);
                Continue(pending.Code==1?0x80010001u:0x10002u);
            }
        }
        void Retain() {
            phase=Phase.RetainedFatal;MayCallOriginalCleanup=false;I("cleanup","retained_fatal");
            retainedCmdDebug=this; // No finalizer/disposer may release an unresolved original subject.
        }
    }
    static void RequireCmdDebugComparable(CmdDebugSession session,PilotCaseReceipt row) {
        if(session==null) return;
        try {
            DirectReceipt r=row.Launcher;
            bool baseline=r.Exit==1 && PilotNumber(r,"pilot_cmd_observation_raw_complete",1) &&
                PilotNumber(r,"pilot_cmd_observation_stdout_matches",1) && PilotNumber(r,"pilot_cmd_observation_stderr_empty",1);
            if(!baseline) {r.Identities["cmd_debug_result"]="debugger_perturbed";r.Identities["cmd_debug_error"]="debugger_perturbed";}
            if(!session.MayCallOriginalCleanup || session.Failed || !PilotIdentity(r,"cmd_debug_cleanup","exit_confirmed") ||
                !PilotNumber(r,"cmd_debug_pair_complete",1) || !baseline) throw new InvalidOperationException("cmd_debug_incomplete");
        } catch {
            row.Fatal=true;row.PositivePassed=false;row.OfflineReferenceRouteValid=false;
            throw new InvalidOperationException("cmd_debug_incomplete");
        }
    }
}
