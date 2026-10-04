// Three fixed read-only metadata observations. No candidate authorizes execution.
using System;
using System.IO;
using System.ComponentModel;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    public sealed class ParentCandidateRow {
        public string Label,PathSource,PathOption,RequestedPath,ValidatedPath,AliasOf;
        public string Outcome="not_attempted",Stage="path",Failure,FailureStage,PreparationFailure;
        public string InitialIdentity,FinalIdentity;
        public uint Volume,Attributes;
        public long RawOpenError=-1;
        public bool Attempted,PathValidated,OpenAttempted,DirectoryHandleAcquired,InitialObjectVerified;
        public bool CheckerAttempted,CheckerCompleted,FinalIdentityRechecked,DirectoryCloseReturned;
        public bool ObservationCompleted,CleanupConfirmed,CandidateTrustVerified,OwnerComparisonObserved,OwnerIsCurrentBroker;
        public bool InitialOpenMissing,NormalTrustRejection;
        public readonly bool selected_for_execution=false;
        public DirectReceipt Checker=new DirectReceipt();
    }
    public sealed class ParentCandidateBatch {
        public ParentCandidateRow[] Rows;
        public bool ObservationCompleted,CleanupConfirmed;
        public readonly bool observation_only=true,selection_made=false,selected_for_execution=false,pilot_invoked=false;
        public readonly int created_directory_count=0,created_profile_count=0,created_process_count=0;
    }
    delegate void ParentCandidateOpenStep(ref IntPtr handle,string path,string label,DirectReceipt receipt);
    delegate FILE_INFO ParentCandidateObjectStep(IntPtr handle,string path,string identity,uint? volume);
    delegate void ParentCandidateTrustStep(IntPtr handle,string path,string identity,string label,DirectReceipt receipt);
    delegate bool ParentCandidateCloseStep(ref IntPtr handle,string label,DirectReceipt receipt);
    sealed class ParentCandidateOperations {
        public ParentCandidateOpenStep Open;
        public ParentCandidateObjectStep Inspect;
        public ParentCandidateTrustStep CheckParent;
        public ParentCandidateCloseStep Close;
    }
    static bool ParentCandidateNumber(DirectReceipt r,string key,long expected) {
        long value;return r.Numbers.TryGetValue(key,out value) && value==expected;
    }
    static bool ParentCandidatePathSyntax(string path) {
        if(String.IsNullOrEmpty(path) || path.Length<4 || path.Length>32700 ||
            !((path[0]>='A' && path[0]<='Z') || (path[0]>='a' && path[0]<='z')) || path[1]!=':' || path[2]!='\\') return false;
        if(path.IndexOf(':',2)>=0 || path.IndexOfAny(new char[]{'/', '"','\'','\0','\r','\n','%','!','&','|','<','>','^','?','*'})>=0) return false;
        string[] parts=path.Substring(3).TrimEnd('\\').Split('\\');
        foreach(string part in parts) {
            if(part.Length==0 || part=="." || part==".." || part.EndsWith(".",StringComparison.Ordinal) || part.EndsWith(" ",StringComparison.Ordinal)) return false;
            foreach(char c in part) if(Char.IsControl(c)) return false;
            try {PilotLeafName(part,false);}
            catch(ArgumentException) {return false;}
            catch(InvalidOperationException) {return false;}
        }
        return true;
    }
    static void PrepareParentCandidatePath(ParentCandidateRow row) {
        if(String.IsNullOrEmpty(row.RequestedPath)) {row.PreparationFailure="path_unavailable";return;}
        if(!ParentCandidatePathSyntax(row.RequestedPath)) {row.PreparationFailure="path_rejected";return;}
        try {row.ValidatedPath=PilotOwnedPath(row.RequestedPath);row.PathValidated=true;}
        catch(ArgumentException failure) {row.PreparationFailure="path_rejected";row.Failure=failure.GetType().Name+": "+failure.Message;}
        catch(Exception failure) {row.PreparationFailure="path_validation_uncertain";row.Failure=failure.GetType().Name+": "+failure.Message;}
    }
    static ParentCandidateBatch PrepareParentCandidateBatch(string runnerTemp,string localApplicationData,string lookupFailure) {
        var batch=new ParentCandidateBatch();
        batch.Rows=new ParentCandidateRow[]{
            new ParentCandidateRow {Label="runner_temp_control",PathSource="RUNNER_TEMP",PathOption="exact_supplied_value",RequestedPath=runnerTemp},
            new ParentCandidateRow {Label="local_application_data",PathSource="Environment.SpecialFolder.LocalApplicationData",PathOption="DoNotVerify",RequestedPath=localApplicationData},
            new ParentCandidateRow {Label="local_application_data_temp",PathSource="validated_LocalApplicationData_literal_Temp",PathOption="literal_child"}
        };
        PrepareParentCandidatePath(batch.Rows[0]);
        if(lookupFailure!=null) {batch.Rows[1].PreparationFailure="path_lookup_failed";batch.Rows[1].Failure=lookupFailure;}
        else PrepareParentCandidatePath(batch.Rows[1]);
        if(batch.Rows[1].PathValidated) {
            try {
                batch.Rows[2].RequestedPath=Path.Combine(batch.Rows[1].ValidatedPath,"Temp");
                PrepareParentCandidatePath(batch.Rows[2]);
                if(batch.Rows[2].PathValidated && (!String.Equals(Path.GetDirectoryName(batch.Rows[2].ValidatedPath),batch.Rows[1].ValidatedPath,StringComparison.Ordinal) ||
                    !String.Equals(Path.GetFileName(batch.Rows[2].ValidatedPath),"Temp",StringComparison.Ordinal))) {
                    batch.Rows[2].PathValidated=false;batch.Rows[2].PreparationFailure="path_validation_uncertain";
                }
            } catch(Exception failure) {batch.Rows[2].PreparationFailure="path_validation_uncertain";batch.Rows[2].Failure=failure.GetType().Name+": "+failure.Message;}
        } else batch.Rows[2].PreparationFailure="parent_path_unavailable";
        for(int i=0;i<batch.Rows.Length;i++) for(int j=0;j<i;j++)
            if(batch.Rows[i].PathValidated && batch.Rows[j].PathValidated &&
                String.Equals(batch.Rows[i].ValidatedPath,batch.Rows[j].ValidatedPath,StringComparison.OrdinalIgnoreCase)) {
                batch.Rows[i].AliasOf=batch.Rows[j].Label;break;
            }
        return batch;
    }
    static bool ParentCandidateCheckerCleanup(ParentCandidateRow row) {
        DirectReceipt r=row.Checker;string label=row.Label;
        foreach(KeyValuePair<string,long> item in r.Numbers) {
            if((item.Key.EndsWith("_close_confirmed",StringComparison.Ordinal) || item.Key.EndsWith("_free_confirmed",StringComparison.Ordinal)) && item.Value!=1) return false;
            if(item.Key.EndsWith("_unowned_output",StringComparison.Ordinal) && item.Value!=0) return false;
        }
        foreach(KeyValuePair<string,string> item in r.Identities)
            if(item.Key.EndsWith("_close_exception",StringComparison.Ordinal) || item.Key.EndsWith("_free_exception",StringComparison.Ordinal)) return false;
        if(row.CheckerAttempted && !ParentCandidateNumber(r,label+"_security_free_confirmed",1)) return false;
        if(r.Numbers.ContainsKey(label+"_broker_owner_query_confirmed")) {
            if(!ParentCandidateNumber(r,label+"_broker_owner_data_free_confirmed",1) ||
                !ParentCandidateNumber(r,label+"_broker_owner_token_close_confirmed",1)) return false;
            if(ParentCandidateNumber(r,label+"_broker_owner_token_open_success",1) &&
                !ParentCandidateNumber(r,label+"_broker_owner_token_close_error",0)) return false;
        }
        return true;
    }
    static bool ParentCandidateAclComplete(ParentCandidateRow row) {
        DirectReceipt r=row.Checker;string label=row.Label;long count,observed,needed,returned,control,rejected;string owner,reason;
        bool complete=ParentCandidateNumber(r,label+"_acl_observation_completed",1) &&
            r.Numbers.TryGetValue(label+"_dacl_ace_count",out count) && count>=-1 && count<=16384 &&
            r.Numbers.TryGetValue(label+"_acl_observed_ace_count",out observed) && observed==(count<0?0:count) &&
            ParentCandidateNumber(r,label+"_broker_owner_query_confirmed",1);
        if(!complete) return false;
        if(!ParentCandidateNumber(r,label+"_security_size_error",122) || !ParentCandidateNumber(r,label+"_security_read_error",0) ||
            !r.Numbers.TryGetValue(label+"_security_control_flags",out control) || control<0 || control>65535 ||
            !r.Identities.TryGetValue(label+"_owner_category",out owner) ||
            (owner!="current_broker" && owner!="system" && owner!="administrators" && owner!="creator_owner" && owner!="other")) return false;
        if(!ParentCandidateNumber(r,label+"_broker_owner_token_desired_access",8) ||
            !ParentCandidateNumber(r,label+"_broker_owner_token_open_success",1) || !ParentCandidateNumber(r,label+"_broker_owner_token_open_error",0) ||
            !ParentCandidateNumber(r,label+"_broker_owner_token_unowned_output",0) ||
            !ParentCandidateNumber(r,label+"_broker_owner_handle_query_success",1) || !ParentCandidateNumber(r,label+"_broker_owner_handle_query_error",0) ||
            !ParentCandidateNumber(r,label+"_broker_owner_handle_flags",0) || !ParentCandidateNumber(r,label+"_broker_owner_size_success",0) ||
            !ParentCandidateNumber(r,label+"_broker_owner_size_error",122) || !ParentCandidateNumber(r,label+"_broker_owner_read_success",1) ||
            !ParentCandidateNumber(r,label+"_broker_owner_read_error",0) ||
            !r.Numbers.TryGetValue(label+"_broker_owner_required_bytes",out needed) || needed<(IntPtr.Size==8?24:16) || needed>65536 ||
            !r.Numbers.TryGetValue(label+"_broker_owner_returned_bytes",out returned) || returned<(IntPtr.Size==8?24:16) || returned>needed) return false;
        // Validate completeness of the existing collector's metadata, not its trust policy.
        count=r.Numbers[label+"_dacl_ace_count"];
        if(!r.Numbers.TryGetValue(label+"_first_rejected_ace_index",out rejected) ||
            !r.Identities.TryGetValue(label+"_first_rejected_reason",out reason)) return false;
        if(reason=="none" || reason=="owner_or_dacl") {if(rejected!=-1) return false;}
        else if((reason!="unsupported_ace_shape" && reason!="unsupported_access_mask" && reason!="untrusted_write_grant") || rejected<0 || rejected>=count) return false;
        for(int index=0;index<count;index++) {
            string ace=label+"_ace_"+index,type,category;long native,flags,mask,qualifier,callback;
            if(!r.Identities.TryGetValue(ace+"_type",out type) || String.IsNullOrEmpty(type) ||
                !r.Numbers.TryGetValue(ace+"_native_type",out native) || native<0 || native>255 ||
                !r.Numbers.TryGetValue(ace+"_flags",out flags) || flags<0 || flags>255) return false;
            if(type=="CommonAce" || type=="ObjectAce" || type=="CompoundAce") {
                if(!r.Numbers.TryGetValue(ace+"_access_mask",out mask) || mask<0 || mask>UInt32.MaxValue ||
                    !r.Identities.TryGetValue(ace+"_sid_category",out category) ||
                    (category!="current_broker" && category!="system" && category!="administrators" && category!="creator_owner" && category!="other")) return false;
            } else if(type!="CustomAce") return false;
            if(type=="CommonAce" && (!r.Numbers.TryGetValue(ace+"_qualifier",out qualifier) || qualifier<0 || qualifier>3 ||
                !r.Numbers.TryGetValue(ace+"_callback",out callback) || (callback!=0 && callback!=1))) return false;
        }
        return true;
    }
    static bool ParentCandidateOrdinaryRejection(ParentCandidateRow row,Exception failure) {
        if(row.Stage!="parent_trust" || failure.GetType()!=typeof(InvalidOperationException) ||
            !ParentCandidateAclComplete(row) || !ParentCandidateNumber(row.Checker,row.Label+"_broker_owned",0)) return false;
        string reason;if(!row.Checker.Identities.TryGetValue(row.Label+"_first_rejected_reason",out reason)) return false;
        long rejected,count;
        if(!row.Checker.Numbers.TryGetValue(row.Label+"_first_rejected_ace_index",out rejected) ||
            !row.Checker.Numbers.TryGetValue(row.Label+"_dacl_ace_count",out count) ||
            (reason=="owner_or_dacl"?rejected!=-1:rejected<0 || rejected>=count)) return false;
        return (reason=="owner_or_dacl" && failure.Message=="pilot parent is not broker-owned") ||
            (reason=="unsupported_ace_shape" && failure.Message=="pilot parent ACL shape unsupported") ||
            (reason=="unsupported_access_mask" && failure.Message=="pilot parent ACL access mask unsupported") ||
            (reason=="untrusted_write_grant" && failure.Message=="pilot parent has an untrusted write grant");
    }
    static void FinalizeParentCandidateRow(ParentCandidateRow row,bool handleCleared) {
        DirectReceipt r=row.Checker;string label=row.Label;string category;
        row.OwnerComparisonObserved=r.Identities.TryGetValue(label+"_owner_category",out category);
        row.OwnerIsCurrentBroker=row.OwnerComparisonObserved && category=="current_broker";
        row.CleanupConfirmed=row.DirectoryCloseReturned && handleCleared && ParentCandidateNumber(r,label+"_close_confirmed",1) &&
            (!row.DirectoryHandleAcquired || ParentCandidateNumber(r,label+"_close_error",0)) && ParentCandidateCheckerCleanup(row);
        row.CandidateTrustVerified=row.CheckerCompleted && row.InitialObjectVerified && row.FinalIdentityRechecked && row.CleanupConfirmed &&
            row.Failure==null && row.RawOpenError==0 && ParentCandidateAclComplete(row) && ParentCandidateNumber(r,label+"_broker_owned",1);
        bool rejection=row.NormalTrustRejection && row.InitialObjectVerified && row.FinalIdentityRechecked;
        row.ObservationCompleted=row.CleanupConfirmed && (row.CandidateTrustVerified || rejection || row.InitialOpenMissing);
        row.Outcome=row.CandidateTrustVerified?"unchanged_parent_predicate_passed":
            row.ObservationCompleted?(row.InitialOpenMissing?"missing_initial_open":"unchanged_parent_predicate_rejected"):"observation_uncertain";
    }
    static void ObserveParentCandidateRow(ParentCandidateRow row,ParentCandidateOperations operations) {
        row.Attempted=true;
        if(!row.PathValidated) {
            row.Outcome=row.PreparationFailure??"path_validation_uncertain";
            row.CleanupConfirmed=true; // No open or allocation is attempted on this path.
            row.ObservationCompleted=row.Outcome=="path_unavailable" || row.Outcome=="path_rejected" || row.Outcome=="parent_path_unavailable";
            return;
        }
        IntPtr handle=IntPtr.Zero;
        try {
            row.Stage="open";row.OpenAttempted=true;
            operations.Open(ref handle,row.ValidatedPath,row.Label,row.Checker);
            row.DirectoryHandleAcquired=handle!=IntPtr.Zero;
            if(!row.DirectoryHandleAcquired) throw new InvalidOperationException("candidate open returned no owned handle");
            row.Stage="initial_object";
            FILE_INFO info=operations.Inspect(handle,row.ValidatedPath,null,null);
            row.InitialIdentity=info.volume+":"+info.indexHigh+":"+info.indexLow;
            row.Volume=info.volume;row.Attributes=info.attributes;row.InitialObjectVerified=true;
            row.Stage="parent_trust";row.CheckerAttempted=true;
            operations.CheckParent(handle,row.ValidatedPath,row.InitialIdentity,row.Label,row.Checker);
            row.CheckerCompleted=true;
        } catch(Exception failure) {
            row.DirectoryHandleAcquired=row.DirectoryHandleAcquired || handle!=IntPtr.Zero;
            row.Failure=failure.GetType().Name+": "+failure.Message;row.FailureStage=row.Stage;
            long error;bool openRecorded=row.Checker.Numbers.TryGetValue(row.Label+"_open_error",out error);
            var native=failure as Win32Exception;
            row.InitialOpenMissing=row.Stage=="open" && !row.DirectoryHandleAcquired && openRecorded && (error==2 || error==3) && native!=null && native.NativeErrorCode==error;
            row.NormalTrustRejection=ParentCandidateOrdinaryRejection(row,failure);
        } finally {
            try {
                if(row.InitialObjectVerified) {
                    row.Stage="final_identity";
                    FILE_INFO finalInfo=operations.Inspect(handle,row.ValidatedPath,row.InitialIdentity,row.Volume);
                    row.FinalIdentity=finalInfo.volume+":"+finalInfo.indexHigh+":"+finalInfo.indexLow;
                    if(row.FinalIdentity!=row.InitialIdentity) throw new InvalidOperationException("candidate final identity changed");
                    row.FinalIdentityRechecked=true;
                }
            } catch(Exception failure) {
                row.Failure=(row.Failure==null?"":row.Failure+"; ")+failure.GetType().Name+": "+failure.Message;row.FailureStage="final_identity";
            } finally {
                row.Stage="close";
                try {row.DirectoryCloseReturned=operations.Close(ref handle,row.Label,row.Checker);}
                catch(Exception failure) {
                    row.Failure=(row.Failure==null?"":row.Failure+"; ")+failure.GetType().Name+": "+failure.Message;row.FailureStage="close";
                    row.DirectoryCloseReturned=false;
                }
            }
        }
        long raw;if(row.Checker.Numbers.TryGetValue(row.Label+"_open_error",out raw)) row.RawOpenError=raw;
        FinalizeParentCandidateRow(row,handle==IntPtr.Zero);row.Stage="finished";
    }
    static ParentCandidateBatch RunParentCandidateObservations(ParentCandidateBatch batch,ParentCandidateOperations operations) {
        bool proceed=true;batch.ObservationCompleted=true;batch.CleanupConfirmed=true;
        foreach(ParentCandidateRow row in batch.Rows) {
            if(!proceed) {row.Outcome="not_attempted_prior_uncertainty";batch.ObservationCompleted=false;batch.CleanupConfirmed=false;continue;}
            try {ObserveParentCandidateRow(row,operations);}
            catch(Exception failure) {
                row.Failure=(row.Failure==null?"":row.Failure+"; ")+failure.GetType().Name+": "+failure.Message;
                row.Outcome="observation_uncertain";row.ObservationCompleted=false;row.CleanupConfirmed=false;row.CandidateTrustVerified=false;
            }
            batch.ObservationCompleted=row.ObservationCompleted && batch.ObservationCompleted;
            batch.CleanupConfirmed=row.CleanupConfirmed && batch.CleanupConfirmed;
            proceed=row.ObservationCompleted && row.CleanupConfirmed;
        }
        return batch;
    }
    public static ParentCandidateBatch ObserveParentCandidates(string runnerTemp) {
        string localApplicationData=null,lookupFailure=null;
        try {localApplicationData=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify);}
        catch(Exception failure) {lookupFailure=failure.GetType().Name+": "+failure.Message;}
        ParentCandidateBatch batch=PrepareParentCandidateBatch(runnerTemp,localApplicationData,lookupFailure);
        var operations=new ParentCandidateOperations {
            Open=delegate(ref IntPtr handle,string path,string label,DirectReceipt r) {PilotOpenHandle(ref handle,path,0x00020081,true,label,r);},
            Inspect=delegate(IntPtr handle,string path,string identity,uint? volume) {return PilotValidateObject(handle,path,true,identity,volume);},
            CheckParent=delegate(IntPtr handle,string path,string identity,string label,DirectReceipt r) {PilotValidateParent(handle,path,identity,label,r);},
            Close=delegate(ref IntPtr handle,string label,DirectReceipt r) {return PilotCloseHandle(ref handle,label,r);}
        };
        return RunParentCandidateObservations(batch,operations);
    }
}
