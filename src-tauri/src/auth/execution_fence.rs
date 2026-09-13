//! Durable evidence that a remote command might outlive an application crash.
//! Recovery is a local operator decision, never inferred from an absent PID.
use std::collections::BTreeSet;
use std::path::Path;
use std::sync::Mutex;
use serde::{Deserialize,Serialize};
use crate::data::AuthDocument;

#[derive(Clone,Default,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
struct Document { version:u32, dirty:bool, generation:String, bindings:BTreeSet<String> }
struct Inner { disk:AuthDocument, document:Document, recovered:bool, poisoned:bool }
pub(crate) struct ExecutionFence { inner:Mutex<Inner> }
impl ExecutionFence {
    pub(crate) fn open(root:&Path)->Result<Self,String> {
        let disk=AuthDocument::open(root).map_err(|_|"执行恢复锁存储不可用；未允许新命令")?;
        let document:Document=disk.load().map_err(|_|"执行恢复锁损坏；原文件已保留")?.unwrap_or(Document {version:1,..Default::default()});
        if document.version!=1 || document.bindings.len()>64
            || document.bindings.iter().any(|b|b.len()!=64 || !b.bytes().all(|c|c.is_ascii_hexdigit()))
            || (document.dirty && uuid::Uuid::parse_str(&document.generation).is_err()) {return Err("执行恢复锁版本或数据无效".into());}
        let recovered=document.dirty;
        Ok(Self {inner:Mutex::new(Inner {disk,document,recovered,poisoned:false})})
    }
    pub(crate) fn bindings(&self)->Vec<String> {self.inner.lock().expect("execution fence").document.bindings.iter().cloned().collect()}
    pub(crate) fn ready(&self)->bool {self.inner.lock().map(|i|!i.recovered&&!i.poisoned).unwrap_or(false)}
    pub(crate) fn mark(&self,binding:&str)->Result<(), &'static str> {
        let mut i=self.inner.lock().map_err(|_|"CHAT_RECOVERY_REQUIRED")?;
        if i.recovered||i.poisoned {return Err("CHAT_RECOVERY_REQUIRED");}
        if binding.len()!=64 || !binding.bytes().all(|c|c.is_ascii_hexdigit()) {return Err("CHAT_CONTEXT_REQUIRED");}
        if i.document.dirty&&i.document.bindings.contains(binding){return Ok(());}
        let mut next=i.document.clone();
        if !next.bindings.contains(binding)&&next.bindings.len()>=64 {return Err("CHAT_RUNTIME_UNAVAILABLE");}
        next.bindings.insert(binding.into());next.dirty=true;next.generation=uuid::Uuid::new_v4().to_string();
        Self::save(&mut i,next)
    }
    fn save(i:&mut Inner,next:Document)->Result<(), &'static str> {
        if i.disk.save(&next).is_err(){i.poisoned=true;return Err("CHAT_RECOVERY_REQUIRED");}
        i.document=next;Ok(())
    }
    /// Only after the authorizer froze admission and observed all known work terminal.
    pub(crate) fn clear_quiet(&self)->Result<(), &'static str> {
        let mut i=self.inner.lock().map_err(|_|"CHAT_RECOVERY_REQUIRED")?;
        if i.recovered||i.poisoned{return Err("CHAT_RECOVERY_REQUIRED");}
        if i.document.dirty {let mut next=i.document.clone();next.dirty=false;Self::save(&mut i,next)?;}
        Ok(())
    }
    pub(crate) fn acknowledge(&self,expected_generation:&str)->Result<(),String> {
        let mut i=self.inner.lock().map_err(|_|"执行恢复锁不可用")?;
        if !i.recovered||i.poisoned||i.document.generation!=expected_generation{return Err("恢复确认已过期或存储不可用；请重新检查".into());}
        let mut next=i.document.clone();next.dirty=false;
        Self::save(&mut i,next).map_err(str::to_string)?;i.recovered=false;Ok(())
    }
    pub(crate) fn snapshot(&self)->serde_json::Value {
        match self.inner.lock(){Ok(i)=>serde_json::json!({"required":i.recovered||i.poisoned,"generation":i.document.generation}),
            Err(_)=>serde_json::json!({"required":true,"generation":null})}
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn crash_reopen_needs_explicit_current_local_confirmation() {
        let root=tempfile::tempdir().unwrap();let f=ExecutionFence::open(root.path()).unwrap();
        f.mark(&"a".repeat(64)).unwrap();assert!(f.ready());drop(f);
        let f=ExecutionFence::open(root.path()).unwrap();assert!(!f.ready());assert!(f.clear_quiet().is_err());
        assert!(f.mark(&"b".repeat(64)).is_err());assert!(f.acknowledge("stale").is_err());
        let id=f.snapshot()["generation"].as_str().unwrap().to_owned();f.acknowledge(&id).unwrap();assert!(f.ready());
        assert!(f.acknowledge(&id).is_err());drop(f);assert!(ExecutionFence::open(root.path()).unwrap().ready());
    }
    #[test]
    fn terminal_work_can_be_cleared_before_restart() {
        let root=tempfile::tempdir().unwrap();let f=ExecutionFence::open(root.path()).unwrap();
        f.mark(&"c".repeat(64)).unwrap();f.clear_quiet().unwrap();drop(f);
        let f=ExecutionFence::open(root.path()).unwrap();assert!(f.ready());assert_eq!(f.bindings(),vec!["c".repeat(64)]);
    }
}
