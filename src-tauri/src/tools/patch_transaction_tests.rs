use super::*;
use std::{collections::BTreeMap, fs, path::Path};

fn workspace() -> (tempfile::TempDir, Workspace) {
    let root = tempfile::tempdir().expect("workspace");
    let workspace = Workspace::new(root.path().to_path_buf()).expect("workspace");
    (root, workspace)
}

fn staged(entries: &[(&str, Option<&[u8]>)]) -> BTreeMap<String, Option<Vec<u8>>> {
    entries
        .iter()
        .map(|(path, bytes)| ((*path).to_owned(), bytes.map(|value| value.to_vec())))
        .collect()
}

fn stage_files(root: &Path) -> Vec<PathBuf> {
    let mut pending = vec![root.to_path_buf()];
    let mut found = Vec::new();
    while let Some(directory) = pending.pop() {
        let Ok(entries) = fs::read_dir(directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                pending.push(path);
            } else if entry
                .file_name()
                .to_string_lossy()
                .contains(".harness-stage-")
            {
                found.push(path);
            }
        }
    }
    found
}

#[test]
fn commit_order_is_stable_workspace_relative_path_order() {
    let (root, workspace) = workspace();
    fs::write(root.path().join("z.txt"), b"old-z").unwrap();
    fs::write(root.path().join("a.txt"), b"old-a").unwrap();
    fs::write(root.path().join("m.txt"), b"old-m").unwrap();
    let staged = staged(&[
        ("z.txt", Some(b"new-z")),
        ("a.txt", Some(b"new-a")),
        ("m.txt", Some(b"new-m")),
    ]);
    let mut observed = Vec::new();
    commit_staged_bytes_with_hook(&workspace, &staged, |_, path, _| {
        observed.push(path.file_name().unwrap().to_string_lossy().into_owned());
        Ok(())
    })
    .unwrap();
    assert_eq!(observed, ["a.txt", "m.txt", "z.txt"]);
    assert!(stage_files(root.path()).is_empty());
}

#[test]
fn partial_add_update_delete_failure_restores_the_snapshot() {
    let (root, workspace) = workspace();
    fs::write(root.path().join("a-update.txt"), b"old-a").unwrap();
    fs::write(root.path().join("c-delete.txt"), b"old-c").unwrap();
    let staged = staged(&[
        ("c-delete.txt", None),
        ("b-created/nested.txt", Some(b"new-b")),
        ("a-update.txt", Some(b"new-a")),
    ]);
    let error = commit_staged_bytes_with_hook(&workspace, &staged, |index, path, _| {
        if index == 2 {
            fs::remove_file(path)?;
            return Err(io::Error::other("injected third commit failure"));
        }
        Ok(())
    })
    .unwrap_err();

    assert_eq!(error.to_error_value()["code"], "PATCH_FAILED");
    assert_eq!(
        fs::read(root.path().join("a-update.txt")).unwrap(),
        b"old-a"
    );
    assert_eq!(
        fs::read(root.path().join("c-delete.txt")).unwrap(),
        b"old-c"
    );
    assert!(!root.path().join("b-created/nested.txt").exists());
    assert!(!root.path().join("b-created").exists());
    assert!(stage_files(root.path()).is_empty());
}

#[test]
fn rollback_removes_only_transaction_created_empty_directories() {
    let (root, workspace) = workspace();
    fs::create_dir(root.path().join("existing")).unwrap();
    let staged = staged(&[("existing/new/deep/file.txt", Some(b"new"))]);
    let _ = commit_staged_bytes_with_hook(&workspace, &staged, |_, _, _| {
        Err(io::Error::other("injected failure"))
    })
    .unwrap_err();

    assert!(root.path().join("existing").is_dir());
    assert!(!root.path().join("existing/new").exists());
    assert!(stage_files(root.path()).is_empty());
}

#[test]
fn successful_update_keeps_existing_permissions_and_cleans_temps() {
    let (root, workspace) = workspace();
    let path = root.path().join("script.txt");
    fs::write(&path, b"old").unwrap();
    let readonly = fs::metadata(&path).unwrap().permissions().readonly();
    commit_staged_bytes(&workspace, &staged(&[("script.txt", Some(b"new"))])).unwrap();

    assert_eq!(fs::read(&path).unwrap(), b"new");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().readonly(),
        readonly
    );
    assert!(stage_files(root.path()).is_empty());
}

#[cfg(unix)]
#[test]
fn unix_mode_is_preserved_on_success_and_failure_rollback() {
    use std::os::unix::fs::PermissionsExt;

    let (root, workspace) = workspace();
    let path = root.path().join("tool.sh");
    fs::write(&path, b"old").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o751)).unwrap();

    commit_staged_bytes(&workspace, &staged(&[("tool.sh", Some(b"first"))])).unwrap();
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o751
    );

    let staged = staged(&[("tool.sh", Some(b"second")), ("z-new.txt", Some(b"new"))]);
    let _ = commit_staged_bytes_with_hook(&workspace, &staged, |index, _, _| {
        if index == 1 {
            return Err(io::Error::other("injected rollback"));
        }
        Ok(())
    })
    .unwrap_err();
    assert_eq!(fs::read(&path).unwrap(), b"first");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o751
    );
    assert!(!root.path().join("z-new.txt").exists());
    assert!(stage_files(root.path()).is_empty());
}

#[cfg(unix)]
#[test]
fn readonly_unix_mode_is_restored_after_later_commit_failure() {
    use std::os::unix::fs::PermissionsExt;

    let (root, workspace) = workspace();
    let path = root.path().join("a-readonly.txt");
    fs::write(&path, b"old").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();

    let staged = staged(&[
        ("a-readonly.txt", Some(b"new")),
        ("z-new.txt", Some(b"new")),
    ]);
    let _ = commit_staged_bytes_with_hook(&workspace, &staged, |index, _, _| {
        if index == 1 {
            return Err(io::Error::other("injected rollback"));
        }
        Ok(())
    })
    .unwrap_err();

    assert_eq!(fs::read(&path).unwrap(), b"old");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o444
    );
    assert!(!root.path().join("z-new.txt").exists());
    assert!(stage_files(root.path()).is_empty());
}
