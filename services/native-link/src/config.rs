use crate::{canonical::digest_json,wire::{self,ConnectChallenge,ConnectClaims,Projected,ProjectionClaims,SignedPayload},LinkError,Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD,Engine};
use ring::signature::{Ed25519KeyPair,KeyPair,UnparsedPublicKey,ED25519};
use serde::{Deserialize,Serialize};
use uuid::Uuid;
use zeroize::Zeroizing;

/// Public locally-selected binding. No workspace path, permission or key is a wire parameter.
#[derive(Clone,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceConfig {
    issuer:String,
    connector:Uuid,
    device:Uuid,
    device_epoch:i64,
}
impl DeviceConfig {
    pub fn new(issuer:String,connector:Uuid,device:Uuid,device_epoch:i64)->Result<Self> {
        let cfg=Self{issuer,connector,device,device_epoch};cfg.validate()?;Ok(cfg)
    }
    pub fn validate(&self)->Result<()> {
        let url=url::Url::parse(&self.issuer).map_err(|_|LinkError::Configuration)?;
        if self.issuer.len()>2048 || url.scheme()!="https" || url.host_str().is_none()
            || !url.username().is_empty() || url.password().is_some() || url.query().is_some()
            || url.fragment().is_some() || self.issuer.contains('%')
            || self.issuer.ends_with('/') || url.path().contains("//")
            || url.as_str().trim_end_matches('/')!=self.issuer
            || self.connector.is_nil() || self.device.is_nil() || self.device_epoch<=0 {
            return Err(LinkError::Configuration);
        }
        Ok(())
    }
    pub fn issuer(&self)->&str {&self.issuer}
    pub fn connector(&self)->Uuid {self.connector}
    pub fn device(&self)->Uuid {self.device}
    pub fn device_epoch(&self)->i64 {self.device_epoch}
    pub fn resource(&self)->String {format!("{}/mcp",self.issuer)}
    pub(crate) fn endpoint(&self)->Result<String> {
        self.validate()?;
        Ok(format!("wss://{}/agent",self.issuer.strip_prefix("https://").ok_or(LinkError::Configuration)?))
    }
    pub(crate) fn fingerprint(&self,key:&DeviceKey)->Result<[u8;32]> {
        self.validate()?;
        digest_json(&serde_json::json!({"version":1,"issuer":self.issuer,"connector":self.connector,
            "device":self.device,"device_epoch":self.device_epoch,"public_key":key.public_key()}),4096)
    }
}
impl std::fmt::Debug for DeviceConfig {
    fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {f.write_str("DeviceConfig([REDACTED])")}
}

/// Host obtains PKCS8 bytes from protected native storage. There is no wire signing API.
pub struct DeviceKey {key:Ed25519KeyPair}
impl DeviceKey {
    pub fn from_pkcs8(bytes:Zeroizing<Vec<u8>>)->Result<Self> {
        if bytes.is_empty()||bytes.len()>4096 {return Err(LinkError::Credentials);}
        Ok(Self{key:Ed25519KeyPair::from_pkcs8(&bytes).map_err(|_|LinkError::Credentials)?})
    }
    pub fn public_key(&self)->String {URL_SAFE_NO_PAD.encode(self.key.public_key().as_ref())}
    pub(crate) fn connect(&self,cfg:&DeviceConfig,c:&ConnectChallenge,at:i64)->Result<SignedPayload> {
        cfg.validate()?;
        if c.version!=1 || c.issuer!=cfg.issuer || c.resource!=cfg.resource() || c.connector!=cfg.connector
            || c.gateway_boot.is_nil() || c.attempt.is_nil() || !wire::valid_digest(&c.nonce)
            || c.issued_at<0 || c.issued_at>at || c.expires_at<=at
            || c.expires_at.checked_sub(c.issued_at)!=Some(10) {return Err(LinkError::Protocol);}
        let claims=ConnectClaims {version:1,issuer:&cfg.issuer,resource:cfg.resource(),connector:cfg.connector,
            device:cfg.device,device_epoch:cfg.device_epoch,gateway_boot:c.gateway_boot,attempt:c.attempt,
            nonce:&c.nonce,issued_at:c.issued_at,expires_at:c.expires_at};
        let data=serde_json::to_vec(&claims).map_err(|_|LinkError::Protocol)?;
        self.proof(b"coding-tools-agent-connect-v1\0",data,4096)
    }
    pub(crate) fn projection(&self,cfg:&DeviceConfig,boot:Uuid,nonce:&str,revision:i64,
        at:i64,until:i64,state:&Projected)->Result<SignedPayload> {
        if boot.is_nil() || !wire::valid_digest(nonce) || revision<=0 || at<0 || until<=at
            || until.checked_sub(at).is_none_or(|n|n>30) || state.authority_epoch<=0 {return Err(LinkError::Protocol);}
        let claims=ProjectionClaims {version:1,issuer:&cfg.issuer,resource:cfg.resource(),connector:cfg.connector,
            device:cfg.device,device_epoch:cfg.device_epoch,gateway_boot:boot,challenge:nonce,revision,
            issued_at:at,valid_until:until,state};
        let data=serde_json::to_vec(&claims).map_err(|_|LinkError::Protocol)?;
        self.proof(b"coding-tools-authority-projection-v1\0",data,8192)
    }
    fn proof(&self,domain:&[u8],data:Vec<u8>,max:usize)->Result<SignedPayload> {
        if data.is_empty()||data.len()>max {return Err(LinkError::Protocol);}
        let mut message=domain.to_vec();message.extend_from_slice(&data);
        Ok(SignedPayload {payload:URL_SAFE_NO_PAD.encode(data),signature:URL_SAFE_NO_PAD.encode(self.key.sign(&message).as_ref())})
    }
    pub(crate) fn journal_signature(&self,data:&[u8])->[u8;64] {
        let mut message=b"coding-tools-native-journal-v1\0".to_vec();message.extend_from_slice(data);
        let mut signature=[0;64];signature.copy_from_slice(self.key.sign(&message).as_ref());signature
    }
    pub(crate) fn verify_journal(&self,data:&[u8],signature:&[u8])->Result<()> {
        let mut message=b"coding-tools-native-journal-v1\0".to_vec();message.extend_from_slice(data);
        UnparsedPublicKey::new(&ED25519,self.key.public_key().as_ref()).verify(&message,signature).map_err(|_|LinkError::Journal)
    }
}
impl std::fmt::Debug for DeviceKey {
    fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {f.write_str("DeviceKey([REDACTED])")}
}
