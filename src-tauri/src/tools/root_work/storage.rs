use super::*;
pub(super) fn private_dir(path: &Path) -> Result<(), RootWorkError> {
    for ancestor in path.ancestors() {
        if let Ok(meta) = std::fs::symlink_metadata(ancestor) {
            if meta.file_type().is_symlink() {
                return Err(RootWorkError);
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if meta.file_attributes() & 0x400 != 0 {
                    return Err(RootWorkError);
                }
            }
        }
    }
    let mut builder = std::fs::DirBuilder::new();
    builder.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder.create(path).map_err(|_| RootWorkError)
}
pub(super) fn regular(path: &Path) -> Result<(), RootWorkError> {
    let meta = std::fs::symlink_metadata(path).map_err(|_| RootWorkError)?;
    if !meta.is_file() || meta.file_type().is_symlink() {
        return Err(RootWorkError);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if meta.file_attributes() & 0x400 != 0 {
            return Err(RootWorkError);
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if meta.nlink() != 1 {
            return Err(RootWorkError);
        }
    }
    Ok(())
}
pub(super) fn overlaps(a: &Path, b: &Path) -> bool {
    a.starts_with(b) || b.starts_with(a)
}
pub(super) fn physical_overlap(a: &RootIdentity, b: &RootIdentity) -> bool {
    a.ancestors.contains(&b.key) || b.ancestors.contains(&a.key)
}
pub(super) fn live_conflict(
    registry: &HashMap<PathBuf, Weak<RootWorkTracker>>,
    root: &Path,
    anchor: &RootIdentity,
) -> Result<(), RootWorkError> {
    for (other, owner) in registry {
        if let Some(owner) = owner.upgrade() {
            if !overlaps(other, root) && !physical_overlap(&owner.anchor, anchor) {
                continue;
            }
            owner.anchor.verify(&owner.root)?;
            let state = owner.state.lock().map_err(|_| RootWorkError)?;
            if state.poisoned
                || state.exclusive.is_some()
                || state.document.phase == Phase::Restore
                || state.drain.status().unconfirmed
            {
                return Err(RootWorkError);
            }
        }
    }
    Ok(())
}
pub(super) fn persisted_conflict(
    parent: &Path,
    root: &Path,
    anchor: &RootIdentity,
    registry: &HashMap<PathBuf, Weak<RootWorkTracker>>,
) -> Result<(), RootWorkError> {
    #[cfg(feature = "native-state-timing")]
    let mut timing = crate::data::native_timing::Span::new("persisted_scan");
    let known: std::collections::HashSet<String> = registry
        .iter()
        .filter(|(_, value)| value.strong_count() > 0)
        .map(|(path, _)| path)
        .map(|p| format!("{:x}", Sha256::digest(p.to_string_lossy().as_bytes())))
        .collect();
    let reader = crate::data::AuthDocumentReader::default();
    // Collect first so reclaim can unlink entries without perturbing the walk.
    // The 512 cap applies to entries that remain after eligible Clean leftovers
    // are reclaimed, not to the raw pre-reclaim directory count.
    let entries = std::fs::read_dir(parent)
        .map_err(|_| RootWorkError)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| RootWorkError)?;
    let mut remaining = 0usize;
    for entry in entries {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.len() != 64 || !name.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(RootWorkError);
        }
        if known.contains(&name) {
            remaining = remaining.checked_add(1).ok_or(RootWorkError)?;
            if remaining >= 512 {
                return Err(RootWorkError);
            }
            continue;
        }
        let path = entry.path();
        regular(&path.join("auth.json"))?;
        regular(&path.join("auth.lock"))?;
        #[cfg(feature = "native-state-timing")]
        timing.ledger();
        let disk = AuthDocument::open(&path).map_err(|_| RootWorkError)?;
        let doc: Document = reader
            .load(&disk)
            .map_err(|_| RootWorkError)?
            .ok_or(RootWorkError)?;
        if doc.version != 1
            || doc.epoch == 0
            || !doc.root.is_absolute()
            || doc.binding != name
            || format!(
                "{:x}",
                Sha256::digest(doc.root.to_string_lossy().as_bytes())
            ) != name
        {
            return Err(RootWorkError);
        }
        if doc.ancestors.len() > 128 || doc.ancestors.first() != Some(&doc.identity) {
            return Err(RootWorkError);
        }
        // A1 C39 (#217): inside the REGISTRY lock, after proving the namespace
        // is not live and while holding auth.lock, reclaim a Clean leftover
        // whose workspace root is gone or no longer matches its recorded
        // identity. Non-Clean, live, corrupted, or verification-failed
        // entries are never reclaimed; those stay fail-closed.
        if doc.phase == Phase::Clean && clean_leftover_reclaimable(&doc) {
            reclaim_clean_leftover(parent, &path, disk)?;
            continue;
        }
        if doc.phase != Phase::Clean
            && (overlaps(root, &doc.root)
                || anchor.ancestors.contains(&doc.identity)
                || doc.ancestors.contains(&anchor.key))
        {
            return Err(RootWorkError);
        }
        remaining = remaining.checked_add(1).ok_or(RootWorkError)?;
        if remaining >= 512 {
            return Err(RootWorkError);
        }
    }
    Ok(())
}

fn clean_leftover_reclaimable(doc: &Document) -> bool {
    match std::fs::symlink_metadata(&doc.root) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => true,
        Err(_) => false,
        Ok(meta) => {
            if !meta.is_dir() || meta.file_type().is_symlink() {
                return false;
            }
            let Ok(canonical) = doc.root.canonicalize() else {
                return false;
            };
            if canonical != doc.root {
                return false;
            }
            match super::identity::RootIdentity::open(&doc.root) {
                Ok(identity) => identity.key != doc.identity,
                Err(_) => false,
            }
        }
    }
}

fn reclaim_clean_leftover(
    parent: &Path,
    namespace: &Path,
    disk: AuthDocument,
) -> Result<(), RootWorkError> {
    let mut saw_json = false;
    let mut saw_lock = false;
    for entry in std::fs::read_dir(namespace).map_err(|_| RootWorkError)? {
        let name = entry.map_err(|_| RootWorkError)?.file_name();
        if name == "auth.json" {
            saw_json = true;
        } else if name == "auth.lock" {
            saw_lock = true;
        } else {
            return Err(RootWorkError);
        }
    }
    if !saw_json || !saw_lock {
        return Err(RootWorkError);
    }
    let auth_json = namespace.join("auth.json");
    let auth_lock = namespace.join("auth.lock");
    regular(&auth_json)?;
    regular(&auth_lock)?;
    std::fs::remove_file(&auth_json).map_err(|_| RootWorkError)?;
    std::fs::remove_file(&auth_lock).map_err(|_| RootWorkError)?;
    drop(disk);
    std::fs::remove_dir(namespace).map_err(|_| RootWorkError)?;
    #[cfg(unix)]
    std::fs::File::open(parent)
        .and_then(|f| f.sync_all())
        .map_err(|_| RootWorkError)?;
    #[cfg(not(unix))]
    let _ = parent;
    Ok(())
}

pub(crate) fn error_value(_: RootWorkError) -> Value {
    json!({"ok":false,"error":{"code":"NATIVE_ROOT_UNAVAILABLE","category":"availability","retryable":false,
        "message":"Native workspace work or recovery is not proven quiescent; no operation was started."}})
}

pub(super) fn managed_layout(root: &Path, store: &Path) -> bool {
    let Ok(relative) = root.strip_prefix(store) else {
        return false;
    };
    let parts: Vec<_> = relative
        .components()
        .map(|c| c.as_os_str().to_string_lossy())
        .collect();
    let id = |s: &str, n: usize| s.len() == n && s.bytes().all(|b| b.is_ascii_hexdigit());
    match parts.as_slice() {
        [kind, workspace, tree] => kind == "worktrees-v1" && id(workspace, 32) && id(tree, 32),
        [chat, key, kind, workspace, tree] => {
            chat == "chat-v1"
                && id(key, 64)
                && kind == "worktrees-v1"
                && id(workspace, 32)
                && id(tree, 32)
        }
        _ => false,
    }
}
