// Pure predicates used by the real coordinator and managed-only negative tests.
using System;

public static partial class BrokerDirectLauncher {
    static bool PilotMayResume(bool ordinaryWitness,bool ownershipCertain,bool profileOwned,PilotCaseReceipt row) {
        return row!=null && row.Launcher!=null && row.Policy=="accesscheck_signature_v1_ci" && row.Case!="ordinary" &&
            ordinaryWitness && ownershipCertain && profileOwned && !row.Fatal && row.AuthorityObserved &&
            row.Launcher.HostStdioClosed && VerifyPilotSignature(row.Launcher,false);
    }
    static bool PilotCleanupPreconditions(PilotCaseReceipt row) {
        return row!=null && !row.Fatal && row.IndividualResourceCleanupConfirmed && row.CaptureIntegrityConfirmed &&
            row.ProfileDeleteApiConfirmed && row.OwnedRootRemoved;
    }
    static bool PilotMayAdvance(PilotCaseReceipt row) {
        if(row==null || row.Fatal || row.Launcher==null) return false;
        if(row.NoCaseResourcesAllocated)
            return row.Status=="preparation_failed" && !row.Launcher.CreateAttempted && !row.Launcher.Created &&
                !row.Launcher.Assigned && !row.Launcher.Resumed && !row.CaseMarkerResolved;
        return PilotCleanupPreconditions(row) && row.CleanupPreconditionsConfirmed && row.CaseMarkerResolved && row.ScopedLifecycleCleanupConfirmed;
    }
    static void PilotCommitBoundary(bool resolved,bool failed,bool bound,Action verifyPending,Action verifyBinding,Action rename) {
        if(resolved || failed || !bound || verifyPending==null || verifyBinding==null || rename==null)
            throw new InvalidOperationException("only a current bound pending journal may commit");
        verifyPending();verifyBinding();rename();
    }

}
