use super::{AgentError, Result};
use crate::PublicIdentity;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::Deserialize;
#[cfg(not(unix))]
use std::io::Read;
use std::path::{Path, PathBuf};
use uuid::Uuid;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentConfig {
    pub origin: String,
    pub prefix: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub authority_epoch: i64,
    pub public_key: String,
    pub revision_file: PathBuf,
    pub ca_der_file: Option<PathBuf>,
    #[serde(default = "default_runtime")]
    pub run_seconds: u64,
}
fn default_runtime() -> u64 {
    3600
}
impl AgentConfig {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        if bytes.is_empty() || bytes.len() > 16_384 {
            return Err(AgentError::Configuration);
        }
        let cfg: Self = serde_json::from_slice(bytes).map_err(|_| AgentError::Configuration)?;
        cfg.identity()?;
        if cfg.device.is_nil()
            || cfg.device_epoch <= 0
            || cfg.authority_epoch <= 0
            || !cfg.revision_file.is_absolute()
            || cfg.revision_file.file_name().is_none()
            || cfg.ca_der_file.as_ref().is_some_and(|p| !p.is_absolute())
            || !(1..=3600).contains(&cfg.run_seconds)
            || cfg.public_key.len() != 43
            || cfg.key_bytes()?.len() != 32
        {
            return Err(AgentError::Configuration);
        }
        Ok(cfg)
    }
    pub(crate) fn read(path: &Path) -> Result<Self> {
        if !path.is_absolute() {
            return Err(AgentError::Configuration);
        }
        #[cfg(unix)]
        let b = crate::service::read_protected(path).map_err(|_| AgentError::Configuration)?;
        #[cfg(not(unix))]
        let b = read_public(path)?;
        Self::from_bytes(&b)
    }
    pub(crate) fn identity(&self) -> Result<PublicIdentity> {
        PublicIdentity::new(&self.origin, &self.prefix, self.connector)
            .map_err(|_| AgentError::Configuration)
    }
    pub(crate) fn endpoint(&self) -> Result<String> {
        let identity = self.identity()?;
        Ok(format!(
            "wss://{}{}/agent",
            identity.authority(),
            identity.prefix()
        ))
    }
    pub(crate) fn key_bytes(&self) -> Result<Vec<u8>> {
        URL_SAFE_NO_PAD
            .decode(&self.public_key)
            .map_err(|_| AgentError::Configuration)
    }
    pub(crate) fn journal_binding(&self) -> Result<Vec<u8>> {
        let identity = self.identity()?;
        serde_json::to_vec(&(
            identity.issuer(),
            identity.resource(),
            self.device,
            self.device_epoch,
            self.authority_epoch,
            &self.public_key,
        ))
        .map_err(|_| AgentError::Configuration)
    }
}
// Public metadata only: Windows secret file input is never routed through here.
#[cfg(not(unix))]
fn read_public(path: &Path) -> Result<Vec<u8>> {
    let meta = std::fs::symlink_metadata(path).map_err(|_| AgentError::Configuration)?;
    if !meta.is_file() || meta.file_type().is_symlink() {
        return Err(AgentError::Configuration);
    }
    let file = std::fs::File::open(path).map_err(|_| AgentError::Configuration)?;
    let mut b = Vec::new();
    file.take(16_385)
        .read_to_end(&mut b)
        .map_err(|_| AgentError::Configuration)?;
    Ok(b)
}
// Keep a size-bound private-CA read. Certificate trust is configuration, not a TLS bypass.
pub(crate) fn read_ca(path: &Path) -> Result<Vec<u8>> {
    #[cfg(unix)]
    {
        crate::service::read_protected(path)
            .map(|v| v.to_vec())
            .map_err(|_| AgentError::Configuration)
    }
    #[cfg(not(unix))]
    {
        read_public(path)
    }
}
