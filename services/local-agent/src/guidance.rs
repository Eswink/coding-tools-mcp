//! Bounded, read-only project guidance. Guidance text is never execution authority.
use std::{
    error::Error,
    fmt, fs,
    io::Read,
    path::{Path, PathBuf},
};

const GUIDANCE_FILE: &str = "AGENTS.md";
const HARD_MAX_DEPTH: usize = 64;
const HARD_MAX_FILES: usize = 32;
const HARD_MAX_FILE_BYTES: usize = 16 * 1024;
const HARD_MAX_TOTAL_BYTES: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct GuidanceLimits {
    max_depth: usize,
    max_files: usize,
    max_file_bytes: usize,
    max_total_bytes: usize,
}

impl GuidanceLimits {
    pub fn new(
        max_depth: usize,
        max_files: usize,
        max_file_bytes: usize,
        max_total_bytes: usize,
    ) -> Result<Self, GuidanceError> {
        if max_depth == 0
            || max_depth > HARD_MAX_DEPTH
            || max_files == 0
            || max_files > HARD_MAX_FILES
            || max_file_bytes == 0
            || max_file_bytes > HARD_MAX_FILE_BYTES
            || max_total_bytes == 0
            || max_total_bytes > HARD_MAX_TOTAL_BYTES
        {
            return Err(GuidanceError::InvalidLimits);
        }
        Ok(Self {
            max_depth,
            max_files,
            max_file_bytes,
            max_total_bytes,
        })
    }
}

impl Default for GuidanceLimits {
    fn default() -> Self {
        Self {
            max_depth: HARD_MAX_DEPTH,
            max_files: HARD_MAX_FILES,
            max_file_bytes: HARD_MAX_FILE_BYTES,
            max_total_bytes: HARD_MAX_TOTAL_BYTES,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GuidanceError {
    InvalidLimits,
    InvalidWorkspace,
    InvalidTarget,
    OutsideWorkspace,
    DepthExceeded,
    FileCountExceeded,
    FileTooLarge,
    TotalTooLarge,
    InvalidGuidanceFile,
    InvalidUtf8,
    Io,
}

impl fmt::Display for GuidanceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidLimits => "invalid guidance limits",
            Self::InvalidWorkspace => "invalid guidance workspace",
            Self::InvalidTarget => "invalid guidance target",
            Self::OutsideWorkspace => "guidance target outside workspace",
            Self::DepthExceeded => "guidance depth exceeded",
            Self::FileCountExceeded => "guidance file count exceeded",
            Self::FileTooLarge => "guidance file too large",
            Self::TotalTooLarge => "guidance total size exceeded",
            Self::InvalidGuidanceFile => "invalid guidance file",
            Self::InvalidUtf8 => "guidance must be utf-8",
            Self::Io => "guidance read failed",
        })
    }
}

impl Error for GuidanceError {}

pub struct GuidanceEntry {
    scope: PathBuf,
    text: String,
}

impl GuidanceEntry {
    pub fn scope(&self) -> &Path {
        &self.scope
    }

    /// The text is untrusted project content. It cannot grant capabilities,
    /// approvals, policy exceptions, Skills or Hook execution.
    pub fn untrusted_text(&self) -> &str {
        &self.text
    }
}

impl fmt::Debug for GuidanceEntry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GuidanceEntry")
            .field("scope", &self.scope)
            .field("text", &"<untrusted-guidance>")
            .finish()
    }
}

pub struct GuidanceSet {
    entries: Vec<GuidanceEntry>,
    total_bytes: usize,
}

impl GuidanceSet {
    pub fn entries(&self) -> &[GuidanceEntry] {
        &self.entries
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn total_bytes(&self) -> usize {
        self.total_bytes
    }
}

impl fmt::Debug for GuidanceSet {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GuidanceSet")
            .field("entries", &self.entries.len())
            .field("total_bytes", &self.total_bytes)
            .finish()
    }
}

pub struct GuidanceResolver {
    workspace_root: PathBuf,
    limits: GuidanceLimits,
}

impl fmt::Debug for GuidanceResolver {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GuidanceResolver")
            .field("workspace_root", &"<workspace>")
            .field("limits", &self.limits)
            .finish()
    }
}

impl GuidanceResolver {
    pub fn new(workspace_root: impl AsRef<Path>) -> Result<Self, GuidanceError> {
        Self::with_limits(workspace_root, GuidanceLimits::default())
    }

    pub fn with_limits(
        workspace_root: impl AsRef<Path>,
        limits: GuidanceLimits,
    ) -> Result<Self, GuidanceError> {
        let root = fs::canonicalize(workspace_root).map_err(|_| GuidanceError::InvalidWorkspace)?;
        if !fs::metadata(&root)
            .map_err(|_| GuidanceError::InvalidWorkspace)?
            .is_dir()
        {
            return Err(GuidanceError::InvalidWorkspace);
        }
        Ok(Self {
            workspace_root: root,
            limits,
        })
    }

    pub fn resolve(&self, target: impl AsRef<Path>) -> Result<GuidanceSet, GuidanceError> {
        let target = target.as_ref();
        let candidate = if target.is_absolute() {
            target.to_path_buf()
        } else {
            self.workspace_root.join(target)
        };
        let canonical = fs::canonicalize(candidate).map_err(|_| GuidanceError::InvalidTarget)?;
        if !canonical.starts_with(&self.workspace_root) {
            return Err(GuidanceError::OutsideWorkspace);
        }
        let metadata = fs::metadata(&canonical).map_err(|_| GuidanceError::InvalidTarget)?;
        let scope_dir = if metadata.is_dir() {
            canonical
        } else if metadata.is_file() {
            canonical
                .parent()
                .ok_or(GuidanceError::InvalidTarget)?
                .to_path_buf()
        } else {
            return Err(GuidanceError::InvalidTarget);
        };
        let relative = scope_dir
            .strip_prefix(&self.workspace_root)
            .map_err(|_| GuidanceError::OutsideWorkspace)?;
        let depth = relative.components().count();
        if depth > self.limits.max_depth {
            return Err(GuidanceError::DepthExceeded);
        }

        let mut directories = Vec::with_capacity(depth + 1);
        directories.push((PathBuf::from("."), self.workspace_root.clone()));
        let mut rel = PathBuf::new();
        let mut absolute = self.workspace_root.clone();
        for component in relative.components() {
            rel.push(component.as_os_str());
            absolute.push(component.as_os_str());
            directories.push((rel.clone(), absolute.clone()));
        }

        let mut entries = Vec::new();
        let mut total_bytes = 0usize;
        for (scope, directory) in directories {
            let Some((text, bytes)) = self.read_guidance(&directory)? else {
                continue;
            };
            if entries.len() >= self.limits.max_files {
                return Err(GuidanceError::FileCountExceeded);
            }
            total_bytes = total_bytes
                .checked_add(bytes)
                .ok_or(GuidanceError::TotalTooLarge)?;
            if total_bytes > self.limits.max_total_bytes {
                return Err(GuidanceError::TotalTooLarge);
            }
            entries.push(GuidanceEntry { scope, text });
        }
        Ok(GuidanceSet {
            entries,
            total_bytes,
        })
    }

    fn read_guidance(&self, directory: &Path) -> Result<Option<(String, usize)>, GuidanceError> {
        let path = directory.join(GUIDANCE_FILE);
        let metadata = match fs::symlink_metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(GuidanceError::Io),
        };
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(GuidanceError::InvalidGuidanceFile);
        }
        if metadata.len() > self.limits.max_file_bytes as u64 {
            return Err(GuidanceError::FileTooLarge);
        }
        let canonical = fs::canonicalize(&path).map_err(|_| GuidanceError::Io)?;
        if !canonical.starts_with(&self.workspace_root) {
            return Err(GuidanceError::OutsideWorkspace);
        }
        let file = fs::File::open(canonical).map_err(|_| GuidanceError::Io)?;
        let mut bytes =
            Vec::with_capacity((metadata.len() as usize).min(self.limits.max_file_bytes));
        file.take((self.limits.max_file_bytes + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| GuidanceError::Io)?;
        if bytes.len() > self.limits.max_file_bytes {
            return Err(GuidanceError::FileTooLarge);
        }
        let len = bytes.len();
        let text = String::from_utf8(bytes).map_err(|_| GuidanceError::InvalidUtf8)?;
        Ok(Some((text, len)))
    }
}

#[cfg(test)]
#[path = "guidance_tests.rs"]
mod tests;
