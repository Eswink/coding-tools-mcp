use super::*;

#[test]
fn unicode_space_and_bracket_paths_preserve_private_config() {
    let root = tempfile::tempdir().unwrap();
    let parent = root.path().join("中文 空格 [配置]");
    let path = parent.join("frpc.toml");
    for index in 0..16 {
        let value = format!("runtime-canary-{index}");
        write_private_config(&path, &value).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), value);
        assert_eq!(fs::read_dir(&parent).unwrap().count(), 1);
        #[cfg(windows)]
        private_windows::verify_current_user(&fs::File::open(&path).unwrap()).unwrap();
    }
}

#[test]
fn parallel_private_config_creation_does_not_share_acl_state() {
    let root = tempfile::tempdir().unwrap();
    std::thread::scope(|scope| {
        let mut workers = Vec::new();
        for index in 0..16 {
            let path = root.path().join(format!("配置 {index}.toml"));
            workers.push(scope.spawn(move || {
                write_private_config(&path, "parallel-canary").unwrap();
                assert_eq!(fs::read_to_string(&path).unwrap(), "parallel-canary");
                #[cfg(windows)]
                private_windows::verify_current_user(&fs::File::open(&path).unwrap()).unwrap();
            }));
        }
        for worker in workers { worker.join().unwrap(); }
    });
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), 16);
}

#[test]
fn exclusive_creation_never_truncates_existing_file() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("already-there.toml");
    fs::write(&path, "original").unwrap();
    assert!(create_private_file(&path).is_err());
    assert_eq!(fs::read_to_string(&path).unwrap(), "original");
}

#[cfg(unix)]
#[test]
fn symlink_destination_is_rejected_without_modifying_target() {
    use std::os::unix::fs::symlink;
    let root = tempfile::tempdir().unwrap();
    let target = root.path().join("target.toml");
    let path = root.path().join("link.toml");
    fs::write(&target, "original").unwrap();
    symlink(&target, &path).unwrap();
    assert!(write_private_config(&path, "not-written").is_err());
    assert_eq!(fs::read_to_string(&target).unwrap(), "original");
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
}

#[cfg(windows)]
#[test]
fn native_creation_is_private_before_any_content_is_written() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("empty.toml");
    let file = create_private_file(&path).unwrap();
    assert_eq!(file.metadata().unwrap().len(), 0);
    private_windows::verify_current_user(&file).unwrap();
}
