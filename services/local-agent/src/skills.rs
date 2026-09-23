//! Bounded, read-only local Skill discovery. Skill text is never execution authority.
use std::{
    collections::BTreeMap,
    error::Error,
    ffi::OsStr,
    fmt, fs,
    io::Read,
    path::{Component, Path, PathBuf},
};

const SKILL_FILE: &str = "SKILL.md";
const HARD_MAX_ROOTS: usize = 8;
const HARD_MAX_DEPTH: usize = 8;
const HARD_MAX_SKILLS: usize = 64;
const HARD_MAX_FILE_BYTES: usize = 64 * 1024;
const HARD_MAX_TOTAL_BYTES: usize = 512 * 1024;
const HARD_MAX_NAME_BYTES: usize = 64;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SkillLimits {
    max_roots: usize,
    max_depth: usize,
    max_skills: usize,
    max_file_bytes: usize,
    max_total_bytes: usize,
}

impl SkillLimits {
    pub fn new(
        max_roots: usize,
        max_depth: usize,
        max_skills: usize,
        max_file_bytes: usize,
        max_total_bytes: usize,
    ) -> Result<Self, SkillError> {
        if max_roots == 0
            || max_roots > HARD_MAX_ROOTS
            || max_depth == 0
            || max_depth > HARD_MAX_DEPTH
            || max_skills == 0
            || max_skills > HARD_MAX_SKILLS
            || max_file_bytes == 0
            || max_file_bytes > HARD_MAX_FILE_BYTES
            || max_total_bytes == 0
            || max_total_bytes > HARD_MAX_TOTAL_BYTES
        {
            return Err(SkillError::InvalidLimits);
        }
        Ok(Self {
            max_roots,
            max_depth,
            max_skills,
            max_file_bytes,
            max_total_bytes,
        })
    }
}

impl Default for SkillLimits {
    fn default() -> Self {
        Self {
            max_roots: HARD_MAX_ROOTS,
            max_depth: HARD_MAX_DEPTH,
            max_skills: HARD_MAX_SKILLS,
            max_file_bytes: HARD_MAX_FILE_BYTES,
            max_total_bytes: HARD_MAX_TOTAL_BYTES,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SkillError {
    InvalidLimits,
    InvalidWorkspace,
    InvalidRoot,
    OutsideWorkspace,
    SymlinkDirectory,
    DepthExceeded,
    SkillCountExceeded,
    FileTooLarge,
    TotalTooLarge,
    InvalidSkillFile,
    InvalidSkillName,
    DuplicateSkill,
    InvalidUtf8,
    Io,
}

impl fmt::Display for SkillError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidLimits => "invalid skill limits",
            Self::InvalidWorkspace => "invalid skill workspace",
            Self::InvalidRoot => "invalid skill root",
            Self::OutsideWorkspace => "skill path outside workspace",
            Self::SymlinkDirectory => "symlinked skill directory is not allowed",
            Self::DepthExceeded => "skill discovery depth exceeded",
            Self::SkillCountExceeded => "skill count exceeded",
            Self::FileTooLarge => "skill document too large",
            Self::TotalTooLarge => "skill documents total size exceeded",
            Self::InvalidSkillFile => "invalid skill document",
            Self::InvalidSkillName => "invalid skill identity",
            Self::DuplicateSkill => "duplicate skill identity",
            Self::InvalidUtf8 => "skill document must be utf-8",
            Self::Io => "skill discovery failed",
        })
    }
}

impl Error for SkillError {}

pub struct LocalSkill {
    name: String,
    scope: PathBuf,
    text: String,
}

impl LocalSkill {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn scope(&self) -> &Path {
        &self.scope
    }

    /// Untrusted content. Reading a Skill never grants execution authority.
    pub fn untrusted_text(&self) -> &str {
        &self.text
    }
}

impl fmt::Debug for LocalSkill {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("LocalSkill")
            .field("name", &self.name)
            .field("scope", &self.scope)
            .field("text", &"<untrusted-skill>")
            .finish()
    }
}

pub struct SkillCatalog {
    skills: Vec<LocalSkill>,
    total_bytes: usize,
}

impl SkillCatalog {
    pub fn skills(&self) -> &[LocalSkill] {
        &self.skills
    }

    pub fn is_empty(&self) -> bool {
        self.skills.is_empty()
    }

    pub fn total_bytes(&self) -> usize {
        self.total_bytes
    }
}

impl fmt::Debug for SkillCatalog {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SkillCatalog")
            .field("skills", &self.skills.len())
            .field("total_bytes", &self.total_bytes)
            .finish()
    }
}

pub struct SkillCatalogLoader {
    workspace_root: PathBuf,
    limits: SkillLimits,
}

impl fmt::Debug for SkillCatalogLoader {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SkillCatalogLoader")
            .field("workspace_root", &"<workspace>")
            .field("limits", &self.limits)
            .finish()
    }
}

impl SkillCatalogLoader {
    pub fn new(workspace_root: impl AsRef<Path>) -> Result<Self, SkillError> {
        Self::with_limits(workspace_root, SkillLimits::default())
    }

    pub fn with_limits(
        workspace_root: impl AsRef<Path>,
        limits: SkillLimits,
    ) -> Result<Self, SkillError> {
        let root = fs::canonicalize(workspace_root).map_err(|_| SkillError::InvalidWorkspace)?;
        if !fs::metadata(&root)
            .map_err(|_| SkillError::InvalidWorkspace)?
            .is_dir()
        {
            return Err(SkillError::InvalidWorkspace);
        }
        Ok(Self {
            workspace_root: root,
            limits,
        })
    }

    pub fn load<I, P>(&self, roots: I) -> Result<SkillCatalog, SkillError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        let mut roots: Vec<_> = roots
            .into_iter()
            .map(|root| self.resolve_root(root.as_ref()))
            .collect::<Result<_, _>>()?;
        if roots.is_empty() || roots.len() > self.limits.max_roots {
            return Err(SkillError::InvalidRoot);
        }
        roots.sort_by(|left, right| left.0.cmp(&right.0));

        let mut found = BTreeMap::new();
        let mut total_bytes = 0usize;
        for (relative, absolute) in roots {
            self.walk(&relative, &absolute, 0, &mut found, &mut total_bytes)?;
        }
        Ok(SkillCatalog {
            skills: found.into_values().collect(),
            total_bytes,
        })
    }

    fn resolve_root(&self, root: &Path) -> Result<(PathBuf, PathBuf), SkillError> {
        if root.as_os_str().is_empty()
            || root.is_absolute()
            || root.components().any(|component| {
                matches!(
                    component,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            })
        {
            return Err(SkillError::InvalidRoot);
        }
        let joined = self.workspace_root.join(root);
        let metadata = fs::symlink_metadata(&joined).map_err(|_| SkillError::InvalidRoot)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(SkillError::InvalidRoot);
        }
        let canonical = fs::canonicalize(joined).map_err(|_| SkillError::InvalidRoot)?;
        if !canonical.starts_with(&self.workspace_root) {
            return Err(SkillError::OutsideWorkspace);
        }
        let relative = canonical
            .strip_prefix(&self.workspace_root)
            .map_err(|_| SkillError::OutsideWorkspace)?
            .to_path_buf();
        if relative.as_os_str().is_empty() {
            return Err(SkillError::InvalidRoot);
        }
        Ok((relative, canonical))
    }

    fn walk(
        &self,
        relative: &Path,
        directory: &Path,
        depth: usize,
        found: &mut BTreeMap<String, LocalSkill>,
        total_bytes: &mut usize,
    ) -> Result<(), SkillError> {
        let mut entries = fs::read_dir(directory)
            .map_err(|_| SkillError::Io)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| SkillError::Io)?;
        entries.sort_by_key(|entry| entry.file_name());

        for entry in entries {
            let name = entry.file_name();
            let file_type = entry.file_type().map_err(|_| SkillError::Io)?;
            let path = entry.path();
            if file_type.is_symlink() {
                if name == OsStr::new(SKILL_FILE) {
                    return Err(SkillError::InvalidSkillFile);
                }
                if fs::metadata(&path)
                    .map(|meta| meta.is_dir())
                    .unwrap_or(false)
                {
                    return Err(SkillError::SymlinkDirectory);
                }
                continue;
            }
            if file_type.is_dir() {
                if depth >= self.limits.max_depth {
                    return Err(SkillError::DepthExceeded);
                }
                let child_relative = relative.join(&name);
                self.walk(&child_relative, &path, depth + 1, found, total_bytes)?;
                continue;
            }
            if file_type.is_file() && name == OsStr::new(SKILL_FILE) {
                self.read_skill(relative, &path, found, total_bytes)?;
            }
        }
        Ok(())
    }

    fn read_skill(
        &self,
        relative: &Path,
        path: &Path,
        found: &mut BTreeMap<String, LocalSkill>,
        total_bytes: &mut usize,
    ) -> Result<(), SkillError> {
        let identity = relative
            .file_name()
            .and_then(OsStr::to_str)
            .ok_or(SkillError::InvalidSkillName)?;
        if !valid_skill_name(identity) {
            return Err(SkillError::InvalidSkillName);
        }
        if found.contains_key(identity) {
            return Err(SkillError::DuplicateSkill);
        }

        let metadata = fs::symlink_metadata(path).map_err(|_| SkillError::Io)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(SkillError::InvalidSkillFile);
        }
        if metadata.len() > self.limits.max_file_bytes as u64 {
            return Err(SkillError::FileTooLarge);
        }
        let canonical = fs::canonicalize(path).map_err(|_| SkillError::Io)?;
        if !canonical.starts_with(&self.workspace_root) {
            return Err(SkillError::OutsideWorkspace);
        }
        let file = fs::File::open(canonical).map_err(|_| SkillError::Io)?;
        let mut bytes =
            Vec::with_capacity((metadata.len() as usize).min(self.limits.max_file_bytes));
        file.take((self.limits.max_file_bytes + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| SkillError::Io)?;
        if bytes.len() > self.limits.max_file_bytes {
            return Err(SkillError::FileTooLarge);
        }
        let next_total = total_bytes
            .checked_add(bytes.len())
            .ok_or(SkillError::TotalTooLarge)?;
        if next_total > self.limits.max_total_bytes {
            return Err(SkillError::TotalTooLarge);
        }
        if found.len() >= self.limits.max_skills {
            return Err(SkillError::SkillCountExceeded);
        }
        let text = String::from_utf8(bytes).map_err(|_| SkillError::InvalidUtf8)?;
        *total_bytes = next_total;
        found.insert(
            identity.to_owned(),
            LocalSkill {
                name: identity.to_owned(),
                scope: relative.to_path_buf(),
                text,
            },
        );
        Ok(())
    }
}

fn valid_skill_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= HARD_MAX_NAME_BYTES
        && value.as_bytes()[0].is_ascii_lowercase()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"-_".contains(&byte))
}

#[cfg(test)]
#[path = "skills_tests.rs"]
mod tests;
