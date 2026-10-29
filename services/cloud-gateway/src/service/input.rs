use super::{Result, ServiceError};
use crate::{PublicIdentity, Secret, SecretKey};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::Deserialize;
use std::{io::Read, net::SocketAddr, path::Path};
use uuid::Uuid;
use zeroize::Zeroizing;

const MAX_INPUT: u64 = 16 * 1024;

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ClientMode {
    Public,
    Confidential,
}
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayConfig {
    pub origin: String,
    pub prefix: String,
    pub connector: Uuid,
    pub owner_subject: Uuid,
    pub client_id: String,
    pub redirect_uri: String,
    pub client_authentication: ClientMode,
    #[serde(default = "default_bind")]
    pub bind: SocketAddr,
}
fn default_bind() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], 28880))
}
impl GatewayConfig {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        if bytes.len() as u64 > MAX_INPUT {
            return Err(ServiceError::Configuration);
        }
        let cfg: Self = serde_json::from_slice(bytes).map_err(|_| ServiceError::Configuration)?;
        cfg.identity()?;
        crate::config::validate_client(&cfg.client_id, &cfg.redirect_uri)
            .map_err(|_| ServiceError::Configuration)?;
        if cfg.owner_subject.is_nil()
            || !cfg.bind.ip().is_loopback()
            || (cfg.bind.port() != 0 && cfg.bind.port() < 1024)
        {
            return Err(ServiceError::Configuration);
        }
        Ok(cfg)
    }
    pub fn identity(&self) -> Result<PublicIdentity> {
        PublicIdentity::new(&self.origin, &self.prefix, self.connector)
            .map_err(|_| ServiceError::Configuration)
    }
    pub(crate) fn read(path: &Path) -> Result<Self> {
        // Unix requires protected config too. Windows config contains no credentials;
        // its integrity belongs to the local operator until the ACL adapter exists.
        #[cfg(unix)]
        let data = read_protected(path)?;
        #[cfg(not(unix))]
        let data = read_config_file(path)?;
        Self::from_bytes(&data)
    }
}

pub(crate) struct Secrets {
    pub database_url: Secret,
    pub identity_key: SecretKey,
    pub password: Option<Secret>,
    pub client_secret: Option<Secret>,
}
// No Debug. Fully parsed fields and the raw input buffer are zeroized on drop.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SecretDocument {
    database_url: String,
    identity_key: String,
    password: Option<String>,
    client_secret: Option<String>,
}
impl Drop for SecretDocument {
    fn drop(&mut self) {
        use zeroize::Zeroize;
        self.database_url.zeroize();
        self.identity_key.zeroize();
        if let Some(p) = self.password.as_mut() {
            p.zeroize();
        }
        if let Some(p) = self.client_secret.as_mut() {
            p.zeroize();
        }
    }
}
impl Secrets {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() as u64 > MAX_INPUT {
            return Err(ServiceError::Input);
        }
        let mut raw: SecretDocument =
            serde_json::from_slice(bytes).map_err(|_| ServiceError::Input)?;
        let url = url::Url::parse(&raw.database_url).map_err(|_| ServiceError::Input)?;
        if !matches!(url.scheme(), "postgres" | "postgresql")
            || url.host_str().is_none()
            || url.fragment().is_some()
            || url.path().len() < 2
            || raw.database_url.len() > 4096
        {
            return Err(ServiceError::Input);
        }
        let key_bytes = Zeroizing::new(
            URL_SAFE_NO_PAD
                .decode(&raw.identity_key)
                .map_err(|_| ServiceError::Input)?,
        );
        let key: [u8; 32] = key_bytes
            .as_slice()
            .try_into()
            .map_err(|_| ServiceError::Input)?;
        let identity_key = SecretKey::new(key).map_err(|_| ServiceError::Input)?;
        Ok(Self {
            database_url: Secret::new(std::mem::take(&mut raw.database_url)),
            identity_key,
            password: raw.password.take().map(Secret::new),
            client_secret: raw.client_secret.take().map(Secret::new),
        })
    }
}

pub(crate) fn read_bounded(reader: impl Read) -> Result<Zeroizing<Vec<u8>>> {
    let mut bytes = Zeroizing::new(Vec::new());
    reader
        .take(MAX_INPUT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ServiceError::Input)?;
    if bytes.is_empty() || bytes.len() as u64 > MAX_INPUT {
        return Err(ServiceError::Input);
    }
    Ok(bytes)
}

/// File input is a local-operator boundary, not a same-UID process sandbox.
/// Windows must use stdin until native ACL validation is implemented.
pub fn read_protected(path: &Path) -> Result<Zeroizing<Vec<u8>>> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
        if !path.is_absolute()
            || path
                .canonicalize()
                .map_err(|_| ServiceError::FileProtection)?
                != path
        {
            return Err(ServiceError::FileProtection);
        }
        let parent = path.parent().ok_or(ServiceError::FileProtection)?;
        let directory = parent
            .metadata()
            .map_err(|_| ServiceError::FileProtection)?;
        // SAFETY: geteuid has no pointer arguments or mutable memory preconditions.
        let uid = unsafe { libc::geteuid() };
        if !directory.is_dir() || directory.uid() != uid || directory.mode() & 0o022 != 0 {
            return Err(ServiceError::FileProtection);
        }
        let file = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(path)
            .map_err(|_| ServiceError::FileProtection)?;
        let m = file.metadata().map_err(|_| ServiceError::FileProtection)?;
        if !m.is_file()
            || m.uid() != uid
            || m.nlink() != 1
            || m.mode() & 0o077 != 0
            || m.len() > MAX_INPUT
        {
            return Err(ServiceError::FileProtection);
        }
        read_bounded(file)
    }
    #[cfg(not(unix))]
    {
        let _ = path;
        Err(ServiceError::FileAclUnsupported)
    }
}
#[cfg(not(unix))]
fn read_config_file(path: &Path) -> Result<Zeroizing<Vec<u8>>> {
    if !path.is_absolute() {
        return Err(ServiceError::Configuration);
    }
    let meta = std::fs::symlink_metadata(path).map_err(|_| ServiceError::Configuration)?;
    if !meta.is_file() || meta.file_type().is_symlink() {
        return Err(ServiceError::Configuration);
    }
    read_bounded(std::fs::File::open(path).map_err(|_| ServiceError::Configuration)?)
}
