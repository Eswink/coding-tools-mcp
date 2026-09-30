use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::Path;

pub const MAX_ENTRIES: usize = 256;
pub const MAX_FILE: u64 = 1024 * 1024;
pub const MAX_TOTAL: u64 = 16 * 1024 * 1024;
pub const MAX_OBJECTS: usize = 16;
pub const MAX_METADATA: u64 = 8 * 1024 * 1024;
pub type Result<T> = std::result::Result<T, SnapshotError>;
pub fn bounded_json<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    struct Buffer {
        bytes: Vec<u8>,
        exceeded: bool,
    }
    impl std::io::Write for Buffer {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            if bytes.len() > MAX_METADATA as usize - self.bytes.len() {
                self.exceeded = true;
                return Err(std::io::Error::other("snapshot metadata capacity"));
            }
            self.bytes.extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }
    let mut buffer = Buffer {
        bytes: Vec::new(),
        exceeded: false,
    };
    if serde_json::to_writer(&mut buffer, value).is_err() {
        return Err(if buffer.exceeded {
            SnapshotError::Capacity
        } else {
            SnapshotError::Corrupt
        });
    }
    Ok(buffer.bytes)
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SnapshotError {
    Unsupported,
    Boundary,
    Protected,
    Capacity,
    Changed,
    Corrupt,
    Unavailable,
    Busy,
    Approval,
    Expired,
    RecoveryRequired,
}
impl std::fmt::Display for SnapshotError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Snapshot operation refused: {:?}", self)
    }
}
impl std::error::Error for SnapshotError {}
impl From<std::io::Error> for SnapshotError {
    fn from(_: std::io::Error) -> Self {
        Self::Unavailable
    }
}

/// Only host-native code implements this trait; never deserialize a root from IPC.
pub(crate) trait TargetAuthority {
    fn root(&self) -> &Path;
    fn workspace_id(&self) -> &str;
    fn worktree_id(&self) -> &str;
    fn head(&self) -> &str;
    fn verify(&self) -> Result<()>;
    /// Production Windows restore stays closed until all security metadata can be retained.
    /// Native code must not infer this proof from an IPC boolean or a successful DACL fixture.
    fn verify_restore_metadata(&self) -> Result<()> {
        if cfg!(windows) {
            Err(SnapshotError::Unsupported)
        } else {
            Ok(())
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub path: String,
    pub directory: bool,
    pub size: u64,
    pub hash: String,
    pub mode: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub security: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attributes: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub uid: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gid: Option<u32>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub version: u32,
    pub id: String,
    pub workspace_id: String,
    pub worktree_id: String,
    pub head: String,
    pub root_identity: String,
    pub entries: Vec<Entry>,
    pub bytes: u64,
    pub digest: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Change {
    pub path: String,
    pub action: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RestorePlan {
    pub id: String,
    pub snapshot_id: String,
    pub workspace_id: String,
    pub worktree_id: String,
    pub head: String,
    pub root_identity: String,
    pub current_digest: String,
    pub snapshot_digest: String,
    pub expires_at: u64,
    pub changes: Vec<Change>,
    pub before: Vec<Entry>,
    pub approval_digest: String,
}
#[derive(Clone, Debug, Serialize)]
pub struct RestoreReport {
    pub transaction_id: String,
    pub restored_digest: String,
    pub retained_backup: bool,
}
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn entries_digest(entries: &[Entry]) -> Result<String> {
    Ok(hash(
        &serde_json::to_vec(entries).map_err(|_| SnapshotError::Corrupt)?,
    ))
}
pub fn plan_digest(plan: &RestorePlan) -> Result<String> {
    let mut value = plan.clone();
    value.approval_digest.clear();
    Ok(hash(
        &serde_json::to_vec(&value).map_err(|_| SnapshotError::Corrupt)?,
    ))
}
pub fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub fn valid_hash(id: &str) -> bool {
    id.len() == 64
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|v| v.as_secs())
        .unwrap_or(u64::MAX)
}
pub fn safe_component(name: &str) -> Result<()> {
    if name.is_empty()
        || name.len() > 200
        || name == "."
        || name == ".."
        || name.ends_with('.')
        || name.ends_with(' ')
        || name
            .chars()
            .any(|c| c.is_control() || "/\\:<>\"|?*".contains(c))
    {
        return Err(SnapshotError::Boundary);
    }
    let base = name.split('.').next().unwrap_or("").to_ascii_lowercase();
    if matches!(
        base.as_str(),
        "con"
            | "prn"
            | "aux"
            | "nul"
            | "com1"
            | "com2"
            | "com3"
            | "com4"
            | "com5"
            | "com6"
            | "com7"
            | "com8"
            | "com9"
            | "lpt1"
            | "lpt2"
            | "lpt3"
            | "lpt4"
            | "lpt5"
            | "lpt6"
            | "lpt7"
            | "lpt8"
            | "lpt9"
    ) {
        return Err(SnapshotError::Boundary);
    }
    Ok(())
}
pub fn content_component(name: &str) -> Result<()> {
    safe_component(name)?;
    let lower = name.to_ascii_lowercase();
    // Refuse rather than silently omit possibly sensitive user content.
    if (lower.starts_with('.') && !matches!(lower.as_str(), ".gitignore" | ".gitattributes"))
        || lower.contains("credential")
        || lower.contains("secret")
        || lower.ends_with(".pem")
        || lower.ends_with(".key")
        || lower == "id_rsa"
        || lower == "id_ed25519"
        || lower.contains("journal")
        || lower.contains("tombstone")
        || lower.contains("authority")
    {
        return Err(SnapshotError::Protected);
    }
    Ok(())
}
pub fn validate_entries(entries: &[Entry]) -> Result<()> {
    if entries.len() > MAX_ENTRIES {
        return Err(SnapshotError::Capacity);
    }
    let mut names = std::collections::BTreeSet::new();
    let mut bytes = 0;
    for entry in entries {
        #[cfg(target_os = "linux")]
        if entry.uid != Some(unsafe { libc::geteuid() })
            || entry.gid != Some(unsafe { libc::getegid() })
        {
            return Err(SnapshotError::Unsupported);
        }
        #[cfg(windows)]
        if entry.uid.is_some() || entry.gid.is_some() {
            return Err(SnapshotError::Corrupt);
        }
        #[cfg(windows)]
        if entry
            .security
            .as_ref()
            .is_none_or(|s| s.is_empty() || s.len() > 16384)
            || entry.attributes.is_none_or(|a| a & !0x27 != 0)
        {
            return Err(SnapshotError::Corrupt);
        }
        #[cfg(not(windows))]
        if entry.security.is_some() || entry.attributes.is_some() {
            return Err(SnapshotError::Unsupported);
        }
        for part in entry.path.split('/') {
            content_component(part)?;
        }
        if !names.insert(&entry.path) || entry.mode & !0o777 != 0 {
            return Err(SnapshotError::Corrupt);
        }
        if entry.directory {
            if entry.size != 0 || !entry.hash.is_empty() {
                return Err(SnapshotError::Corrupt);
            }
        } else {
            if entry.size > MAX_FILE || !valid_hash(&entry.hash) {
                return Err(SnapshotError::Corrupt);
            }
            bytes += entry.size;
        }
        if let Some((parent, _)) = entry.path.rsplit_once('/') {
            if !entries.iter().any(|e| e.path == parent && e.directory) {
                return Err(SnapshotError::Corrupt);
            }
        }
    }
    if bytes > MAX_TOTAL || entries.windows(2).any(|pair| pair[0].path >= pair[1].path) {
        return Err(SnapshotError::Corrupt);
    }
    Ok(())
}

#[cfg(test)]
mod bounded_tests {
    use super::*;
    #[test]
    fn metadata_json_limit_is_enforced_before_publication() {
        let limit = MAX_METADATA as usize;
        assert_eq!(bounded_json(&"a".repeat(limit - 2)).unwrap().len(), limit);
        assert_eq!(
            bounded_json(&"a".repeat(limit - 1)),
            Err(SnapshotError::Capacity)
        );
        assert_eq!(
            bounded_json(&"\n".repeat(limit / 2)),
            Err(SnapshotError::Capacity)
        );
    }
}
