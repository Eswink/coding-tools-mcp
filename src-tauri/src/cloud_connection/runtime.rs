//! Native-only materialization. Nothing in this module is serializable to IPC.
use super::*;
use crate::auth::cloud_context::CloudTransport;
use coding_tools_cloud_agent::AgentConfig;
use serde_json::json;

pub(crate) struct RuntimeMaterial {
    pub config: Vec<u8>,
    pub key: Zeroizing<Vec<u8>>,
    pub link: CloudTransport,
    pub root: PathBuf,
    pub authority_epoch: i64,
}
impl ConnectionStore {
    pub(crate) fn runtime_material(&self) -> Result<RuntimeMaterial, ConfigurationError> {
        directory_chain(&self.root)?;
        private_directory(&self.root)?;
        regular_file(&self.root.join("auth.json"))?;
        regular_file(&self.root.join("auth.lock"))?;
        let disk = AuthDocument::open(&self.root).map_err(|_| ConfigurationError::Unavailable)?;
        let document: Document = disk
            .load()
            .map_err(|_| ConfigurationError::Unavailable)?
            .ok_or(ConfigurationError::Unavailable)?;
        self.validate_document(&document)?;
        let cfg = &document.config;
        let root = self.root.join("runtime-v1");
        let config = serde_json::to_vec(&json!({
            "origin": cfg.origin, "prefix": cfg.prefix, "connector": cfg.connector,
            "device": cfg.device, "device_epoch": cfg.device_epoch,
            "authority_epoch": cfg.authority_epoch, "public_key": cfg.public_key,
            "run_seconds": cfg.run_seconds, "revision_file": root.join("revision.bin"),
            "ca_der_file": null,
        }))
        .map_err(|_| ConfigurationError::Unavailable)?;
        let checked =
            AgentConfig::from_bytes(&config).map_err(|_| ConfigurationError::Unavailable)?;
        let link = CloudTransport::new(
            &self.profile,
            Path::new(&self.workspace),
            &cfg.origin,
            &cfg.prefix,
            checked.connector,
            checked.device,
            cfg.device_epoch as u64,
            &document.binding_key,
        )
        .map_err(|_| ConfigurationError::InvalidBinding)?;
        // Serialize directly into a zeroizing byte buffer. No Debug implementation
        // or intermediate JSON Value containing private key material is retained.
        #[derive(Serialize)]
        struct Key<'a> {
            pkcs8: &'a str,
        }
        let key = Zeroizing::new(
            serde_json::to_vec(&Key {
                pkcs8: &document.pkcs8,
            })
            .map_err(|_| ConfigurationError::Unavailable)?,
        );
        Ok(RuntimeMaterial {
            config,
            key,
            link,
            root,
            authority_epoch: cfg.authority_epoch,
        })
    }
}
impl RuntimeMaterial {
    /// Called only after this application's lifecycle has reserved the workspace.
    /// Partial setup remains occupied on disk forever; retry cannot overwrite it.
    pub(crate) fn prepare_journals(&self, initialize: bool) -> Result<PathBuf, ConfigurationError> {
        directory_chain(&self.root)?;
        if initialize {
            let mut builder = fs::DirBuilder::new();
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            builder
                .recursive(false)
                .create(&self.root)
                .map_err(|error| {
                    if error.kind() == std::io::ErrorKind::AlreadyExists {
                        ConfigurationError::AlreadyInitialized
                    } else {
                        ConfigurationError::Unavailable
                    }
                })?;
            sync_directory(self.root.parent().ok_or(ConfigurationError::Unavailable)?)?;
            private_directory(&self.root)?;
            builder
                .create(self.root.join("projection"))
                .map_err(|_| ConfigurationError::Unavailable)?;
            sync_directory(&self.root)?;
        } else {
            private_directory(&self.root)?;
            private_directory(&self.root.join("projection"))?;
            for name in [
                "executions.bin",
                "projection/auth.json",
                "projection/auth.lock",
            ] {
                regular_file(&self.root.join(name))?;
            }
        }
        // HostJournal requires an already canonical parent. On Windows this
        // includes the verbatim path prefix; retain the strict journal check.
        // Resolve only after create-once setup and no-reparse validation.
        directory_chain(&self.root)?;
        self.root.canonicalize().map_err(|_| ConfigurationError::Unavailable)
    }
}

#[cfg(test)]
impl ConnectionStore {
    pub(crate) fn application_test_store(root: PathBuf, profile: &str, workspace: &Path) -> Self {
        Self::at(root, profile, workspace).unwrap()
    }
}
