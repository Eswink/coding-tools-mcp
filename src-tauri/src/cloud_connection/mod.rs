//! Local connection configuration is not a grant, a live channel or an execution permit.
mod storage;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde::{Deserialize, Serialize};
use zeroize::{Zeroize, Zeroizing};

pub(crate) use storage::ConnectionStore;

const MAX_CONFIG_BYTES: usize = 16 * 1024;
const MAX_KEY_BYTES: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ConfigurationError {
    InvalidInput,
    InvalidBinding,
    AlreadyInitialized,
    Unavailable,
}

impl std::fmt::Display for ConfigurationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::InvalidInput => "Cloud connection input is invalid; no credentials were imported.",
            Self::InvalidBinding => "Cloud connection does not match the selected local workspace.",
            Self::AlreadyInitialized => {
                "Cloud connection namespace already exists; overwrite and automatic recovery are refused."
            }
            Self::Unavailable => {
                "Cloud connection storage is unavailable or invalid; existing state was preserved."
            }
        })
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ConnectionConfig {
    pub(crate) version: u32,
    pub(crate) origin: String,
    pub(crate) prefix: String,
    pub(crate) connector: String,
    pub(crate) device: String,
    pub(crate) device_epoch: i64,
    pub(crate) authority_epoch: i64,
    pub(crate) public_key: String,
    pub(crate) run_seconds: u64,
}

impl ConnectionConfig {
    pub(crate) fn validate(&self) -> Result<(), ConfigurationError> {
        let invalid = ConfigurationError::InvalidInput;
        if self.version != 1 || self.origin.len() > 512 || !self.origin.is_ascii() {
            return Err(invalid);
        }
        let url = reqwest::Url::parse(&self.origin).map_err(|_| invalid)?;
        if url.scheme() != "https"
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.path() != "/"
            || url.query().is_some()
            || url.fragment().is_some()
            || url.origin().ascii_serialization() != self.origin
        {
            return Err(invalid);
        }
        // Match the fixed single-segment gateway namespace, not an arbitrary URL/path.
        let route = self.prefix.strip_prefix('/').ok_or(invalid)?;
        if route.is_empty()
            || route.len() > 64
            || !route.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            || route.starts_with('-')
            || route.ends_with('-')
        {
            return Err(invalid);
        }
        for id in [&self.connector, &self.device] {
            let parsed = uuid::Uuid::parse_str(id).map_err(|_| invalid)?;
            if parsed.is_nil() || parsed.hyphenated().to_string() != *id {
                return Err(invalid);
            }
        }
        if self.device_epoch <= 0
            || self.authority_epoch <= 0
            || !(1..=3600).contains(&self.run_seconds)
        {
            return Err(invalid);
        }
        decode_key(&self.public_key, 32)?;
        Ok(())
    }
}

fn decode_key(raw: &str, length: usize) -> Result<Zeroizing<Vec<u8>>, ConfigurationError> {
    let bytes = Zeroizing::new(
        URL_SAFE_NO_PAD.decode(raw).map_err(|_| ConfigurationError::InvalidInput)?,
    );
    if bytes.len() != length || URL_SAFE_NO_PAD.encode(&*bytes) != raw {
        return Err(ConfigurationError::InvalidInput);
    }
    Ok(bytes)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PrivateInput {
    pkcs8: String,
}

impl Drop for PrivateInput {
    fn drop(&mut self) {
        self.pkcs8.zeroize();
    }
}

pub(crate) struct CheckedImport {
    pub(super) config: ConnectionConfig,
    pub(super) pkcs8: Zeroizing<String>,
}

impl std::fmt::Debug for CheckedImport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("CheckedImport([REDACTED])")
    }
}

impl CheckedImport {
    pub(crate) fn parse(public: &str, private: &str) -> Result<Self, ConfigurationError> {
        if public.is_empty()
            || public.len() > MAX_CONFIG_BYTES
            || private.is_empty()
            || private.len() > MAX_KEY_BYTES
        {
            return Err(ConfigurationError::InvalidInput);
        }
        let config: ConnectionConfig =
            serde_json::from_str(public).map_err(|_| ConfigurationError::InvalidInput)?;
        config.validate()?;
        let input: PrivateInput =
            serde_json::from_str(private).map_err(|_| ConfigurationError::InvalidInput)?;
        verify_private_key(&config, &input.pkcs8)?;
        Ok(Self {
            config,
            pkcs8: Zeroizing::new(input.pkcs8.clone()),
        })
    }
}

pub(super) fn verify_private_key(
    config: &ConnectionConfig,
    encoded: &str,
) -> Result<(), ConfigurationError> {
    if encoded.is_empty() || encoded.len() > MAX_KEY_BYTES {
        return Err(ConfigurationError::InvalidInput);
    }
    let bytes = Zeroizing::new(
        URL_SAFE_NO_PAD.decode(encoded).map_err(|_| ConfigurationError::InvalidInput)?,
    );
    if URL_SAFE_NO_PAD.encode(&*bytes) != encoded {
        return Err(ConfigurationError::InvalidInput);
    }
    let key = Ed25519KeyPair::from_pkcs8(&bytes).map_err(|_| ConfigurationError::InvalidInput)?;
    let public = decode_key(&config.public_key, 32)?;
    if key.public_key().as_ref() != public.as_slice() {
        return Err(ConfigurationError::InvalidBinding);
    }
    Ok(())
}

/// Deliberately excludes key material, workspace paths, grants and runtime state.
#[derive(Debug, Serialize)]
pub(crate) struct ConnectionSummary {
    pub(crate) configured: bool,
    pub(crate) scope: &'static str,
    pub(crate) origin: String,
    pub(crate) prefix: String,
    pub(crate) connector: String,
    pub(crate) device: String,
    pub(crate) device_epoch: i64,
    pub(crate) authority_epoch: i64,
    pub(crate) public_key: String,
    pub(crate) run_seconds: u64,
}

impl From<&ConnectionConfig> for ConnectionSummary {
    fn from(config: &ConnectionConfig) -> Self {
        Self {
            configured: true,
            scope: "configuration_only_not_execution_authority",
            origin: config.origin.clone(),
            prefix: config.prefix.clone(),
            connector: config.connector.clone(),
            device: config.device.clone(),
            device_epoch: config.device_epoch,
            authority_epoch: config.authority_epoch,
            public_key: config.public_key.clone(),
            run_seconds: config.run_seconds,
        }
    }
}

#[cfg(test)]
mod tests;
