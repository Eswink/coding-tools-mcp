// Cleanup attempts for one subject never skip the other subject's cleanup.
using System;
using System.IO;
using System.Runtime.InteropServices;

public static partial class BrokerDirectLauncher {
    static bool QualificationCleanupStep(Action operation,string label,DirectReceipt r) {
        try {operation();return true;}
        catch(Exception failure) {r.Identities[label+"_exception"]=failure.GetType().Name;return false;}
    }
    static bool StopQualificationSubject(QualificationSubject s) {
        DirectReceipt r=s.Receipt;bool certain=s.OwnershipCertain;
        certain=QualificationCleanupStep(delegate {certain=CloseOwned(ref s.SourceToken,"token",r) && certain;},"source_token_cleanup",r) && certain;
        if(s.Process.process!=IntPtr.Zero) {
            certain=QualificationCleanupStep(delegate {
                uint before=WaitForSingleObject(s.Process.process,0);r.Numbers["cleanup_initial_process_wait"]=before;
                if(before!=WAIT_OBJECT_0) {
                    bool terminated=TerminateProcess(s.Process.process,91);
                    r.Numbers["terminate_process_error"]=terminated?0:Marshal.GetLastWin32Error();
                    if(!terminated) certain=false;
                }
                uint stopped=WaitForSingleObject(s.Process.process,5000);r.Numbers["cleanup_final_process_wait"]=stopped;
                s.ProcessStopped=stopped==WAIT_OBJECT_0;
                r.Numbers["exact_process_stop_confirmed"]=s.ProcessStopped?1:0;
            },"exact_process_stop",r) && certain;
            certain=s.ProcessStopped && certain;
        } else {s.ProcessStopped=!r.Created;r.Numbers["exact_process_stop_applicable"]=r.Created?1:0;}
        if(s.Job!=IntPtr.Zero) {
            certain=QualificationCleanupStep(delegate {
                bool terminated=TerminateJobObject(s.Job,91);r.Numbers["terminate_job_error"]=terminated?0:Marshal.GetLastWin32Error();
                if(!terminated) certain=false;
                for(int attempt=0;attempt<250;attempt++) {
                    JOB_ACCOUNTING accounting;
                    bool ok=QueryInformationJobObject(s.Job,1,out accounting,(uint)Marshal.SizeOf(typeof(JOB_ACCOUNTING)),IntPtr.Zero);
                    r.Numbers["job_query_error"]=ok?0:Marshal.GetLastWin32Error();
                    if(!ok) break;
                    r.Numbers["job_active_processes"]=accounting.activeProcesses;
                    if(accounting.activeProcesses==0) {s.JobDrained=true;break;}
                    System.Threading.Thread.Sleep(20);
                }
            },"job_drain",r) && certain;
            certain=s.JobDrained && certain;
        } else {s.JobDrained=!r.Created;}
        r.Drained=s.JobDrained;
        certain=QualificationCleanupStep(delegate {certain=CloseOwned(ref s.Process.thread,"thread",r) && certain;},"thread_cleanup",r) && certain;
        certain=QualificationCleanupStep(delegate {certain=CloseOwned(ref s.Process.process,"process",r) && certain;},"process_cleanup",r) && certain;
        certain=QualificationCleanupStep(delegate {certain=CloseOwned(ref s.Job,"job",r) && certain;},"job_cleanup",r) && certain;
        certain=QualificationCleanupStep(delegate {
            if(s.Sid!=IntPtr.Zero) {
                IntPtr sid=s.Sid;s.Sid=IntPtr.Zero;
                bool freed=FreeSid(sid)==IntPtr.Zero;r.Numbers["profile_sid_memory_freed"]=freed?1:0;
                if(!freed) certain=false;
            }
        },"profile_sid_memory_cleanup",r) && certain;
        r.CleanupConfirmed=false; // Intentionally unresumed/unadopted; retain owned profile/root.
        r.Numbers["individual_stop_drain_close_confirmed"]=certain?1:0;
        return certain;
    }
    public sealed class QualificationPairReceipt {
        public string Failure;
        public bool ObservationOnly=true,VerifierAdopted=false,ObservationsCollected,IndividualResourceCleanupConfirmed;
        public bool CleanupConfirmed=false,RecoveryRetained=true;
        public DirectReceipt[] Subjects;
    }
    public static QualificationPairReceipt ObserveQualificationPair(string fixture,string parent,int port) {
        var subjects=new QualificationSubject[]{NewQualificationSubject(parent,"ordinary"),NewQualificationSubject(parent,"lpac")};
        var pair=new QualificationPairReceipt();pair.Subjects=new DirectReceipt[]{subjects[0].Receipt,subjects[1].Receipt};
        string recovery=Path.Combine(parent,"cleanup-uncertain.txt");
        File.WriteAllText(recovery,"Observation-only pair pending; all owned profiles/roots retained until explicit recovery");
        try {
            PrepareQualificationSubject(subjects[0],fixture,false,port);
            PrepareQualificationSubject(subjects[1],fixture,true,port);
            bool sourcesValid=true;
            foreach(QualificationSubject s in subjects) sourcesValid=ObserveQualificationSource(s) && sourcesValid;
            if(!sourcesValid) throw new InvalidOperationException("paired restricted source properties unverified");
            foreach(QualificationSubject s in subjects) {
                s.Receipt.Stage="observe_identification_duplicate";
                bool observerClosed=ObserveAccessCheckToken(s.SourceToken,s.Receipt.ProfileSid,s.Receipt);
                s.OwnershipCertain=observerClosed && s.OwnershipCertain;
                if(!observerClosed) throw new InvalidOperationException("paired observer cleanup uncertain");
            }
            pair.ObservationsCollected=true;
            // No result can authorize assignment or resume in this qualification entry.
        } catch(Exception failure) {pair.Failure=failure.GetType().Name+": "+failure.Message;}
        finally {
            bool certain=true;
            foreach(QualificationSubject s in subjects) {
                // Each subject owns its cleanup, even when the other subject failed.
                try {certain=StopQualificationSubject(s) && certain;}
                catch(Exception failure) {certain=false;s.Receipt.Identities["cleanup_unhandled_exception"]=failure.GetType().Name;}
            }
            bool stoppedAndDrained=true;
            foreach(QualificationSubject s in subjects) stoppedAndDrained=s.ProcessStopped && s.JobDrained && stoppedAndDrained;
            if(stoppedAndDrained) {
                foreach(QualificationSubject s in subjects) {
                    foreach(string file in new string[]{"stdout.txt","stderr.txt"}) {
                        try {certain=CaptureOwnedFile(s.Workspace,s.Parent,file,s.Receipt) && certain;}
                        catch(Exception failure) {certain=false;s.Receipt.Identities["capture_"+file+"_exception"]=failure.GetType().Name;}
                    }
                }
            }
            pair.IndividualResourceCleanupConfirmed=certain && stoppedAndDrained;
            // Deliberately never clear the marker, delete a profile/root, or claim full cleanup.
            File.WriteAllText(recovery,"Observation-only qualification retained; individual stop/drain/close confirmed="+
                pair.IndividualResourceCleanupConfirmed+"; ordinary="+subjects[0].Root+"/"+subjects[0].Profile+
                "; lpac="+subjects[1].Root+"/"+subjects[1].Profile);
        }
        return pair;
    }
}
