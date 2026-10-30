use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;
use uuid::Uuid;

use super::worktree_git::{git_path_arg, list_registered_under, run_git};

const MAX_MANAGED_WORKTREES: usize = 8;
const OPAQUE_ID_LEN: usize = 32;
/// A1 C4 (N1): legacy chat-v1 conversation roots scanned per listing.
const LEGACY_ROOT_LIMIT: usize = 256;

#[cfg(test)]
thread_local! {
    /// Test seam (A1 C4 N1): `git worktree list` runs made by legacy scans.
    static LEGACY_GIT_RUNS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    /// Test seam (A1 C2-ad NB3): broken legacy registrations skipped by the last scan.
    static LEGACY_BROKEN: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ManagedWorktree {
    pub id: String,
    pub display_path: String,
    pub head: String,
    pub detached: bool,
    /// A1 C3: a pre-C1-b tree under a session's `chat-v1/<key>` harness root.
    /// Counted against the main-root slots and listed, never moved or removed here.
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub legacy: bool,
}

#[derive(Clone, Eq, PartialEq)]
pub struct WorktreeError {
    code: &'static str,
    message: &'static str,
    /// A1 C2-ad (N2, v5 §1.7): set on CAPACITY when legacy trees alone fill
    /// the shared slots, so callers can answer `details.legacy_slots` + hint.
    legacy_slots: Option<usize>,
}

impl WorktreeError {
    pub(super) fn new(code: &'static str, message: &'static str) -> Self {
        Self {
            code,
            message,
            legacy_slots: None,
        }
    }
    pub fn code(&self) -> &'static str {
        self.code
    }
    /// The legacy tree count when legacy trees alone fill the eight slots.
    pub fn legacy_slots(&self) -> Option<usize> {
        self.legacy_slots
    }
}

impl fmt::Debug for WorktreeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("WorktreeError")
            .field("code", &self.code)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for WorktreeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message)
    }
}

impl std::error::Error for WorktreeError {}

pub type WorktreeResult<T> = Result<T, WorktreeError>;

#[derive(Clone)]
pub struct WorktreeManager {
    repository_root: PathBuf,
    harness_root: PathBuf,
    managed_root: PathBuf,
    workspace_id: String,
    root_identities: Vec<(PathBuf, super::worktree_boundary::FileIdentity)>,
}

impl fmt::Debug for WorktreeManager {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("WorktreeManager")
            .field("workspace_id", &self.workspace_id)
            .field("max_managed", &MAX_MANAGED_WORKTREES)
            .finish()
    }
}

impl WorktreeManager {
    pub fn new(
        workspace_root: &Path,
        harness_root: &Path,
        workspace_id: &str,
    ) -> WorktreeResult<Self> {
        if !valid_id(workspace_id) {
            return Err(error("INVALID_ID", "Invalid workspace identifier."));
        }
        let workspace_root = canonical_directory(workspace_root, "Workspace is unavailable.")?;
        let harness_root = canonical_directory(harness_root, "Harness state root is unavailable.")?;
        if workspace_root.starts_with(&harness_root) || harness_root.starts_with(&workspace_root) {
            return Err(boundary_error());
        }
        let repository_root = discover_repository_root(&workspace_root)?;
        if !repository_root.starts_with(&workspace_root) {
            return Err(boundary_error());
        }
        let worktrees_root = harness_root.join("worktrees-v1");
        ensure_owned_directory(&worktrees_root)?;
        let managed_root = worktrees_root.join(workspace_id);
        ensure_owned_directory(&managed_root)?;
        let managed_root = managed_root.canonicalize().map_err(|_| io_failure())?;
        if !managed_root.starts_with(&harness_root) {
            return Err(boundary_error());
        }
        let root_identities = [
            &repository_root,
            &harness_root,
            &worktrees_root,
            &managed_root,
        ]
        .into_iter()
        .map(|path| super::worktree_boundary::identity(path).map(|id| (path.clone(), id)))
        .collect::<WorktreeResult<Vec<_>>>()?;
        Ok(Self {
            root_identities,
            repository_root,
            harness_root,
            managed_root,
            workspace_id: workspace_id.to_owned(),
        })
    }
    pub fn create_detached(&self) -> WorktreeResult<ManagedWorktree> {
        let _guard = native::lock()?;
        // Not-yet-built worker reservations share the same eight-slot budget.
        self.ensure_free_slot(MAX_MANAGED_WORKTREES)?;
        let (id, target) = self.allocate()?;
        self.add_locked(id, target)
    }
    fn allocate(&self) -> WorktreeResult<(String, PathBuf)> {
        (0..16)
            .find_map(|_| {
                let id = Uuid::new_v4().simple().to_string();
                let target = self.managed_root.join(&id);
                (!target.exists()
                    && !target.is_symlink()
                    && !reservations::holds(&self.managed_root, &id))
                .then_some((id, target))
            })
            .ok_or_else(|| error("CAPACITY", "Unable to allocate managed worktree."))
    }
    /// Reserves one of the eight managed slots under the native lifecycle lock and
    /// pins the opaque id the later build will use. Dropping the guard frees the slot.
    pub(crate) fn reserve_slot(&self) -> WorktreeResult<SlotReservation> {
        let _guard = native::lock()?;
        self.ensure_free_slot(MAX_MANAGED_WORKTREES)?;
        let (id, _) = self.allocate()?;
        Ok(reservations::take(&self.managed_root, id))
    }
    /// Releases an unused reservation while the native lifecycle lock is held, so
    /// the slot never frees outside the lock a concurrent create counts under (C1-a).
    /// Test seam (A1 C3): fail this thread's next lifecycle lock acquisition.
    #[cfg(test)]
    pub(crate) fn fail_next_lifecycle_lock_for_test() {
        native::fail_next_lock_for_test();
    }
    pub(crate) fn release_slot(&self, slot: SlotReservation) {
        // A1 C3: an Err from native::lock() (poisoned mutex) still releases inside
        // the lock; lock_for_release recovers the guard instead of skipping it.
        let guard = native::lock().unwrap_or_else(|_| native::lock_for_release());
        drop(slot);
        drop(guard);
    }
    /// Builds the worktree for a reservation. The slot is released while the native
    /// lifecycle lock is still held on every path, early returns included (SPEC-A1 v4 N4).
    pub(crate) fn create_reserved(&self, slot: SlotReservation) -> WorktreeResult<ManagedWorktree> {
        let guard = match native::lock() {
            Ok(guard) => guard,
            Err(error) => {
                // A1 C3: never drop the reservation on the early-return path.
                self.release_slot(slot);
                return Err(error);
            }
        };
        let result = self.build_reserved(&slot);
        drop(slot);
        drop(guard);
        result
    }
    fn build_reserved(&self, slot: &SlotReservation) -> WorktreeResult<ManagedWorktree> {
        if slot.root() != self.managed_root.as_path() || !valid_id(slot.id()) {
            return Err(boundary_error());
        }
        // The slot being built is itself one of the counted reservations.
        self.ensure_free_slot(MAX_MANAGED_WORKTREES + 1)?;
        let id = slot.id().to_owned();
        let target = self.managed_root.join(&id);
        if target.exists() || target.is_symlink() {
            return Err(boundary_error());
        }
        self.add_locked(id, target)
    }
    fn add_locked(&self, id: String, target: PathBuf) -> WorktreeResult<ManagedWorktree> {
        let args = vec![
            OsString::from("worktree"),
            OsString::from("add"),
            OsString::from("--detach"),
            git_path_arg(&target),
            OsString::from("HEAD"),
        ];
        let output = run_git(
            &self.repository_root,
            &args,
            &self.repository_root,
            Some(&self.managed_root),
        )?;
        if !output.success {
            cleanup_empty_directory(&target);
            return Err(git_failed());
        }
        let item = self
            .list()?
            .into_iter()
            .find(|item| item.id == id)
            .ok_or_else(|| error("GIT_FAILED", "Git did not register the managed worktree."))?;
        Ok(item)
    }
    pub fn list(&self) -> WorktreeResult<Vec<ManagedWorktree>> {
        self.validate_boundary()?;
        let registry = self.registry_entries()?;
        let mut managed = Vec::new();
        for entry in registry {
            let raw_path = entry.path;
            let lexical_managed = raw_path.starts_with(&self.managed_root);
            if fs::symlink_metadata(&raw_path).is_ok_and(|metadata| is_link_or_reparse(&metadata)) {
                if lexical_managed {
                    return Err(boundary_error());
                }
                continue;
            }
            let canonical = match raw_path.canonicalize() {
                Ok(path) => path,
                Err(_) if lexical_managed => return Err(boundary_error()),
                Err(_) => continue,
            };
            if !canonical.starts_with(&self.managed_root) {
                if lexical_managed {
                    return Err(boundary_error());
                }
                continue;
            }
            if canonical.parent() != Some(self.managed_root.as_path()) {
                return Err(boundary_error());
            }
            let id = canonical
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(boundary_error)?;
            if !valid_id(id) || !entry.detached {
                return Err(boundary_error());
            }
            let head = entry
                .head
                .as_deref()
                .filter(|head| valid_head(head))
                .ok_or_else(|| error("PARSE_FAILED", "Git worktree metadata is invalid."))?;
            managed.push(ManagedWorktree {
                id: id.to_owned(),
                display_path: format!("managed/{id}"),
                head: head.to_owned(),
                detached: true,
                legacy: false,
            });
        }
        managed.sort_by(|left, right| left.id.cmp(&right.id));
        if managed.len() > MAX_MANAGED_WORKTREES {
            return Err(error("CAPACITY", "Managed worktree capacity exceeded."));
        }
        Ok(managed)
    }
    /// A1 C3: slots held on this main root: its managed trees, the legacy
    /// chat-v1 trees of the same workspace, and not-yet-built reservations.
    fn slots_in_use(&self) -> WorktreeResult<(usize, usize)> {
        let legacy = self.legacy_list()?.len();
        Ok((
            self.list()?.len() + legacy + reservations::count(&self.managed_root),
            legacy,
        ))
    }
    /// CAPACITY when `limit` or more slots are in use. A1 C2-ad (N2, v5 §1.7):
    /// when the legacy trees alone hold all eight, the error carries their count
    /// (`details.legacy_slots`, `hint:"local_cleanup"`); nothing is migrated or removed.
    fn ensure_free_slot(&self, limit: usize) -> WorktreeResult<()> {
        let (used, legacy) = self.slots_in_use()?;
        if used < limit {
            return Ok(());
        }
        let mut capacity = error("CAPACITY", "Managed worktree capacity reached.");
        if legacy >= MAX_MANAGED_WORKTREES {
            capacity.legacy_slots = Some(legacy);
        }
        Err(capacity)
    }
    #[cfg(test)]
    pub(crate) fn legacy_scan_warnings_for_test(&self) -> (Vec<ManagedWorktree>, usize) {
        LEGACY_BROKEN.with(|count| count.set(0));
        let (items, _) = self.legacy_scan().expect("legacy scan");
        (items, LEGACY_BROKEN.with(|count| count.get()))
    }
    /// A1 C3: the managed trees followed by the legacy chat-v1 trees (by id).
    pub fn list_with_legacy(&self) -> WorktreeResult<Vec<ManagedWorktree>> {
        let mut items = self.list()?;
        items.extend(self.legacy_list()?);
        items.sort_by(|left, right| left.id.cmp(&right.id));
        Ok(items)
    }
    /// A1 C3 (C1-b orphans): Git-registered trees at
    /// `<harness_root>/chat-v1/<64 hex>/worktrees-v1/<workspace_id>/<id>`, i.e. the
    /// per-session roots worktree tools used before C1-b. Read-only: nothing is
    /// moved. Links, other workspaces and non-detached entries are ignored.
    fn legacy_list(&self) -> WorktreeResult<Vec<ManagedWorktree>> {
        let (legacy, skipped) = self.legacy_scan()?;
        if skipped > 0 {
            // A1 C4 (N1): never fail create/spawn/list over too many legacy roots.
            eprintln!(
                "warning: {skipped} legacy chat-v1 conversation roots beyond {LEGACY_ROOT_LIMIT} were skipped"
            );
        }
        Ok(legacy)
    }
    /// A1 C4 (N1): only real `chat-v1/<64 hex>` directories that hold a real
    /// `worktrees-v1` directory are counted; files and other names are skipped.
    /// Beyond [`LEGACY_ROOT_LIMIT`] such roots (by name) the rest are skipped and
    /// reported, never an error. `git worktree list` runs once, filtered by parent.
    fn legacy_scan(&self) -> WorktreeResult<(Vec<ManagedWorktree>, usize)> {
        let (rooted, skipped) = self.legacy_scan_rooted()?;
        Ok((rooted.into_iter().map(|(item, _)| item).collect(), skipped))
    }
    /// [`Self::legacy_scan`] with each tree's legacy managed root
    /// (`chat-v1/<key>/worktrees-v1/<ws>`), for the local cleanup path (N2).
    fn legacy_scan_rooted(&self) -> WorktreeResult<(Vec<(ManagedWorktree, PathBuf)>, usize)> {
        let real_dir = |path: &Path| {
            fs::symlink_metadata(path).is_ok_and(|m| m.is_dir() && !is_link_or_reparse(&m))
        };
        let base = self.harness_root.join("chat-v1");
        if !real_dir(&base) || base.canonicalize().ok().as_deref() != Some(base.as_path()) {
            return Ok((Vec::new(), 0));
        }
        let hex = |s: &str| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit());
        let mut names = Vec::new();
        for entry in fs::read_dir(&base).map_err(|_| io_failure())? {
            let Ok(entry) = entry else { continue };
            let Some(name) = entry
                .file_name()
                .to_str()
                .filter(|name| hex(name))
                .map(str::to_owned)
            else {
                continue;
            };
            let path = base.join(&name);
            if real_dir(&path) && real_dir(&path.join("worktrees-v1")) {
                names.push(name);
            }
        }
        names.sort();
        let skipped = names.len().saturating_sub(LEGACY_ROOT_LIMIT);
        names.truncate(LEGACY_ROOT_LIMIT);
        let roots: Vec<PathBuf> = names
            .iter()
            .map(|name| {
                base.join(name)
                    .join("worktrees-v1")
                    .join(&self.workspace_id)
            })
            .filter(|root| {
                real_dir(root) && root.canonicalize().ok().as_deref() == Some(root.as_path())
            })
            .collect();
        if roots.is_empty() {
            return Ok((Vec::new(), skipped));
        }
        #[cfg(test)]
        LEGACY_GIT_RUNS.with(|runs| runs.set(runs.get() + 1));
        let mut legacy = Vec::new();
        let (entries, broken) = list_registered_under(&self.repository_root, &roots)?;
        #[cfg(test)]
        LEGACY_BROKEN.with(|count| count.set(broken));
        #[cfg(not(test))]
        let _ = broken;
        for (index, id, head) in entries {
            if valid_id(&id) && valid_head(&head) {
                legacy.push((
                    ManagedWorktree {
                        display_path: format!("legacy/{id}"),
                        id,
                        head,
                        detached: true,
                        legacy: true,
                    },
                    roots[index].clone(),
                ));
            }
        }
        legacy.sort_by(|left, right| left.0.id.cmp(&right.0.id));
        Ok((legacy, skipped))
    }
    pub fn remove_clean(&self, id: &str) -> WorktreeResult<()> {
        let _guard = native::lock()?;
        self.remove_clean_locked(id)
    }
    /// [`Self::remove_clean`] for a caller already holding the lifecycle lock.
    fn remove_clean_locked(&self, id: &str) -> WorktreeResult<()> {
        if !valid_id(id) {
            return Err(error("INVALID_ID", "Invalid managed worktree identifier."));
        }
        let item = self.list()?.into_iter().find(|item| item.id == id);
        let Some(item) = item else {
            if self.legacy_list()?.iter().any(|item| item.id == id) {
                return Err(error(
                    "LEGACY_WORKTREE",
                    "This worktree belongs to a pre-0.8 conversation root and is not removed here.",
                ));
            }
            // Absence is retry-safe only when no unregistered filesystem entry remains.
            return match fs::symlink_metadata(self.managed_root.join(id)) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                _ => Err(boundary_error()),
            };
        };
        let target = self.managed_root.join(&item.id);
        let target = target.canonicalize().map_err(|_| boundary_error())?;
        if target.parent() != Some(self.managed_root.as_path()) || target.is_symlink() {
            return Err(boundary_error());
        }
        let status = run_git(
            &target,
            &[
                OsString::from("status"),
                OsString::from("--porcelain=v1"),
                OsString::from("--untracked-files=all"),
                OsString::from("--ignored"),
                OsString::from("-z"),
            ],
            &self.repository_root,
            Some(&self.managed_root),
        )?;
        if !status.success {
            return Err(git_failed());
        }
        if !status.stdout.is_empty() {
            return Err(error("DIRTY", "Managed worktree contains local changes."));
        }
        let output = run_git(
            &self.repository_root,
            &[
                OsString::from("worktree"),
                OsString::from("remove"),
                git_path_arg(&target),
            ],
            &self.repository_root,
            Some(&self.managed_root),
        )?;
        if !output.success || target.exists() || self.list()?.iter().any(|value| value.id == id) {
            return Err(git_failed());
        }
        Ok(())
    }
    fn validate_boundary(&self) -> WorktreeResult<()> {
        for (path, expected) in &self.root_identities {
            if &super::worktree_boundary::identity(path)? != expected {
                return Err(boundary_error());
            }
        }
        for path in [
            self.repository_root.clone(),
            self.harness_root.clone(),
            self.harness_root.join("worktrees-v1"),
            self.managed_root.clone(),
        ] {
            let canonical = canonical_directory(&path, "Managed directory is unavailable.")?;
            if canonical != path {
                return Err(boundary_error());
            }
        }
        Ok(())
    }
    fn registry_entries(&self) -> WorktreeResult<Vec<RegistryEntry>> {
        let output = run_git(
            &self.repository_root,
            &[
                OsString::from("worktree"),
                OsString::from("list"),
                OsString::from("--porcelain"),
                OsString::from("-z"),
            ],
            &self.repository_root,
            Some(&self.managed_root),
        )?;
        if !output.success {
            return Err(git_failed());
        }
        parse_registry(&output.stdout)
    }
}

#[derive(Default)]
struct RegistryEntry {
    path: PathBuf,
    head: Option<String>,
    detached: bool,
}

fn discover_repository_root(workspace_root: &Path) -> WorktreeResult<PathBuf> {
    let output = run_git(
        workspace_root,
        &[
            OsString::from("rev-parse"),
            OsString::from("--show-toplevel"),
        ],
        workspace_root,
        None,
    )?;
    if !output.success {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    let text = std::str::from_utf8(&output.stdout)
        .map_err(|_| error("PARSE_FAILED", "Git repository metadata is invalid."))?
        .trim();
    if text.is_empty() {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    let root = PathBuf::from(text)
        .canonicalize()
        .map_err(|_| error("NOT_REPOSITORY", "Workspace is not a Git repository."))?;
    if !root.is_dir() {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    Ok(root)
}

fn parse_registry(bytes: &[u8]) -> WorktreeResult<Vec<RegistryEntry>> {
    let mut entries = Vec::new();
    let mut current: Option<RegistryEntry> = None;
    for field in bytes.split(|byte| *byte == 0) {
        if field.is_empty() {
            if let Some(entry) = current.take() {
                if entry.path.as_os_str().is_empty() {
                    return Err(parse_failed());
                }
                entries.push(entry);
            }
            continue;
        }
        let field = std::str::from_utf8(field).map_err(|_| parse_failed())?;
        if let Some(path) = field.strip_prefix("worktree ") {
            if let Some(entry) = current.take() {
                if entry.path.as_os_str().is_empty() {
                    return Err(parse_failed());
                }
                entries.push(entry);
            }
            current = Some(RegistryEntry {
                path: PathBuf::from(path),
                ..RegistryEntry::default()
            });
            continue;
        }
        let entry = current.as_mut().ok_or_else(parse_failed)?;
        if let Some(head) = field.strip_prefix("HEAD ") {
            entry.head = Some(head.to_owned());
        } else if field == "detached" {
            entry.detached = true;
        } else if field == "bare"
            || field.starts_with("branch ")
            || field.starts_with("locked")
            || field.starts_with("prunable")
        {
            // Valid Git porcelain metadata that is irrelevant to this first increment.
        } else {
            return Err(parse_failed());
        }
    }
    if let Some(entry) = current {
        if entry.path.as_os_str().is_empty() {
            return Err(parse_failed());
        }
        entries.push(entry);
    }
    Ok(entries)
}

fn canonical_directory(path: &Path, message: &'static str) -> WorktreeResult<PathBuf> {
    for ancestor in path
        .ancestors()
        .filter(|value| !value.as_os_str().is_empty())
    {
        let metadata = fs::symlink_metadata(ancestor).map_err(|_| boundary_error())?;
        if is_link_or_reparse(&metadata) {
            return Err(boundary_error());
        }
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| error("BOUNDARY_VIOLATION", message))?;
    if is_link_or_reparse(&metadata) {
        return Err(boundary_error());
    }
    let path = path
        .canonicalize()
        .map_err(|_| error("BOUNDARY_VIOLATION", message))?;
    if !path.is_dir() {
        return Err(error("BOUNDARY_VIOLATION", message));
    }
    Ok(path)
}

/// SPEC-A1 v4 §4.2 (C4): on unix the managed roots are created 0700, and an
/// existing one must be owned by the effective uid with no group/other write
/// bit. Other platforms keep their pre-C4 behavior unchanged.
fn ensure_owned_directory(path: &Path) -> WorktreeResult<()> {
    if path.exists() || path.is_symlink() {
        let metadata = fs::symlink_metadata(path).map_err(|_| io_failure())?;
        if is_link_or_reparse(&metadata) || !metadata.is_dir() {
            return Err(boundary_error());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o022 != 0 {
                return Err(boundary_error());
            }
        }
    } else {
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            use std::os::unix::fs::PermissionsExt;
            fs::DirBuilder::new()
                .mode(0o700)
                .create(path)
                .map_err(|_| io_failure())?;
            // A1 C2-ad (NB4): exactly 0700 whatever the umask. Only directories
            // the harness creates here are set; an existing root is never
            // tightened (it is only checked above).
            fs::set_permissions(path, fs::Permissions::from_mode(0o700))
                .map_err(|_| io_failure())?;
        }
        #[cfg(not(unix))]
        fs::create_dir(path).map_err(|_| io_failure())?;
    }
    Ok(())
}

fn is_link_or_reparse(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
        if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return true;
        }
    }
    metadata.file_type().is_symlink()
}

fn cleanup_empty_directory(path: &Path) {
    if path.is_dir()
        && fs::read_dir(path)
            .ok()
            .is_some_and(|mut entries| entries.next().is_none())
    {
        let _ = fs::remove_dir(path);
    }
}

fn valid_id(value: &str) -> bool {
    value.len() == OPAQUE_ID_LEN
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_head(value: &str) -> bool {
    !value.is_empty() && value.len() <= 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn boundary_error() -> WorktreeError {
    error(
        "BOUNDARY_VIOLATION",
        "Managed worktree boundary validation failed.",
    )
}

fn parse_failed() -> WorktreeError {
    error("PARSE_FAILED", "Git worktree metadata is invalid.")
}

fn git_failed() -> WorktreeError {
    error("GIT_FAILED", "Git worktree operation failed.")
}

fn io_failure() -> WorktreeError {
    error("IO_FAILED", "Managed worktree I/O failed.")
}

fn error(code: &'static str, message: &'static str) -> WorktreeError {
    WorktreeError::new(code, message)
}

#[cfg(test)]
#[path = "worktree_tests.rs"]
mod tests;

#[path = "worktree_snapshot.rs"]
mod snapshot;
pub(crate) use snapshot::SnapshotTarget;

#[path = "worktree_native.rs"]
mod native;

#[path = "worktree_legacy.rs"]
mod legacy;
#[cfg(all(test, unix))]
pub(crate) use legacy::LegacyState;
pub(crate) use legacy::{legacy_digest, LegacyCandidate, LegacyJournal, LegacyOutcome};

#[path = "worktree_reservations.rs"]
mod reservations;
pub(crate) use reservations::SlotReservation;
