//! Encrypted disk boundary, shared by production and provider-injected tests.
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use zeroize::Zeroizing;

use crate::error::{AppError, AppResult};
use super::{encrypted_config as codec, key_store::KeyStore};

pub(super) struct Vault<'a> {
    keys: &'a dyn KeyStore,
}

impl<'a> Vault<'a> {
    pub(super) fn new(keys: &'a dyn KeyStore) -> Self { Self { keys } }

    pub(super) fn read(&self, path: &Path) -> AppResult<(Zeroizing<String>, bool)> {
        let raw = read_bounded(path)?;
        match codec::parse_envelope(&raw)? {
            Some(envelope) => Ok((codec::open(&envelope, self.keys)?, true)),
            None => Ok((raw, false)),
        }
    }

    /// The caller holds the configuration lock. Never create a new key for an
    /// existing envelope, even when its system credential has disappeared.
    pub(super) fn write(&self, path: &Path, plaintext: &str) -> AppResult<()> {
        let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
        let mut builder = fs::DirBuilder::new();
        builder.recursive(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(parent)?;
        let existing = match read_bounded(path) {
            Ok(raw) => Some(raw),
            Err(AppError::Io(error)) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => return Err(error),
        };
        let envelope = existing.as_ref().map(|raw| codec::parse_envelope(raw)).transpose()?.flatten();
        let (id, allow_create) = if let Some(envelope) = envelope {
            // Authenticate before replacing a file, not just trusting its key ID.
            let _verified = codec::open(&envelope, self.keys)?;
            (envelope.key_id, false)
        } else {
            (codec::key_id_for_path(path)?, true)
        };
        let encrypted = codec::seal(plaintext, &id, allow_create, self.keys)?;
        atomic_replace(path, encrypted.as_bytes())
    }

    /// A task namespace reuses ONE key, rather than leaking a credential entry
    /// for every completed job. Scope binding also rejects copied ciphertext.
    pub(super) fn read_scoped(&self, path: &Path, key_id: &str) -> AppResult<Zeroizing<String>> {
        let raw = read_bounded(path)?;
        let envelope = codec::parse_envelope(&raw)?.ok_or_else(|| AppError::Message("任务记录必须加密；原文件已保留。".into()))?;
        if envelope.key_id != key_id { return Err(AppError::Message("任务记录不属于当前命名空间。".into())); }
        codec::open(&envelope, self.keys)
    }

    pub(super) fn write_scoped(&self, path: &Path, plaintext: &str, key_id: &str, allow_create: bool) -> AppResult<()> {
        match read_bounded(path) {
            Ok(_) => { let _verified = self.read_scoped(path, key_id)?; },
            Err(AppError::Io(err)) if err.kind() == std::io::ErrorKind::NotFound => {},
            Err(err) => return Err(err),
        }
        let encrypted = codec::seal(plaintext, key_id, allow_create, self.keys)?;
        atomic_replace(path, encrypted.as_bytes())
    }

    pub(super) fn protect_legacy(&self, path: &Path) -> AppResult<()> {
        let (raw, encrypted) = self.read(path)?;
        if !encrypted { self.write(path, &raw)?; }
        Ok(())
    }
}

fn read_bounded(path: &Path) -> AppResult<Zeroizing<String>> {
    if fs::symlink_metadata(path)?.file_type().is_symlink() {
        return Err(AppError::Message("配置文件不能是符号链接；原文件已保留。".into()));
    }
    let file = fs::File::open(path)?;
    if file.metadata()?.len() > codec::MAX_DOCUMENT {
        return Err(AppError::Message("配置超过安全大小限制，原文件已保留。".into()));
    }
    let mut raw = Zeroizing::new(String::new());
    file.take(codec::MAX_DOCUMENT + 1).read_to_string(&mut raw)?;
    if raw.len() as u64 > codec::MAX_DOCUMENT {
        return Err(AppError::Message("配置超过安全大小限制，原文件已保留。".into()));
    }
    Ok(raw)
}

/// Same-directory rename is the sole commit point. A failed write/rename never
/// removes the old destination; both temporary and destination contain ciphertext.
fn atomic_replace(path: &Path, bytes: &[u8]) -> AppResult<()> {
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    let temporary = parent.join(format!(".profiles-{}.tmp", uuid::Uuid::new_v4()));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    let _cleanup = TemporaryFile(temporary.clone());
    file.write_all(bytes)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    drop(file);
    fs::rename(&temporary, path)?;
    #[cfg(unix)]
    if fs::File::open(parent).and_then(|dir| dir.sync_all()).is_err() {
        // The rename has committed; do not report a false pre-commit rollback.
        eprintln!("配置已原子替换，但目录同步失败；请检查存储设备。");
    }
    Ok(())
}

struct TemporaryFile(PathBuf);
impl Drop for TemporaryFile {
    fn drop(&mut self) { let _ = fs::remove_file(&self.0); }
}

#[cfg(test)]
#[path = "配置文件回归v6.rs"]
mod tests;

#[cfg(all(test, feature = "native-keyring-tests"))]
#[path = "原生凭据回归v6.rs"]
mod native_tests;
