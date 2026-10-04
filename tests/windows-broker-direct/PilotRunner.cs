// Finite CI-only pilot. Per-target authority and current-owner lifecycle are mandatory.
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static partial class BrokerDirectLauncher {
    public sealed class PilotCaseReceipt {
        public string Case,Policy="accesscheck_signature_v1_ci",Status="pending",Failure,CanaryClassification="not_measured";
        public DirectReceipt Launcher=new DirectReceipt();
        public bool Fatal,NoCaseResourcesAllocated,AuthorityObserved,OrdinarySignatureMatched,OrdinaryRejected,PreResumeReady;
        public bool IndividualResourceCleanupConfirmed,CaptureIntegrityConfirmed,ProfileDeleteApiConfirmed,OwnedRootRemoved;
        public bool CleanupPreconditionsConfirmed,CaseMarkerResolved,ScopedLifecycleCleanupConfirmed;
        public bool OutsideUnchanged,OutsideWriteAbsent,OutsideReadObserved,OutsideWriteObserved,ScriptEntryObserved,OutputOk,MutationOk;
        public bool PositivePassed,OfflineReferenceRouteValid,NativeFiveAssertionsPassed,NetworkDenialProven=false;
        public bool CmdExit23Observed,CmdBatchExit23Observed;
        public bool CmdCwdObserved,CmdReadObserved;
        public bool CmdRelativeBatchExit23Observed;
        public string ExitHex,KnownStartupStatus;
    }
    public sealed class PilotRunReceipt {
        public string Policy="accesscheck_signature_v1_ci",Phase="collecting",Failure;
        public string CleanupScope="eleven required case outcomes, their actually created profile/private scopes and disposable run root and selected-parent metadata handles only; listener, preparation evidence, outer workflow capture/upload are separate outcomes";
        public string CompletionJournal,JournalProtocol="completed filename is the final resolution receipt; preconditions alone are not completion";
        public bool OrdinaryControlPassed,ReferenceRoutePassed,AllFourOfflineCasesPassed,AllCaseCleanupConfirmed,RunRootRemoved;
        public bool CmdSentinelObservationPassed,CmdBatchObservationPassed;
        public bool CmdCwdRawObservationMatched,CmdReadRawObservationMatched;
        public bool CmdRelativeBatchRawObservationMatched;
        public bool NetworkDenialProven=false;
        public int RequiredCaseCount=11,OriginalPilotRequiredCaseCount=6,AdditiveSentinelRequiredCaseCount=1,AdditiveBatchRequiredCaseCount=1,OriginalNestedRequiredRows=20;
        public int AdditiveCwdRequiredCaseCount=1,AdditiveReadRequiredCaseCount=1;
        public int AdditiveRelativeBatchRequiredCaseCount=1;
        public string[] NotCovered=new string[]{"python","npm.cmd","git","nested_child_support","ConPTY","production_integration"};
        public SelectedParentReceipt InitialSelectedParent,SelectedParent=new SelectedParentReceipt();
        public DirectReceipt Broker=new DirectReceipt();
        public List<PilotCaseReceipt> Cases=new List<PilotCaseReceipt>();
    }
    static void ClassifyPilotCase(PilotCaseReceipt row,string evidence) {
        var files=new Dictionary<string,string>(StringComparer.Ordinal);
        foreach(string name in new string[]{"stdout.txt","stderr.txt","script-entry.txt","mutation.txt","runtime-canary.txt","outside-read.txt","pre-network.txt","runtime-checks.txt","receipt.txt","canary.txt","probe-write.txt"}) {
            long error;
            if(!row.Launcher.Numbers.TryGetValue("capture_"+name+"_open_error",out error))
                throw new InvalidOperationException("capture observation missing");
            if(error==2) {
                if(name=="stdout.txt" || name=="stderr.txt" || name=="canary.txt") throw new InvalidOperationException("mandatory captured evidence absent");
                continue;
            }
            if(error!=0) throw new InvalidOperationException("capture absence is not proven by this error");
            // Every present capture must read successfully; File.Exists cannot turn an I/O failure into absence.
            files.Add(name,File.ReadAllText(Path.Combine(evidence,name)));
        }
        ClassifyPilotFacts(row,files);
    }
    static PilotCaseReceipt RunPilotCase(string fixture,string fixtureHash,string payload,string parent,string evidence,string kind,int port,string originalCmdHash,
        bool ordinaryControlPassed,PilotJournal runJournal,Action<string[]> markerGuard,Func<PilotCaseReceipt,string> serialize) {
        var row=new PilotCaseReceipt();row.Case=kind;row.Launcher.Kind=(kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind))?"cmd":kind;DirectReceipt r=row.Launcher;
        r.Identities["pilot_case_id"]=kind;
        var s=new QualificationSubject();s.Receipt=r;s.Parent=parent;s.Profile="ctm.fixture.pilot."+Guid.NewGuid().ToString("N");
        string leaf="owned-"+Guid.NewGuid().ToString("N");s.Root=Path.Combine(parent,leaf);
        r.Identities["pilot_profile_name"]=s.Profile;
        s.Code=Path.Combine(s.Root,"code");s.Workspace=Path.Combine(s.Root,"workspace");s.Outside=Path.Combine(s.Root,"outside");
        PilotJournal journal=null;PilotOwnedScope owned=null;
        CmdDebugSession cmdDebug=null;
        try {
            runJournal.VerifyPending();
            journal=new PilotJournal(evidence,kind,s.Root,s.Profile,r);
            markerGuard(new string[]{runJournal.Path,journal.Path});
            owned=CreatePilotOwnedScope(parent,leaf,r);
            WritePilotEvidence(Path.Combine(evidence,"ownership-root.json"),serialize(row),r,"ownership_root");
            PreparePilotSubject(s,fixture,payload,kind,port,evidence,delegate {
                WritePilotEvidence(Path.Combine(evidence,"ownership-profile.json"),serialize(row),r,"ownership_profile");
            });
            WritePilotEvidence(Path.Combine(evidence,"ownership-process.json"),serialize(row),r,"ownership_process");
            if(!s.ProfileCreated || !s.OwnershipCertain || !PilotIdentity(r,"fixture_source_sha256",fixtureHash) ||
                ((kind=="ordinary" || kind=="reference") && r.ExecutableSha256!=fixtureHash))
                throw new InvalidOperationException("same-run native bytes or owned profile unverified");
            if(kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind)) {
                r.Numbers["pilot_cmd_same_binary_verified"]=0;
                if(!PilotCmdSha256(originalCmdHash) || originalCmdHash!=r.ExecutableSha256)
                    throw new InvalidOperationException("sentinel cmd bytes differ from original cmd case");
                r.Identities["pilot_original_cmd_sha256"]=originalCmdHash;
                r.Numbers["pilot_cmd_same_binary_verified"]=1;
            }
            foreach(string manifest in new string[]{"copy-source-destination-sha256.txt","private-code-sha256.txt","environment.txt"}) {
                bool copied=CaptureOwnedFile(s.Root,evidence,manifest,r);
                if(!copied || !PilotNumber(r,"capture_"+manifest+"_open_error",0)) throw new InvalidOperationException("mandatory same-run provenance capture failed");
            }
            r.Stage="inspect_actual_suspended_target";
            bool sourceValid=false,observerClosed=false,sourceClosed=false;
            try {
                sourceValid=ObserveQualificationSource(s);
                if(sourceValid) observerClosed=ObserveAccessCheckToken(s.SourceToken,r.ProfileSid,r);
                s.OwnershipCertain=observerClosed && s.OwnershipCertain;
            } finally {
                sourceClosed=QualificationSetupCleanup(s,delegate {sourceClosed=PilotCloseHandle(ref s.SourceToken,"token",r);},"pilot_source_close") && sourceClosed;
                s.OwnershipCertain=sourceClosed && s.OwnershipCertain;
            }
            bool ordinary=kind=="ordinary";
            bool signature=sourceValid && observerClosed && sourceClosed && s.OwnershipCertain && VerifyPilotSignature(r,ordinary);
            row.OrdinarySignatureMatched=ordinary && signature;
            row.OrdinaryRejected=ordinary && signature && !VerifyPilotSignature(r,false);
            row.AuthorityObserved=!ordinary && signature;
            if(ordinary) {
                if(!row.OrdinarySignatureMatched || !row.OrdinaryRejected) throw new InvalidOperationException("ordinary negative control did not strictly reject LPAC predicate");
            } else {
                runJournal.VerifyPending();journal.VerifyPending();
                markerGuard(new string[]{runJournal.Path,journal.Path});
                row.PreResumeReady=PilotMayResume(ordinaryControlPassed,s.OwnershipCertain,s.ProfileCreated,row);
                if(!row.PreResumeReady) throw new InvalidOperationException("current-run ordinary control or actual suspended target predicate unverified");
                r.Stage="assign_verified_target";Check(AssignProcessToJobObject(s.Job,s.Process.process),"pilot assign before resume");r.Assigned=true;
                if(kind=="cmd-relative-batch-exit23") {
                    cmdDebug=new CmdDebugSession(s,new CmdDebugNative());
                    cmdDebug.Observe();
                    if(cmdDebug.Failed) throw new InvalidOperationException("cmd_debug_observation_failed");
                } else {
                r.Stage="resume_verified_target";uint previous=ResumeThread(s.Process.thread);r.Numbers["resume_previous_count"]=previous;
                if(previous!=1) throw new InvalidOperationException("unexpected target suspension state");r.Resumed=true;
                r.Stage="wait";r.Wait=WaitForSingleObject(s.Process.process,30000);
                if(r.Wait!=WAIT_OBJECT_0 && r.Wait!=WAIT_TIMEOUT) throw new InvalidOperationException("pilot wait failed");
                if(r.Wait==WAIT_OBJECT_0) {uint exit;Check(GetExitCodeProcess(s.Process.process,out exit),"pilot exit code");r.Exit=exit;r.Numbers["pilot_exit_query_success"]=1;}
                }
                r.Stage="target_observation_terminal";
            }
        } catch(Exception failure) {
            row.Fatal=true;row.Failure=failure.GetType().Name+": "+failure.Message;row.Status="pilot_setup_or_authority_failed";r.Failure=row.Failure;
            if(journal!=null) journal.Failed=true;
        } finally {
            if(cmdDebug!=null && !cmdDebug.MayCallOriginalCleanup) {
                row.Fatal=true;row.IndividualResourceCleanupConfirmed=false;row.Status="cmd_debug_recovery_retained";
            } else {
            try {row.IndividualResourceCleanupConfirmed=StopQualificationSubject(s);}
            catch(Exception failure) {row.Fatal=true;row.Failure="cleanup: "+failure.GetType().Name+": "+failure.Message;}
            }
            if(!row.IndividualResourceCleanupConfirmed) {row.Fatal=true;row.Status="individual_resource_cleanup_uncertain";}
        }
        if(!row.Fatal && s.ProcessStopped && s.JobDrained) {
            try {
                runJournal.VerifyPending();journal.VerifyPending();
                markerGuard(new string[]{runJournal.Path,journal.Path});
                bool captured=true;
                foreach(string file in new string[]{"stdout.txt","stderr.txt","script-entry.txt","mutation.txt","runtime-canary.txt","outside-read.txt","pre-network.txt","runtime-checks.txt","receipt.txt"})
                    captured=CaptureOwnedFile(s.Workspace,evidence,file,r) && captured;
                captured=CaptureOwnedFile(s.Outside,evidence,"canary.txt",r) && captured;
                captured=CaptureOwnedFile(s.Outside,evidence,"probe-write.txt",r) && captured;
                row.CaptureIntegrityConfirmed=captured;
                if(!captured) throw new InvalidOperationException("capture close uncertain");
                if(PilotCmdObservationKind(kind)) ReadPilotCmdObservation(s,evidence);
                RequireCmdDebugComparable(cmdDebug,row);
                ClassifyPilotCase(row,evidence);
                if(!row.Fatal) {
                    if(!s.ProfileCreated) throw new InvalidOperationException("profile ownership absent");
                    int hr=DeleteAppContainerProfile(s.Profile);r.Numbers["delete_profile_hresult"]=hr;
                    row.ProfileDeleteApiConfirmed=hr==0;
                    if(!row.ProfileDeleteApiConfirmed) throw new InvalidOperationException("exact owned profile deletion failed");
                    row.OwnedRootRemoved=RemovePilotOwnedScope(owned,r);
                    if(!row.OwnedRootRemoved) throw new InvalidOperationException("exact owned root removal unconfirmed");
                    row.CleanupPreconditionsConfirmed=PilotCleanupPreconditions(row);
                    runJournal.VerifyPending();journal.VerifyPending();
                    journal.BindPreconditions(serialize(row));
                    journal.Resolve();row.CaseMarkerResolved=true;
                    row.ScopedLifecycleCleanupConfirmed=row.CleanupPreconditionsConfirmed && row.CaseMarkerResolved;
                }
            } catch(Exception failure) {row.Fatal=true;row.Status="evidence_or_scoped_cleanup_failed";row.Failure=failure.GetType().Name+": "+failure.Message;}
        }
        if(row.Fatal) {if(journal!=null) journal.Failed=true;row.PositivePassed=false;row.OfflineReferenceRouteValid=false;}
        // The run journal survives this post-resolution write and every matrix write.
        try {WritePilotEvidence(Path.Combine(evidence,"case.json"),serialize(row),r,"case_receipt");}
        catch(Exception failure) {
            row.Fatal=true;row.PositivePassed=false;row.OfflineReferenceRouteValid=false;
            row.Status="case_receipt_persistence_failed";row.Failure=failure.GetType().Name+": "+failure.Message;
            runJournal.Failed=true;
        }
        return row;
    }
    public static PilotRunReceipt RunPilot(string fixture,string payload,string evidence,string temp,int port,string[] ready,
        Action<string[]> markerGuard,Func<PilotCaseReceipt,string> serializeCase,Func<PilotRunReceipt,string> serializeRun) {
        if(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" || Environment.GetEnvironmentVariable("RUNNER_OS")!="Windows")
            throw new InvalidOperationException("GitHub Windows diagnostic only");
        foreach(string path in new string[]{fixture,payload,evidence,temp}) SafePath(path);
        if(Path.GetFileName(fixture)!="windows_sandbox_fixture.exe" || port<1 || port>65535) throw new ArgumentException("fixed native fixture and bounded endpoint required");
        if(markerGuard==null || serializeCase==null || serializeRun==null) throw new ArgumentException("mandatory fixed guard and evidence serializers required");
        var result=new PilotRunReceipt();PilotJournal journal=null;PilotOwnedScope scope=null;PilotSelectedParent selectedParent=null;
        Action<string[]> fixedMarkerGuard=markerGuard;
        string fixtureHash=HashFile(fixture);result.Broker.Identities["same_run_native_fixture_sha256"]=fixtureHash;
        try {
            result.InitialSelectedParent=CheckSelectedParentRecovery(temp,fixedMarkerGuard,new string[0]);
            if(result.InitialSelectedParent.Failure!=null || !result.InitialSelectedParent.FinalScanConfirmed || !result.InitialSelectedParent.CloseConfirmed)
                throw new InvalidOperationException("selected-parent initial recovery preflight failed");
            string runLeaf="ctm-direct-pilot-"+Guid.NewGuid().ToString("N");
            journal=new PilotJournal(evidence,"run",Path.Combine(temp,runLeaf),null,result.Broker);result.CompletionJournal=Path.GetFileName(journal.CompletedPath);
            journal.VerifyPending();
            selectedParent=new PilotSelectedParent(temp,result.SelectedParent,SelectedParentNativeOperations());
            selectedParent.AcquireSelectedParent();
            markerGuard=delegate(string[] allowed) {selectedParent.GuardSelectedRecovery(fixedMarkerGuard,allowed);};
            markerGuard(new string[]{journal.Path});
            scope=CreatePilotOwnedScope(temp,runLeaf,result.Broker);
            var available=new Dictionary<string,bool>(StringComparer.Ordinal);
            foreach(string kind in ready) {
                if((kind!="node" && kind!="cmd" && kind!="powershell" && kind!="pwsh") || available.ContainsKey(kind))
                    throw new ArgumentException("finite distinct prepared runtime list required");
                available.Add(kind,true);
            }
            bool blocked=false;string originalCmdHash=null;
            foreach(string kind in new string[]{"ordinary","reference","node","cmd","powershell","pwsh","cmd-exit23","cmd-batch-exit23","cmd-cwd","cmd-read-direct","cmd-relative-batch-exit23"}) {
                PilotCaseReceipt row;
                string runtime=(kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind))?"cmd":kind;
                if(blocked || (kind!="ordinary" && !result.OrdinaryControlPassed) || (kind!="ordinary" && kind!="reference" && !result.ReferenceRoutePassed)) {
                    row=new PilotCaseReceipt();row.Case=kind;row.Status="blocked_prior_control_or_recovery";row.Fatal=true;row.NoCaseResourcesAllocated=true;
                } else if(kind!="ordinary" && kind!="reference" && !available.ContainsKey(runtime)) {
                    row=new PilotCaseReceipt();row.Case=kind;row.Status="preparation_failed";row.NoCaseResourcesAllocated=true;
                } else if((kind=="cmd-exit23" || kind=="cmd-batch-exit23" || PilotCmdObservationKind(kind)) && !PilotCmdSha256(originalCmdHash)) {
                    row=new PilotCaseReceipt();row.Case=kind;row.Status="blocked_original_cmd_provenance";row.Fatal=true;row.NoCaseResourcesAllocated=true;
                } else {
                    journal.VerifyPending();markerGuard(new string[]{journal.Path});string caseEvidence=Path.Combine(evidence,kind);
                    if(Directory.Exists(caseEvidence) || File.Exists(caseEvidence)) throw new InvalidOperationException("case evidence must be new");
                    Directory.CreateDirectory(caseEvidence);
                    row=RunPilotCase(fixture,fixtureHash,payload,scope.Root,caseEvidence,kind,port,originalCmdHash,result.OrdinaryControlPassed,journal,markerGuard,serializeCase);
                }
                result.Cases.Add(row);
                result.AllFourOfflineCasesPassed=PilotOriginalSixPassed(result.Cases);
                result.CmdSentinelObservationPassed=PilotCmdSentinelPassed(result.Cases);
                result.CmdBatchObservationPassed=PilotCmdBatchPassed(result.Cases);
                result.CmdCwdRawObservationMatched=PilotCmdCwdRawMatched(result.Cases);
                result.CmdReadRawObservationMatched=PilotCmdReadRawMatched(result.Cases);
                result.CmdRelativeBatchRawObservationMatched=PilotCmdRelativeBatchRawMatched(result.Cases);
                WritePilotEvidence(Path.Combine(evidence,"matrix-"+result.Cases.Count.ToString("D2")+".json"),serializeRun(result),result.Broker,"matrix_"+result.Cases.Count);
                if(!PilotMayAdvance(row)) {blocked=true;journal.Failed=true;}
                if(kind=="ordinary") result.OrdinaryControlPassed=row.OrdinarySignatureMatched && row.OrdinaryRejected && row.ScopedLifecycleCleanupConfirmed && !row.Fatal;
                if(kind=="reference") result.ReferenceRoutePassed=row.OfflineReferenceRouteValid && row.ScopedLifecycleCleanupConfirmed && !row.Fatal;
                if(kind=="cmd" && PilotNumber(row.Launcher,"pilot_copied_bytes_verified",1)) originalCmdHash=row.Launcher.ExecutableSha256;
            }
            bool allCleanup=true;
            foreach(PilotCaseReceipt row in result.Cases) {
                allCleanup=allCleanup && PilotMayAdvance(row);
            }
            result.AllCaseCleanupConfirmed=allCleanup && result.Cases.Count==11;
            if(!result.AllCaseCleanupConfirmed || journal.Failed) throw new InvalidOperationException("required case cleanup incomplete; run journal retained");
            journal.VerifyPending();markerGuard(new string[]{journal.Path});
            result.RunRootRemoved=RemovePilotOwnedScope(scope,result.Broker);
            if(!result.RunRootRemoved) throw new InvalidOperationException("run scaffolding removal unconfirmed");
            journal.VerifyPending();markerGuard(new string[]{journal.Path});
            result.SelectedParent.FinalScanConfirmed=true;
            if(!selectedParent.CloseSelectedParent()) throw new InvalidOperationException("selected parent pin closure unconfirmed");
            // Selected-namespace operations end here. Only fixed evidence and journal operations follow.
            result.Phase="completion_preconditions_persisted";
            WritePilotEvidence(Path.Combine(evidence,"pilot-result.json"),serializeRun(result),result.Broker,"final_result");
            journal.BindPreconditions(serializeRun(result));
            journal.VerifyPending();
            journal.Resolve(); // Last required fallible pilot action. No later persistence or launch.
            return result;
        } catch(Exception failure) {
            if(journal!=null) journal.Failed=true;
            if(selectedParent!=null) selectedParent.CloseSelectedParent();
            result.Failure=failure.GetType().Name+": "+failure.Message;result.Phase="failed_recovery_retained";
            var recorded=new Dictionary<string,bool>(StringComparer.Ordinal);
            foreach(PilotCaseReceipt row in result.Cases) if(!recorded.ContainsKey(row.Case)) recorded.Add(row.Case,true);
            foreach(string kind in new string[]{"ordinary","reference","node","cmd","powershell","pwsh","cmd-exit23","cmd-batch-exit23","cmd-cwd","cmd-read-direct","cmd-relative-batch-exit23"})
                if(!recorded.ContainsKey(kind)) {var blocked=new PilotCaseReceipt();blocked.Case=kind;blocked.Fatal=true;blocked.Status="blocked_run_failure_no_subject_created";blocked.NoCaseResourcesAllocated=true;result.Cases.Add(blocked);}
            result.AllFourOfflineCasesPassed=PilotOriginalSixPassed(result.Cases);
            result.CmdSentinelObservationPassed=PilotCmdSentinelPassed(result.Cases);
            result.CmdBatchObservationPassed=PilotCmdBatchPassed(result.Cases);
            result.CmdCwdRawObservationMatched=PilotCmdCwdRawMatched(result.Cases);
            result.CmdReadRawObservationMatched=PilotCmdReadRawMatched(result.Cases);
            result.CmdRelativeBatchRawObservationMatched=PilotCmdRelativeBatchRawMatched(result.Cases);
            // Best-effort error evidence never resolves or substitutes for the blocking journal.
            try {WritePilotEvidence(Path.Combine(evidence,"pilot-failure.json"),serializeRun(result),result.Broker,"failure");} catch {}
            throw new InvalidOperationException(result.Failure,failure);
        }
    }
}
