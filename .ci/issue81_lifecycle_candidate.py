"""One-shot, reviewable source preparation; never a product runtime or release tool."""
from pathlib import Path
import sys

ROOT = Path('services/native-link')

def replace(path, old, new, count=1):
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    if text.count(old) != count:
        raise RuntimeError(f'exact source mismatch: {path}: {old[:100]!r}')
    p.write_text(text.replace(old, new), encoding='utf-8', newline='\n')

def prepare():
    replace('src/lib.rs', 'mod wire;', 'mod wire;\nmod lifecycle;\npub use lifecycle::ConnectionStatus;\n#[cfg(test)]\nmod tests;\n#[cfg(test)]\nmod lifecycle_tests;')
    replace('src/journal.rs', 'state_file.by_ref()', 'Read::by_ref(&mut state_file)')
    replace('src/journal.rs', 'log.by_ref()', 'Read::by_ref(&mut log)')
    replace('src/journal.rs', '    inner:Mutex<Inner>,', '    inner:Mutex<Inner>,\n    pub(crate) lifecycle:Arc<crate::lifecycle::Lifecycle>,')
    replace('src/journal.rs', 'key,_lock:lock,inner:', 'key,_lock:lock,lifecycle:crate::lifecycle::Lifecycle::new(false),inner:', 2)
    old = '''    pub(crate) fn recovery_projection(&self)->Result<Option<Offered>> {
        let inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        if inner.poisoned {return Err(LinkError::Journal);}
        Ok(inner.state.offered.clone().or_else(||inner.state.confirmed.clone()))
    }'''
    new = '''    pub(crate) fn projection_state(&self)->Result<ProjectionState> {
        let inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        if inner.poisoned {return Err(LinkError::Journal);}
        Ok((inner.state.confirmed.clone(),inner.state.offered.clone()))
    }
    pub(crate) fn check_binding(&self,cfg:&DeviceConfig,key:&DeviceKey)->Result<()> {
        let inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        if inner.poisoned || inner.state.binding!=cfg.fingerprint(key)? {return Err(LinkError::Journal);}
        Ok(())
    }'''
    replace('src/journal.rs', old, new)
    replace('src/journal.rs', 'const MAX_REQUESTS:usize=4096;', 'pub(crate) type ProjectionState = (Option<Offered>, Option<Offered>);\n\nconst MAX_REQUESTS:usize=4096;')
    replace('src/transport.rs', '    pub fn requires_local_recovery(&self)->bool {', '    pub fn connection_status(&self)->crate::ConnectionStatus { self.journal.lifecycle.status() }\n    pub fn requires_local_recovery(&self)->bool {')
    (ROOT/'Cargo.lock').write_bytes(Path('services/cloud-gateway/Cargo.lock').read_bytes())

def fix():
    # These changes operate on the deliberately unformatted prepared source.
    replace('src/journal.rs', '    binding:[u8;32],\n    revision:i64,', '    binding:[u8;32],\n    log_sequence:u64,\n    log_head:[u8;32],\n    revision:i64,')
    replace('src/journal.rs', 'let state=State {version:1,binding:cfg.fingerprint(&key)?,revision:0,', 'let mut state=State {version:2,binding:cfg.fingerprint(&key)?,log_sequence:1,log_head:[0;32],revision:0,')
    replace('src/journal.rs', '        write_initial_state(root,&key,&state)?;', '        state.log_head=hash;\n        write_initial_state(root,&key,&state)?;')
    replace('src/journal.rs', 'if state.version!=1 ||', 'if state.version!=2 ||')
    replace('src/journal.rs', '        if sequence==0 {return Err(LinkError::Journal);}', '        if sequence==0 || state.log_sequence!=sequence || state.log_head!=previous {return Err(LinkError::Journal);}')
    replace('src/journal.rs', 'lifecycle:crate::lifecycle::Lifecycle::new(false),inner:Mutex::new(Inner{state,log,sequence,previous,seen,poisoned:false})', 'lifecycle:crate::lifecycle::Lifecycle::new(seen.values().any(|s|s.outcome.is_none())),inner:Mutex::new(Inner{state,log,sequence,previous,seen,poisoned:false})')
    replace('src/journal.rs', '        inner.sequence=sequence;inner.previous=hash;Ok(())', '        let mut state=inner.state.clone();\n        state.log_sequence=sequence;state.log_head=hash;\n        self.save(inner,state)?;\n        inner.sequence=sequence;inner.previous=hash;Ok(())')
    replace('src/transport.rs', '        self.quarantined.lock().map(|v|!v.is_empty()).unwrap_or(true)', '        self.journal.lifecycle.status().recovery_required || self.quarantined.lock().map(|v|!v.is_empty()).unwrap_or(true)')
    replace('src/transport.rs', '    pub async fn run(&self,stop:CancellationToken)->Result<()> {\n        let mut attempts=0u32;', '''    pub async fn run(&self,stop:CancellationToken)->Result<()> {
        let _owner=self.journal.lifecycle.begin()?;
        let outcome=self.run_connections(stop).await;
        self.journal.lifecycle.drain(Duration::from_secs(5)).await?;
        outcome
    }
    async fn run_connections(&self,stop:CancellationToken)->Result<()> {
        let mut attempts=0u32;''')
    replace('src/transport.rs', '            if stop.is_cancelled(){return Ok(());}', '            if stop.is_cancelled(){return Ok(());}\n            if self.requires_local_recovery(){return Err(LinkError::Journal);}')
    replace('src/transport.rs', 'let host=self.host.clone();let journal=self.journal.clone();let live=session.clone();let quarantine=self.quarantined.clone();', 'let host=self.host.clone();let journal=self.journal.clone();let live=session.clone();let quarantine=self.quarantined.clone();\n                            let worker=self.journal.lifecycle.worker()?;')
    replace('src/transport.rs', '                                                let result=bounded_result(result);', '''                                                let result=match result {
                                                    Ok(value)=>bounded_result(Ok(value)),
                                                    Err(_)=>uncertain("LOCAL_WORKER_OUTCOME_UNKNOWN"),
                                                };
                                                if result["process_may_be_running"]==true || result["execution_outcome"]=="unknown" {
                                                    quarantine_permit(&quarantine,&mut permit);
                                                    return Finished::Execution(ExecutionReply{binding:request.binding,result});
                                                }''')
    replace('src/transport.rs', '                                    Ok(Ok(ClaimOutcome::AlreadyClaimed{..}))=>uncertain("REQUEST_ALREADY_CLAIMED"),', '''                                    Ok(Ok(ClaimOutcome::AlreadyClaimed{completed:true}))=> {
                                        let mut value=crate::tool_error("REQUEST_ALREADY_COMPLETED");
                                        value["execution_outcome"]=serde_json::json!("completed_without_output");value
                                    },
                                    Ok(Ok(ClaimOutcome::AlreadyClaimed{completed:false}))=>uncertain("REQUEST_ALREADY_CLAIMED"),''')
    replace('src/transport.rs', '                                    _=>crate::tool_error("LOCAL_JOURNAL_REJECTED"),', '                                    Ok(Err(LinkError::Capacity))=>crate::tool_error("LOCAL_CAPACITY_EXHAUSTED"),\n                                    _=>uncertain("LOCAL_JOURNAL_REJECTED"),')
    replace('src/transport.rs', '                                Finished::Execution(ExecutionReply{binding:request.binding,result})', '                                if result["process_may_be_running"]!=true && result["execution_outcome"]!="unknown" {worker.finish();}\n                                Finished::Execution(ExecutionReply{binding:request.binding,result})')
    replace('src/transport.rs', 'let permit=permit.map_err(|_|LinkError::Capacity)?;let host=self.host.clone();let live=session.clone();', 'let permit=permit.map_err(|_|LinkError::Capacity)?;let host=self.host.clone();let live=session.clone();\n                            let worker=self.journal.lifecycle.worker()?;')
    replace('src/transport.rs', '                                Finished::Approval(ApprovalReply{binding,result:bounded_result(result.unwrap_or(Err(LinkError::NotApproved)))})', '                                worker.finish();\n                                Finished::Approval(ApprovalReply{binding,result:bounded_result(result.unwrap_or(Err(LinkError::NotApproved)))})')
    # File-scoped projection/one_session impacts reviewed in run 36522683379.
    # This is an argument grouping only: retain every signed field and bound.
    replace('src/config.rs', 'at:i64,until:i64,state:&Projected)->Result<SignedPayload> {', 'window:std::ops::Range<i64>,state:&Projected)->Result<SignedPayload> {\n        let (at,until)=(window.start,window.end);')
    replace('src/transport.rs', 'self.key.projection(&self.cfg,boot,&nonce,prepared.offered.revision,crate::now()?,until,&prepared.offered.state)?', 'self.key.projection(&self.cfg,boot,&nonce,prepared.offered.revision,crate::now()?..until,&prepared.offered.state)?')
    replace('src/lib.rs', 'mod lifecycle_tests;', 'mod lifecycle_tests;\n#[cfg(test)]\nmod projection_window_tests;')

if __name__ == '__main__':
    {'prepare': prepare, 'fix': fix}[sys.argv[1]]()
