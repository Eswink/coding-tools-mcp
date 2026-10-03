// Fixed CI parent selection. Metadata pins never become target inherited handles.
using System;
using System.IO;
using System.Collections.Generic;

public static partial class BrokerDirectLauncher {
    public sealed class SelectedParentReceipt {
        public string Policy="localappdata_temp_ci_v1",RequestedPath,ResolvedPath,Failure;
        public bool Acquired,FinalScanConfirmed,CloseAttempted,CloseConfirmed;
        public int PlannedHandles,AcquiredHandles,VerifiedGuards;
        public DirectReceipt Metadata=new DirectReceipt();
    }
    delegate void SelectedParentOpen(ref IntPtr handle,string path,uint access,string label,DirectReceipt receipt);
    delegate FILE_INFO SelectedParentInspect(IntPtr handle,string path,string identity,uint? volume);
    delegate void SelectedParentTrust(IntPtr handle,string path,string identity,string label,DirectReceipt receipt);
    delegate bool SelectedParentClose(ref IntPtr handle,string label,DirectReceipt receipt);
    sealed class SelectedParentOperations {
        public Func<string> Resolve;
        public SelectedParentOpen Open;
        public SelectedParentInspect Inspect;
        public SelectedParentTrust Trust;
        public SelectedParentClose Close;
    }
    static string SelectedParentFromKnownFolder(string local) {
        if(!ParentCandidatePathSyntax(local)) throw new ArgumentException("fixed LocalApplicationData path rejected");
        string exact=PilotOwnedPath(local);
        if(!String.Equals(exact,local,StringComparison.Ordinal)) throw new ArgumentException("known folder path must be exact");
        string selected=Path.Combine(exact,"Temp");
        if(!ParentCandidatePathSyntax(selected) || !String.Equals(Path.GetDirectoryName(selected),exact,StringComparison.Ordinal) ||
            !String.Equals(Path.GetFileName(selected),"Temp",StringComparison.Ordinal)) throw new ArgumentException("literal Temp child rejected");
        return selected;
    }
    public static string ResolvePilotSelectedPath() {
        return SelectedParentFromKnownFolder(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify));
    }
    static string[] SelectedParentChain(string selected) {
        if(!ParentCandidatePathSyntax(selected) || !String.Equals(PilotOwnedPath(selected),selected,StringComparison.Ordinal))
            throw new ArgumentException("selected parent must be exact and local");
        string[] parts=selected.Substring(3).Split('\\');
        if(parts.Length+1>32) throw new ArgumentException("selected ancestor count exceeds 32");
        var paths=new List<string>();string path=selected.Substring(0,3);paths.Add(path);
        foreach(string part in parts) {PilotLeafName(part,false);path=Path.Combine(path,part);paths.Add(path);}
        if(paths[paths.Count-1]!=selected) throw new ArgumentException("selected chain does not bind endpoint");
        return paths.ToArray();
    }
    static SelectedParentOperations SelectedParentNativeOperations() {
        return new SelectedParentOperations {
            Resolve=ResolvePilotSelectedPath,
            Open=delegate(ref IntPtr h,string p,uint access,string label,DirectReceipt r) {PilotOpenHandle(ref h,p,access,true,label,r);},
            Inspect=delegate(IntPtr h,string p,string identity,uint? volume) {return PilotValidateObject(h,p,true,identity,volume);},
            Trust=delegate(IntPtr h,string p,string identity,string label,DirectReceipt r) {PilotValidateParent(h,p,identity,label,r);},
            Close=delegate(ref IntPtr h,string label,DirectReceipt r) {return PilotCloseHandle(ref h,label,r);}
        };
    }
    sealed class PilotSelectedParent {
        public readonly SelectedParentReceipt Receipt;
        readonly SelectedParentOperations Operations;
        readonly List<IntPtr> Handles=new List<IntPtr>();
        readonly List<string> Identities=new List<string>();
        string[] Paths;
        uint Volume;
        bool Failed,Closed,CheckerAttempted,OwnershipUncertain;
        public PilotSelectedParent(string requested,SelectedParentReceipt receipt,SelectedParentOperations operations) {
            Receipt=receipt;Receipt.RequestedPath=requested;Operations=operations;
        }
        public void AcquireSelectedParent() {
            if(Closed || Failed || Paths!=null) throw new InvalidOperationException("selected parent lease is single-use");
            try {
                Receipt.ResolvedPath=Operations.Resolve();
                if(!String.Equals(Receipt.RequestedPath,Receipt.ResolvedPath,StringComparison.Ordinal)) throw new InvalidOperationException("independent selected parent resolution mismatch");
                Paths=SelectedParentChain(Receipt.ResolvedPath);Receipt.PlannedHandles=Paths.Length;
                for(int index=0;index<Paths.Length;index++) {
                    IntPtr handle=IntPtr.Zero;string label="selected_pin_"+index;
                    // Preserve an owned handle if validation inside Open throws after acquisition.
                    try {Operations.Open(ref handle,Paths[index],index==Paths.Length-1?0x00020081u:0x000000A0u,label,Receipt.Metadata);}
                    finally {
                        if(handle==new IntPtr(-1)) {OwnershipUncertain=true;handle=IntPtr.Zero;}
                        Handles.Add(handle);if(handle!=IntPtr.Zero) Receipt.AcquiredHandles++;
                    }
                    if(handle==IntPtr.Zero || handle==new IntPtr(-1)) throw new InvalidOperationException("selected parent open ownership unverified");
                    FILE_INFO info=Operations.Inspect(handle,Paths[index],null,index==0?(uint?)null:Volume);
                    if(index==0) Volume=info.volume;
                    string identity=info.volume+":"+info.indexHigh+":"+info.indexLow;
                    Identities.Add(identity);Receipt.Metadata.Identities[label+"_path"]=Paths[index];
                    Receipt.Metadata.Identities[label+"_identity"]=identity;
                    Receipt.Metadata.Numbers[label+"_attributes"]=info.attributes;
                    RecheckSelectedChain(); // Recheck all earlier pins after every literal child open.
                }
                CheckSelectedEndpoint();Receipt.Acquired=true;
            } catch(Exception failure) {MarkSelectedFailure(failure);throw;}
        }
        void RecheckSelectedChain() {
            if(Closed || Failed || Paths==null || Handles.Count!=Identities.Count) throw new InvalidOperationException("selected chain incomplete or unavailable");
            for(int index=0;index<Handles.Count;index++) {
                FILE_INFO info=Operations.Inspect(Handles[index],Paths[index],Identities[index],Volume);
                string identity=info.volume+":"+info.indexHigh+":"+info.indexLow;
                if(identity!=Identities[index]) throw new InvalidOperationException("selected pin identity changed");
                Receipt.Metadata.Identities["selected_pin_"+index+"_rechecked_identity"]=identity;
            }
        }
        void CheckSelectedEndpoint() {
            int last=Paths.Length-1;
            CheckerAttempted=true;
            Operations.Trust(Handles[last],Paths[last],Identities[last],"selected_parent",Receipt.Metadata);
            var observation=new ParentCandidateRow {Label="selected_parent",Checker=Receipt.Metadata,CheckerAttempted=true};
            if(!ParentCandidateAclComplete(observation) || !ParentCandidateCheckerCleanup(observation) ||
                !ParentCandidateNumber(Receipt.Metadata,"selected_parent_broker_owned",1))
                throw new InvalidOperationException("selected parent strict checker evidence incomplete");
        }
        public void GuardSelectedRecovery(Action<string[]> guard,string[] allowed) {
            if(guard==null || !Receipt.Acquired || Closed || Failed) throw new InvalidOperationException("active selected parent and mandatory recovery guard required");
            try {
                RecheckSelectedChain();CheckSelectedEndpoint();
                guard(allowed);
                RecheckSelectedChain();CheckSelectedEndpoint();Receipt.VerifiedGuards++;
            } catch(Exception failure) {MarkSelectedFailure(failure);throw;}
        }
        void MarkSelectedFailure(Exception failure) {
            Failed=true;Receipt.Failure=(Receipt.Failure==null?"":Receipt.Failure+"; ")+failure.GetType().Name+": "+failure.Message;
        }
        public bool CloseSelectedParent() {
            if(Closed) return Receipt.CloseConfirmed;
            Closed=true;Receipt.CloseAttempted=true;bool confirmed=true;
            for(int index=Handles.Count-1;index>=0;index--) {
                IntPtr owned=Handles[index];Handles[index]=IntPtr.Zero;
                if(owned==IntPtr.Zero) continue;
                // Transfer before the single close attempt, including exceptions. Never retry an uncertain value.
                try {if(!Operations.Close(ref owned,"selected_pin_"+index,Receipt.Metadata) || owned!=IntPtr.Zero) confirmed=false;}
                catch(Exception failure) {confirmed=false;MarkSelectedFailure(failure);}
            }
            var observation=new ParentCandidateRow {Label="selected_parent",Checker=Receipt.Metadata,CheckerAttempted=CheckerAttempted};
            confirmed=confirmed && !OwnershipUncertain && ParentCandidateCheckerCleanup(observation);
            Receipt.CloseConfirmed=confirmed;
            if(!confirmed) {Failed=true;if(Receipt.Failure==null) Receipt.Failure="selected parent close unconfirmed";}
            return confirmed;
        }
    }
    public static SelectedParentReceipt CheckSelectedParentRecovery(string selected,Action<string[]> guard,string[] allowed) {
        var receipt=new SelectedParentReceipt();var lease=new PilotSelectedParent(selected,receipt,SelectedParentNativeOperations());
        try {lease.AcquireSelectedParent();lease.GuardSelectedRecovery(guard,allowed);receipt.FinalScanConfirmed=true;}
        catch(Exception failure) {if(receipt.Failure==null) receipt.Failure=failure.GetType().Name+": "+failure.Message;}
        finally {lease.CloseSelectedParent();}
        return receipt;
    }
}
