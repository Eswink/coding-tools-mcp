//! Protected native metadata only. No command, argument, result or workspace path is persisted.
use crate::{canonical::digest_json,wire::{ExecutionRequest,Projected},DeviceConfig,DeviceKey,LinkError,Result};
use fs2::FileExt;
use serde::{Deserialize,Serialize};
use sha2::{Digest,Sha256};
use std::{collections::BTreeMap,fs::{File,OpenOptions},io::{Read,Write},path::{Path,PathBuf},sync::{Arc,Mutex}};
use uuid::Uuid;

const MAX_REQUESTS:usize=4096;
const MAX_LOG_BYTES:u64=8*1024*1024;
const MAX_RECORD:usize=4096;
const MAX_STATE:usize=32768;

#[derive(Clone,Debug,PartialEq,Eq)]
pub enum ClaimOutcome { Fresh, AlreadyClaimed { completed:bool } }
#[derive(Clone,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Offered {
    pub revision:i64,
    pub state:Projected,
    pub native_epoch:u64,
    pub native_revision:u64,
    pub execution_generation:u64,
}
#[derive(Clone,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
struct State {
    version:u8,
    binding:[u8;32],
    revision:i64,
    authority_epoch:i64,
    confirmed:Option<Offered>,
    offered:Option<Offered>,
}
#[derive(Clone,Serialize,Deserialize)]
#[serde(tag="kind",rename_all="snake_case",deny_unknown_fields)]
enum Entry {
    Header { binding:[u8;32] },
    Claim { request:Uuid, identity:[u8;32] },
    Completed { request:Uuid, identity:[u8;32], outcome:[u8;32] },
}
#[derive(Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
struct Record { sequence:u64, previous:[u8;32], entry:Entry }
#[derive(Clone)]
struct Seen { identity:[u8;32], outcome:Option<[u8;32]> }
struct Inner {
    state:State,
    log:File,
    sequence:u64,
    previous:[u8;32],
    seen:BTreeMap<Uuid,Seen>,
    poisoned:bool,
}

/// The desktop supplies its private application-data directory, never a workspace/model path.
/// Unix modes and all final-path reparse/symlink boundaries are checked here. The Windows
/// desktop must first create this directory using its user-only native storage ACL policy.
pub struct Journal {
    root:PathBuf,
    key:Arc<DeviceKey>,
    _lock:File,
    inner:Mutex<Inner>,
}
impl std::fmt::Debug for Journal {
    fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {f.write_str("Journal([REDACTED])")}
}
impl Journal {
    /// Explicit enrollment/configuration only. Startup uses open_existing and never recreates history.
    pub fn create(root:&Path,cfg:&DeviceConfig,key:Arc<DeviceKey>)->Result<Self> {
        check_root(root)?;
        let lock=open_file(&root.join("owner.lock"),true,true)?;
        lock.try_lock_exclusive().map_err(|_|LinkError::Journal)?;
        let mut log=open_file(&root.join("requests.log"),true,true)?;
        let state=State {version:1,binding:cfg.fingerprint(&key)?,revision:0,authority_epoch:1,confirmed:None,offered:None};
        let (bytes,hash)=encode_record(&key,1,[0;32],Entry::Header{binding:state.binding})?;
        log.write_all(&bytes).and_then(|()|log.sync_all()).map_err(|_|LinkError::Journal)?;
        write_initial_state(root,&key,&state)?;
        sync_directory(root)?;
        Ok(Self{root:root.into(),key,_lock:lock,inner:Mutex::new(Inner{state,log,sequence:1,previous:hash,seen:BTreeMap::new(),poisoned:false})})
    }
    pub fn open_existing(root:&Path,cfg:&DeviceConfig,key:Arc<DeviceKey>)->Result<Self> {
        check_root(root)?;
        let lock=open_file(&root.join("owner.lock"),false,true)?;
        lock.try_lock_exclusive().map_err(|_|LinkError::Journal)?;
        let mut state_file=open_file(&root.join("projection.state"),false,false)?;
        let mut data=Vec::new();state_file.by_ref().take((MAX_STATE+65) as u64).read_to_end(&mut data).map_err(|_|LinkError::Journal)?;
        if data.len()<65 || data.len()>MAX_STATE+64 {return Err(LinkError::Journal);}
        let n=data.len()-64;key.verify_journal(&data[..n],&data[n..])?;
        let state:State=serde_json::from_slice(&data[..n]).map_err(|_|LinkError::Journal)?;
        if state.version!=1 || state.binding!=cfg.fingerprint(&key)? || state.revision<0 || state.authority_epoch<=0
            || state.confirmed.as_ref().is_some_and(|s|s.revision>state.revision)
            || state.offered.as_ref().is_some_and(|s|s.revision>state.revision) {return Err(LinkError::Journal);}
        let mut log=open_file(&root.join("requests.log"),false,true)?;
        if log.metadata().map_err(|_|LinkError::Journal)?.len()>MAX_LOG_BYTES {return Err(LinkError::Journal);}
        let mut raw=Vec::new();log.by_ref().take(MAX_LOG_BYTES+1).read_to_end(&mut raw).map_err(|_|LinkError::Journal)?;
        let mut offset=0;let mut sequence=0;let mut previous=[0;32];let mut seen:BTreeMap<Uuid,Seen>=BTreeMap::new();
        while offset<raw.len() {
            if raw.len()-offset<4 {return Err(LinkError::Journal);}
            let n=u32::from_be_bytes(raw[offset..offset+4].try_into().map_err(|_|LinkError::Journal)?) as usize;
            if n==0 || n>MAX_RECORD || raw.len()-offset<4+n+64 {return Err(LinkError::Journal);}
            let start=offset+4;let end=start+n;
            key.verify_journal(&raw[start..end],&raw[end..end+64])?;
            let r:Record=serde_json::from_slice(&raw[start..end]).map_err(|_|LinkError::Journal)?;
            if sequence==u64::MAX || r.sequence!=sequence+1 || r.previous!=previous {return Err(LinkError::Journal);}
            match r.entry {
                Entry::Header{binding} if sequence==0 && binding==state.binding=>{},
                Entry::Claim{request,identity} if sequence>0 && !request.is_nil() && !seen.contains_key(&request) && seen.len()<MAX_REQUESTS=>{
                    seen.insert(request,Seen{identity,outcome:None});
                },
                Entry::Completed{request,identity,outcome} if sequence>0=>{
                    let s=seen.get_mut(&request).ok_or(LinkError::Journal)?;
                    if s.identity!=identity || s.outcome.is_some() {return Err(LinkError::Journal);}
                    s.outcome=Some(outcome);
                },
                _=>return Err(LinkError::Journal),
            }
            offset=end+64;previous=Sha256::digest(&raw[start-4..offset]).into();sequence=r.sequence;
        }
        if sequence==0 {return Err(LinkError::Journal);}
        // A signed incomplete tail is never truncated or interpreted as absence of a claim.
        Ok(Self{root:root.into(),key,_lock:lock,inner:Mutex::new(Inner{state,log,sequence,previous,seen,poisoned:false})})
    }
    pub fn claim(&self,request:&ExecutionRequest)->Result<ClaimOutcome> {
        let id=request.binding.request_id;
        if id.is_nil() {return Err(LinkError::Protocol);}
        let identity=request_identity(request)?;
        let mut inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        if inner.poisoned {return Err(LinkError::Journal);}
        if let Some(seen)=inner.seen.get(&id) {
            if seen.identity!=identity {return Err(LinkError::ReplayConflict);}
            return Ok(ClaimOutcome::AlreadyClaimed{completed:seen.outcome.is_some()});
        }
        if inner.seen.len()>=MAX_REQUESTS {return Err(LinkError::Capacity);}
        self.append(&mut inner,Entry::Claim{request:id,identity})?;
        inner.seen.insert(id,Seen{identity,outcome:None});
        Ok(ClaimOutcome::Fresh)
    }
    pub fn complete(&self,request:&ExecutionRequest,result:&serde_json::Value)->Result<()> {
        let identity=request_identity(request)?;let outcome=digest_json(result,crate::wire::MAX_RESULT)?;
        let mut inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        let seen=inner.seen.get(&request.binding.request_id).ok_or(LinkError::Journal)?;
        if seen.identity!=identity {return Err(LinkError::ReplayConflict);}
        if let Some(old)=seen.outcome {return if old==outcome {Ok(())}else{Err(LinkError::ReplayConflict)};}
        self.append(&mut inner,Entry::Completed{request:request.binding.request_id,identity,outcome})?;
        inner.seen.get_mut(&request.binding.request_id).ok_or(LinkError::Journal)?.outcome=Some(outcome);Ok(())
    }
    fn append(&self,inner:&mut Inner,entry:Entry)->Result<()> {
        if inner.poisoned {return Err(LinkError::Journal);}
        let sequence=inner.sequence.checked_add(1).ok_or(LinkError::Journal)?;
        let (bytes,hash)=encode_record(&self.key,sequence,inner.previous,entry)?;
        if inner.log.metadata().map_err(|_|LinkError::Journal)?.len().checked_add(bytes.len() as u64).is_none_or(|n|n>MAX_LOG_BYTES) {return Err(LinkError::Capacity);}
        if inner.log.write_all(&bytes).and_then(|()|inner.log.sync_all()).is_err() {inner.poisoned=true;return Err(LinkError::Journal);}
        inner.sequence=sequence;inner.previous=hash;Ok(())
    }
    pub(crate) fn recovery_projection(&self)->Result<Option<Offered>> {
        let inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        if inner.poisoned {return Err(LinkError::Journal);}
        Ok(inner.state.offered.clone().or_else(||inner.state.confirmed.clone()))
    }
    pub(crate) fn next_epoch(&self)->Result<i64> {
        let mut inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        let mut state=inner.state.clone();state.authority_epoch=state.authority_epoch.checked_add(1).ok_or(LinkError::Journal)?;
        let value=state.authority_epoch;self.save(&mut inner,state)?;Ok(value)
    }
    pub(crate) fn offer(&self,mut offered:Offered)->Result<Offered> {
        let mut inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        let mut state=inner.state.clone();state.revision=state.revision.checked_add(1).ok_or(LinkError::Journal)?;
        if offered.state.authority_epoch>state.authority_epoch || offered.state.authority_epoch<=0 {return Err(LinkError::Journal);}
        offered.revision=state.revision;state.offered=Some(offered.clone());
        self.save(&mut inner,state)?;Ok(offered)
    }
    pub(crate) fn acknowledge(&self,revision:i64)->Result<()> {
        let mut inner=self.inner.lock().map_err(|_|LinkError::Journal)?;
        let mut state=inner.state.clone();let offered=state.offered.take().ok_or(LinkError::Protocol)?;
        if offered.revision!=revision {return Err(LinkError::Protocol);}
        state.confirmed=Some(offered);self.save(&mut inner,state)
    }
    fn save(&self,inner:&mut Inner,state:State)->Result<()> {
        if inner.poisoned {return Err(LinkError::Journal);}
        let temp=self.root.join(format!(".projection-{}.tmp",Uuid::new_v4()));
        let operation=||->Result<()> {
            let raw=state_bytes(&self.key,&state)?;
            let mut file=open_file(&temp,true,true)?;
            file.write_all(&raw).and_then(|()|file.sync_all()).map_err(|_|LinkError::Journal)?;
            drop(file);
            check_file(&self.root.join("projection.state"))?;
            std::fs::rename(&temp,self.root.join("projection.state")).map_err(|_|LinkError::Journal)?;
            sync_directory(&self.root)
        };
        if operation().is_err() {inner.poisoned=true;return Err(LinkError::Journal);}
        inner.state=state;Ok(())
    }
}
fn request_identity(r:&ExecutionRequest)->Result<[u8;32]> {
    // Reconnection cannot turn an existing request into new work. Only its channel changes.
    digest_json(&serde_json::json!({"id":r.binding.request_id,"connector":r.binding.peer.connector,
        "device":r.binding.peer.device,"device_epoch":r.binding.peer.device_epoch,
        "grant":r.binding.grant_id,"epoch":r.binding.authority_epoch,"conversation":r.binding.conversation,
        "scope":r.binding.scope,"tool":r.binding.tool,"arguments":r.binding.arguments_hash,
        "deadline":r.binding.deadline}),2048)
}
fn encode_record(key:&DeviceKey,sequence:u64,previous:[u8;32],entry:Entry)->Result<(Vec<u8>,[u8;32])> {
    let raw=serde_json::to_vec(&Record{sequence,previous,entry}).map_err(|_|LinkError::Journal)?;
    if raw.len()>MAX_RECORD {return Err(LinkError::Journal);}
    let mut bytes=(raw.len() as u32).to_be_bytes().to_vec();bytes.extend_from_slice(&raw);bytes.extend_from_slice(&key.journal_signature(&raw));
    let hash=Sha256::digest(&bytes).into();Ok((bytes,hash))
}
fn state_bytes(key:&DeviceKey,state:&State)->Result<Vec<u8>> {
    let mut raw=serde_json::to_vec(state).map_err(|_|LinkError::Journal)?;
    if raw.len()>MAX_STATE {return Err(LinkError::Journal);}
    let signature=key.journal_signature(&raw);raw.extend_from_slice(&signature);Ok(raw)
}
fn write_initial_state(root:&Path,key:&DeviceKey,state:&State)->Result<()> {
    let mut f=open_file(&root.join("projection.state"),true,true)?;
    f.write_all(&state_bytes(key,state)?).and_then(|()|f.sync_all()).map_err(|_|LinkError::Journal)
}
fn check_root(root:&Path)->Result<()> {
    let m=std::fs::symlink_metadata(root).map_err(|_|LinkError::Journal)?;
    if !root.is_absolute() || !m.is_dir() || m.file_type().is_symlink()
        || root.canonicalize().map_err(|_|LinkError::Journal)?!=root {return Err(LinkError::Journal);}
    #[cfg(unix)] {
        use std::os::unix::fs::PermissionsExt;
        if m.permissions().mode()&0o077!=0 {return Err(LinkError::Journal);}
    }
    #[cfg(windows)] {
        use std::os::windows::fs::MetadataExt;
        if m.file_attributes()&0x400!=0 {return Err(LinkError::Journal);}
    }
    Ok(())
}
fn check_file(path:&Path)->Result<()> {
    let m=std::fs::symlink_metadata(path).map_err(|_|LinkError::Journal)?;
    if !m.is_file() || m.file_type().is_symlink() {return Err(LinkError::Journal);}
    #[cfg(unix)] {
        use std::os::unix::fs::{MetadataExt,PermissionsExt};
        if m.permissions().mode()&0o077!=0 || m.nlink()!=1 {return Err(LinkError::Journal);}
    }
    #[cfg(windows)] {
        use std::os::windows::fs::MetadataExt;
        if m.file_attributes()&0x400!=0 {return Err(LinkError::Journal);}
    }
    Ok(())
}
fn open_file(path:&Path,new:bool,writable:bool)->Result<File> {
    if !new {check_file(path)?;}
    let mut options=OpenOptions::new();options.read(true);
    if writable {options.append(true);}
    if new {options.create_new(true);}
    #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
    #[cfg(windows)] {use std::os::windows::fs::OpenOptionsExt;options.custom_flags(0x00200000);}
    let file=options.open(path).map_err(|_|LinkError::Journal)?;
    check_file(path)?;Ok(file)
}
fn sync_directory(root:&Path)->Result<()> {
    #[cfg(unix)] {File::open(root).and_then(|f|f.sync_all()).map_err(|_|LinkError::Journal)?;}
    #[cfg(not(unix))] {let _=root;}
    Ok(())
}
