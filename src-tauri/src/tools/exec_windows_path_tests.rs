//! Lexical path contracts; these tests do not require or claim SMB access.
use super::{command_for_program, platform_command_path, windows_batch_command_line, windows_command_path};
use std::path::{Path, PathBuf};

#[test]
fn extended_unc_path_preserves_network_root() {
    for (input, expected) in [
        (r"\\?\UNC\server\share\repo", r"\\server\share\repo"),
        (r"\\?\UNC\server\share\中文 [workspace]\run.ps1", r"\\server\share\中文 [workspace]\run.ps1"),
        (r"\\?\uNc\server\share\repo", r"\\server\share\repo"),
    ] {
        assert_eq!(windows_command_path(input), expected, "input={input}");
    }
}

#[test]
fn extended_drive_path_keeps_existing_runner_compatibility() {
    for (input, expected) in [
        (r"\\?\C:\workspace\run.cmd", r"C:\workspace\run.cmd"),
        (r"\\?\z:\中文 workspace\run.ps1", r"z:\中文 workspace\run.ps1"),
    ] {
        assert_eq!(windows_command_path(input), expected);
    }
}

#[test]
fn ordinary_and_relative_paths_are_unchanged() {
    for path in [r"\\server\share\repo", r"C:\workspace", "C:/workspace", "scripts/run.cmd", ""] {
        assert_eq!(windows_command_path(path), path);
    }
}

#[test]
fn device_namespaces_are_not_reinterpreted_as_relative_paths() {
    for path in [
        r"\\?\Volume{12345678-1234-1234-1234-123456789abc}\repo",
        r"\\?\GLOBALROOT\Device\HarddiskVolume1\repo",
        r"\\.\pipe\fixture",
        r"\\?\C:relative",
    ] {
        assert_eq!(windows_command_path(path), path);
    }
}

#[test]
fn unrecognized_unicode_prefixes_do_not_panic_or_change() {
    for path in [r"\\?\中文路径", r"\\?\a中文", r"\\?\", r"\\?\C:"] {
        assert_eq!(windows_command_path(path), path);
    }
}

#[test]
fn cwd_and_script_wrappers_use_the_same_unc_conversion() {
    let input = r"\\?\UNC\server\share\中文 workspace\run.ps1";
    let expected = r"\\server\share\中文 workspace\run.ps1";
    assert_eq!(platform_command_path(Path::new(input)), PathBuf::from(expected));
    let script = command_for_program(input, &[]);
    assert!(script.as_std().get_args().any(|arg| arg == expected));
    assert_eq!(
        windows_batch_command_line(r"\\?\UNC\server\share\run & tooling.cmd", &["argument & value".into()]),
        r#"call "\\server\share\run & tooling.cmd" "argument & value""#,
    );
}
