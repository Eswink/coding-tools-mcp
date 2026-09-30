use std::fs::{self, Metadata};
use std::path::{Path, PathBuf};

use ring::rand::{SecureRandom, SystemRandom};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use zeroize::{Zeroize, Zeroizing};

use super::{
    decode_key, verify_private_key, CheckedImport, ConfigurationError, ConnectionConfig,
    ConnectionSummary, URL_SAFE_NO_PAD,
};
use crate::data::AuthDocument;
use base64::Engine;

const DOCUMENT_VERSION: u32 = 1;
const DOCUMENT_STATE: &str = "configured_without_runtime_journals";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    version: u32,
    state: String,
    profile: String,
    workspace: String,
    config: ConnectionConfig,
    pkcs8: String,
    binding_key: String,
}

impl Drop for Document {
    fn drop(&mut self) {
        self.pkcs8.zeroize();
        self.binding_key.zeroize();
    }
}

/// The path is chosen by the native host, never by imported/cloud arguments.
pub(crate) struct ConnectionStore {
    root: PathBuf,
    profile: String,
    workspace: String,
}

impl std::fmt::Debug for ConnectionStore {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ConnectionStore([LOCAL_BINDING_REDACTED])")
    }
}

impl ConnectionStore {
    pub(crate) fn for_workspace(
        profile: &str,
        workspace: &Path,
    ) -> Result<Self, ConfigurationError> {
        let base = crate::harness::Harness::default_root()
            .map_err(|_| ConfigurationError::Unavailable)?
            .join("cloud-connections-v1");
        let name = format!("{:x}", Sha256::digest(profile.as_bytes()));
        Self::at(base.join(name), profile, workspace)
    }

    pub(super) fn at(
        root: PathBuf,
        profile: &str,
        workspace: &Path,
    ) -> Result<Self, ConfigurationError> {
        if !root.is_absolute()
            || profile.is_empty()
            || profile.len() > 128
            || profile.chars().any(char::is_control)
        {
            return Err(ConfigurationError::InvalidBinding);
        }
        let workspace = workspace
            .canonicalize()
            .map_err(|_| ConfigurationError::InvalidBinding)?;
        if !workspace.is_dir() {
            return Err(ConfigurationError::InvalidBinding);
        }
        let workspace = workspace
            .to_str()
            .ok_or(ConfigurationError::InvalidBinding)?
            .to_owned();
        Ok(Self {
            root,
            profile: profile.to_owned(),
            workspace,
        })
    }

    pub(crate) fn initialize(
        &self,
        input: CheckedImport,
    ) -> Result<ConnectionSummary, ConfigurationError> {
        // Validate even a crate-internal caller before *any* namespace writes.
        input.config.validate()?;
        verify_private_key(&input.config, &input.pkcs8)?;
        let mut random = Zeroizing::new([0u8; 32]);
        SystemRandom::new()
            .fill(random.as_mut())
            .map_err(|_| ConfigurationError::Unavailable)?;
        let document = Document {
            version: DOCUMENT_VERSION,
            state: DOCUMENT_STATE.to_owned(),
            profile: self.profile.clone(),
            workspace: self.workspace.clone(),
            config: input.config.clone(),
            pkcs8: input.pkcs8.to_string(),
            binding_key: URL_SAFE_NO_PAD.encode(random.as_ref()),
        };
        let parent = self.root.parent().ok_or(ConfigurationError::Unavailable)?;
        directory_chain(parent)?;
        let mut parent_builder = fs::DirBuilder::new();
        parent_builder.recursive(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            parent_builder.mode(0o700);
        }
        parent_builder
            .create(parent)
            .map_err(|_| ConfigurationError::Unavailable)?;
        directory_chain(parent)?;
        private_directory(parent)?;
        let mut exclusive = fs::DirBuilder::new();
        exclusive.recursive(false);
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            exclusive.mode(0o700);
        }
        // This is the initialization linearization point. Never use recursive
        // creation here and never remove this directory on an error afterwards.
        exclusive.create(&self.root).map_err(|error| {
            if error.kind() == std::io::ErrorKind::AlreadyExists {
                ConfigurationError::AlreadyInitialized
            } else {
                ConfigurationError::Unavailable
            }
        })?;
        sync_directory(parent)?;
        let mut disk =
            AuthDocument::open(&self.root).map_err(|_| ConfigurationError::Unavailable)?;
        if disk
            .load::<Document>()
            .map_err(|_| ConfigurationError::Unavailable)?
            .is_some()
        {
            return Err(ConfigurationError::AlreadyInitialized);
        }
        disk.save(&document)
            .map_err(|_| ConfigurationError::Unavailable)?;
        sync_directory(&self.root)?;
        let verified: Document = disk
            .load()
            .map_err(|_| ConfigurationError::Unavailable)?
            .ok_or(ConfigurationError::Unavailable)?;
        self.validate_document(&verified)?;
        Ok(ConnectionSummary::from(&verified.config))
    }

    pub(crate) fn summary(&self) -> Result<Option<ConnectionSummary>, ConfigurationError> {
        match fs::symlink_metadata(&self.root) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(ConfigurationError::Unavailable),
            Ok(metadata) if !metadata.is_dir() || redirect(&metadata) => {
                return Err(ConfigurationError::Unavailable);
            }
            Ok(_) => {}
        }
        directory_chain(&self.root)?;
        private_directory(&self.root)?;
        // AuthDocument::open can create a missing lock; status must not turn
        // an incomplete or externally deleted namespace into a fresh one.
        regular_file(&self.root.join("auth.json"))?;
        regular_file(&self.root.join("auth.lock"))?;
        let disk = AuthDocument::open(&self.root).map_err(|_| ConfigurationError::Unavailable)?;
        let document: Document = disk
            .load()
            .map_err(|_| ConfigurationError::Unavailable)?
            .ok_or(ConfigurationError::Unavailable)?;
        self.validate_document(&document)?;
        Ok(Some(ConnectionSummary::from(&document.config)))
    }

    fn validate_document(&self, document: &Document) -> Result<(), ConfigurationError> {
        if document.version != DOCUMENT_VERSION
            || document.state != DOCUMENT_STATE
            || document.profile != self.profile
            || document.workspace != self.workspace
        {
            return Err(ConfigurationError::InvalidBinding);
        }
        document
            .config
            .validate()
            .map_err(|_| ConfigurationError::Unavailable)?;
        verify_private_key(&document.config, &document.pkcs8)
            .map_err(|_| ConfigurationError::Unavailable)?;
        decode_key(&document.binding_key, 32).map_err(|_| ConfigurationError::Unavailable)?;
        Ok(())
    }
}

fn directory_chain(path: &Path) -> Result<(), ConfigurationError> {
    for component in path.ancestors() {
        match fs::symlink_metadata(component) {
            Ok(metadata) if !metadata.is_dir() || redirect(&metadata) => {
                return Err(ConfigurationError::Unavailable);
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(ConfigurationError::Unavailable),
        }
    }
    Ok(())
}

fn redirect(metadata: &Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return true;
        }
    }
    metadata.file_type().is_symlink()
}

fn regular_file(path: &Path) -> Result<(), ConfigurationError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ConfigurationError::Unavailable)?;
    if !metadata.is_file() || redirect(&metadata) {
        return Err(ConfigurationError::Unavailable);
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(ConfigurationError::Unavailable);
        }
    }
    Ok(())
}

fn private_directory(path: &Path) -> Result<(), ConfigurationError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ConfigurationError::Unavailable)?;
    if !metadata.is_dir() || redirect(&metadata) {
        return Err(ConfigurationError::Unavailable);
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.mode() & 0o077 != 0 || metadata.uid() != unsafe { libc::geteuid() } {
            return Err(ConfigurationError::Unavailable);
        }
    }
    Ok(())
}

fn sync_directory(path: &Path) -> Result<(), ConfigurationError> {
    #[cfg(unix)]
    fs::File::open(path)
        .and_then(|file| file.sync_all())
        .map_err(|_| ConfigurationError::Unavailable)?;
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

#[path = "runtime.rs"]
mod runtime;
pub(crate) use runtime::RuntimeMaterial;
