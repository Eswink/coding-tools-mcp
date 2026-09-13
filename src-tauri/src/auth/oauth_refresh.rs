//! Rotating refresh families. Raw bearer credentials never enter the document.
//! A valid old generation revokes its family; there is deliberately no retry grace.
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock, Weak};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{hmac, rand::{SecureRandom, SystemRandom}};
use serde::{Deserialize, Serialize};
use zeroize::Zeroizing;
use crate::data::AuthDocument;
use super::{chat::unix_now, session_policy::SessionPolicy};

pub(crate) fn storage_root(profile: &str) -> Result<PathBuf,String> {
    use sha2::{Digest,Sha256};
    let root=crate::harness::Harness::default_root().map_err(|e|e.to_string())?;
    Ok(root.join("remote-auth-v1").join(format!("{:x}",Sha256::digest(profile.as_bytes()))))
}
const MAX_FAMILIES: usize = 64;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum RefreshError { InvalidGrant, InvalidTarget, InvalidScope, Unavailable, Capacity }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Family {
    id: String, client_id: String, issuer: String, resource: String,
    credential_tag: String, scopes: String, generation: u64, current_digest: String,
    issued_at: u64, expires_at: u64, last_used_at: u64, revoked: bool,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document { version: u32, families: HashMap<String, Family> }
impl Default for Document { fn default() -> Self { Self { version:1, families:HashMap::new() } } }
struct Inner { disk: Option<AuthDocument>, document: Document, initialized: bool, poisoned: bool }
pub(crate) struct RefreshStore { root: PathBuf, inner: Mutex<Inner> }
#[derive(Clone)]
pub(crate) struct RefreshContext {
    pub client_id: String, pub issuer: String, pub resource: String,
    pub key: Arc<Zeroizing<Vec<u8>>>, pub policy: SessionPolicy,
}
pub(crate) struct RefreshPair {
    pub token: Zeroizing<String>, pub family_id: String, pub scopes: String, pub expires_at: u64,
}
impl RefreshContext {
    pub(crate) fn new(client_id: &str, issuer: &str, resource: &str, token_secret: &str,
        password: &str, client_secret: Option<&str>, policy: &SessionPolicy) -> Self {
        let raw = Zeroizing::new(serde_json::to_vec(&("refresh-credentials-v1", client_id, password, client_secret)).expect("credential encoding"));
        let key = hmac::sign(&hmac::Key::new(hmac::HMAC_SHA256, token_secret.as_bytes()), &raw).as_ref().to_vec();
        Self { client_id:client_id.into(), issuer:issuer.trim_end_matches('/').into(), resource:resource.into(),
            key:Arc::new(Zeroizing::new(key)), policy:policy.clone() }
    }
    fn mac(&self, text: &[u8]) -> String {
        URL_SAFE_NO_PAD.encode(hmac::sign(&hmac::Key::new(hmac::HMAC_SHA256, &self.key),text).as_ref())
    }
    fn tag(&self) -> String { self.mac(b"refresh-credential-tag-v1") }
    fn matches(&self, f: &Family) -> bool {
        f.client_id == self.client_id && f.issuer == self.issuer && f.resource == self.resource
            && super::bearer::constant_time_eq_str(&f.credential_tag,&self.tag())
    }
}
impl RefreshStore {
    pub(crate) fn shared(root: PathBuf) -> Arc<Self> {
        static REGISTRY: OnceLock<Mutex<HashMap<PathBuf, Weak<RefreshStore>>>> = OnceLock::new();
        let mut registry = REGISTRY.get_or_init(Mutex::default).lock().expect("refresh registry");
        registry.retain(|_,s|s.strong_count()>0);
        if let Some(s) = registry.get(&root).and_then(Weak::upgrade) { return s; }
        let store = Arc::new(Self { root:root.clone(), inner:Mutex::new(Inner {
            disk:None, document:Document::default(), initialized:false, poisoned:false }) });
        registry.insert(root,Arc::downgrade(&store)); store
    }
    fn initialize(&self, inner: &mut Inner) -> Result<(), RefreshError> {
        if inner.poisoned { return Err(RefreshError::Unavailable); }
        if inner.initialized { return Ok(()); }
        let result = (|| {
            let disk = AuthDocument::open(&self.root).map_err(|_|RefreshError::Unavailable)?;
            let document: Document = disk.load().map_err(|_|RefreshError::Unavailable)?.unwrap_or_default();
            if document.version != 1 || document.families.len()>MAX_FAMILIES { return Err(RefreshError::Unavailable); }
            for (id,f) in &document.families {
                if id != &f.id || uuid::Uuid::parse_str(id).is_err() || f.client_id.is_empty() || f.client_id.len()>256
                    || f.expires_at <= f.issued_at || f.expires_at-f.issued_at>90*86400 || f.generation>1_000_000
                    || f.scopes != "mcp offline_access" || f.current_digest.len()!=43 || f.credential_tag.len()!=43 {
                    return Err(RefreshError::Unavailable);
                }
            }
            inner.document = document; inner.disk = Some(disk); inner.initialized = true; Ok(())
        })();
        if result.is_err() { inner.poisoned = true; } result
    }
    fn commit(inner: &mut Inner, document: Document) -> Result<(), RefreshError> {
        // Durable commit precedes exposing any new refresh token or in-memory generation.
        if inner.disk.as_mut().ok_or(RefreshError::Unavailable)?.save(&document).is_err() {
            inner.poisoned = true; return Err(RefreshError::Unavailable);
        }
        inner.document = document; Ok(())
    }
    fn token(ctx: &RefreshContext, family: &str, generation: u64) -> Result<Zeroizing<String>, RefreshError> {
        let mut random = [0u8;32]; SystemRandom::new().fill(&mut random).map_err(|_|RefreshError::Unavailable)?;
        let payload = Zeroizing::new(format!("rt1.{family}.{generation}.{}",URL_SAFE_NO_PAD.encode(random)));
        Ok(Zeroizing::new(format!("{}.{}",&*payload,ctx.mac(payload.as_bytes()))))
    }
    fn parse(ctx: &RefreshContext, raw: &str) -> Result<(String,u64),RefreshError> {
        if raw.len()>512 { return Err(RefreshError::InvalidGrant); }
        let (payload,tag)=raw.rsplit_once('.').ok_or(RefreshError::InvalidGrant)?;
        let tag=URL_SAFE_NO_PAD.decode(tag).map_err(|_|RefreshError::InvalidGrant)?;
        hmac::verify(&hmac::Key::new(hmac::HMAC_SHA256,&ctx.key),payload.as_bytes(),&tag).map_err(|_|RefreshError::InvalidGrant)?;
        let parts: Vec<_>=payload.split('.').collect();
        if parts.len()!=4 || parts[0]!="rt1" || uuid::Uuid::parse_str(parts[1]).is_err()
            || URL_SAFE_NO_PAD.decode(parts[3]).map(|v|v.len()).unwrap_or(0)!=32 { return Err(RefreshError::InvalidGrant); }
        Ok((parts[1].into(),parts[2].parse().map_err(|_|RefreshError::InvalidGrant)?))
    }
    pub(crate) fn issue(&self, ctx: &RefreshContext) -> Result<RefreshPair,RefreshError> {
        ctx.policy.validate().map_err(|_|RefreshError::Unavailable)?;
        let mut inner=self.inner.lock().map_err(|_|RefreshError::Unavailable)?; self.initialize(&mut inner)?;
        let mut document=inner.document.clone(); let now=unix_now();
        document.families.retain(|_,f|f.expires_at>now);
        if document.families.len()>=MAX_FAMILIES { return Err(RefreshError::Capacity); }
        let id=uuid::Uuid::new_v4().to_string(); let token=Self::token(ctx,&id,0)?;
        let expires_at=now+ctx.policy.refresh_session_ttl_seconds; let scopes="mcp offline_access".to_owned();
        document.families.insert(id.clone(),Family { id:id.clone(),client_id:ctx.client_id.clone(),issuer:ctx.issuer.clone(),
            resource:ctx.resource.clone(),credential_tag:ctx.tag(),scopes:scopes.clone(),generation:0,
            current_digest:ctx.mac(token.as_bytes()),issued_at:now,expires_at,last_used_at:now,revoked:false });
        Self::commit(&mut inner,document)?;
        Ok(RefreshPair {token,family_id:id,scopes,expires_at})
    }
    pub(crate) fn rotate(&self, ctx: &RefreshContext, raw: &str, resource: &str, scope: &str) -> Result<RefreshPair,RefreshError> {
        // Authenticate the opaque token before touching any persisted family (no guessed-ID DoS).
        let (id,generation)=Self::parse(ctx,raw)?;
        if !resource.is_empty() && resource!=ctx.resource { return Err(RefreshError::InvalidTarget); }
        let requested = if scope.is_empty() { None } else {
            Some(super::oauth_scope::normalize(scope,true).map_err(|_|RefreshError::InvalidScope)?)
        };
        let mut inner=self.inner.lock().map_err(|_|RefreshError::Unavailable)?; self.initialize(&mut inner)?;
        let f=inner.document.families.get(&id).ok_or(RefreshError::InvalidGrant)?;
        if !ctx.matches(f) || f.revoked || unix_now()>=f.expires_at { return Err(RefreshError::InvalidGrant); }
        let mut document=inner.document.clone(); let f=document.families.get_mut(&id).unwrap();
        if generation<f.generation {
            f.revoked=true; Self::commit(&mut inner,document)?; return Err(RefreshError::InvalidGrant);
        }
        if generation!=f.generation || !super::bearer::constant_time_eq_str(&ctx.mac(raw.as_bytes()),&f.current_digest) {
            return Err(RefreshError::InvalidGrant);
        }
        let next=f.generation.checked_add(1).filter(|n|*n<=1_000_000).ok_or(RefreshError::InvalidGrant)?;
        let token=Self::token(ctx,&id,next)?; f.generation=next; f.current_digest=ctx.mac(token.as_bytes()); f.last_used_at=unix_now();
        let scopes=requested.unwrap_or_else(||f.scopes.clone()); let expires_at=f.expires_at;
        Self::commit(&mut inner,document)?;
        Ok(RefreshPair {token,family_id:id,scopes,expires_at})
    }
    pub(crate) fn valid_family(&self, ctx: &RefreshContext, id: &str) -> bool {
        let Ok(mut inner)=self.inner.lock() else {return false};
        if self.initialize(&mut inner).is_err() {return false}
        inner.document.families.get(id).is_some_and(|f|ctx.matches(f)&&!f.revoked&&unix_now()<f.expires_at)
    }
    pub(crate) fn revoke_all(&self) -> Result<(),RefreshError> {
        let mut inner=self.inner.lock().map_err(|_|RefreshError::Unavailable)?; self.initialize(&mut inner)?;
        let mut doc=inner.document.clone(); for f in doc.families.values_mut(){f.revoked=true;}
        Self::commit(&mut inner,doc)
    }
    pub(crate) fn snapshot(&self) -> Result<serde_json::Value,RefreshError> {
        let mut inner=self.inner.lock().map_err(|_|RefreshError::Unavailable)?; self.initialize(&mut inner)?;
        let active: Vec<_>=inner.document.families.values().filter(|f|!f.revoked&&unix_now()<f.expires_at).collect();
        Ok(serde_json::json!({"active_families":active.len(),"latest_expiry":active.iter().map(|f|f.expires_at).max(),
            "rotation":"strict","raw_tokens_stored":false}))
    }
}
#[cfg(test)]
#[path="oauth_refresh_tests.rs"]
mod tests;
