use super::*;
#[cfg(target_os = "linux")]
use coding_tools_local_agent::{
    Command, ExecDecision, ExecPolicy, HostExecutable, PrefixRule, TokenPattern,
};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};
pub(super) fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub(super) struct Artifact {
    path: PathBuf,
    named: PathBuf,
    file: File,
    pub digest: String,
}
pub(super) struct Script {
    root: File,
    relative: PathBuf,
    pub digest: String,
    pub bytes: Vec<u8>,
}
#[cfg(target_os = "linux")]
fn read_script(root: &File, relative: &Path) -> Result<Vec<u8>, &'static str> {
    use std::os::{
        fd::{AsRawFd, FromRawFd},
        unix::{ffi::OsStrExt, fs::MetadataExt},
    };
    #[repr(C)]
    struct OpenHow {
        flags: u64,
        mode: u64,
        resolve: u64,
    }
    let path = std::ffi::CString::new(relative.as_os_str().as_bytes())
        .map_err(|_| "HOOK_SCRIPT_REJECTED")?;
    let how = OpenHow {
        flags: (libc::O_RDONLY | libc::O_CLOEXEC) as u64,
        mode: 0,
        resolve: 0x08 | 0x04 | 0x02,
    };
    // Pinned root, relative traversal only, no symlinks/magiclinks anywhere in
    // the path. Unlike canonicalize+open this cannot race into an outside file.
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            root.as_raw_fd(),
            path.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    };
    if fd < 0 {
        return Err("HOOK_ARTIFACT_CHANGED");
    }
    let file = unsafe { File::from_raw_fd(fd as i32) };
    let metadata = file.metadata().map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
    if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() > 65536 {
        return Err("HOOK_ARTIFACT_INVALID");
    }
    let mut bytes = Vec::new();
    file.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
    if bytes.len() > 65536 {
        return Err("HOOK_ARTIFACT_INVALID");
    }
    Ok(bytes)
}
#[cfg(not(target_os = "linux"))]
fn read_script(_root: &File, _relative: &Path) -> Result<Vec<u8>, &'static str> {
    Err("HOOK_SANDBOX_UNAVAILABLE")
}
#[cfg(unix)]
fn protected_file(file: &File) -> Result<(), &'static str> {
    use std::os::unix::fs::MetadataExt;
    let uid = unsafe { libc::geteuid() };
    let m = file.metadata().map_err(|_| "HOOK_EXECUTABLE_REJECTED")?;
    // The agent cannot mutate this inode, including via chmod. Directory/path
    // swaps are handled by the owned FD, not by assuming immutable ancestors.
    if uid == 0
        || m.uid() == uid
        || m.mode() & 0o022 != 0
        || !m.is_file()
        || m.nlink() != 1
        || m.len() > 16 * 1024 * 1024
    {
        return Err("HOOK_EXECUTABLE_REJECTED");
    }
    Ok(())
}
#[cfg(not(unix))]
fn protected_file(_file: &File) -> Result<(), &'static str> {
    Err("HOOK_SANDBOX_UNAVAILABLE")
}
fn pinned_bytes(file: &File) -> Result<Vec<u8>, &'static str> {
    let mut file = file.try_clone().map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
    file.seek(SeekFrom::Start(0))
        .map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
    let mut bytes = Vec::new();
    file.take(16 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("HOOK_ARTIFACT_INVALID");
    }
    Ok(bytes)
}
impl Artifact {
    #[cfg(target_os = "linux")]
    fn open(path: &Path, workspace: &Path) -> Result<Self, &'static str> {
        if !path.is_absolute() || path.starts_with(workspace) {
            return Err("HOOK_EXECUTABLE_REJECTED");
        }
        let canonical = std::fs::canonicalize(path).map_err(|_| "HOOK_EXECUTABLE_REJECTED")?;
        if canonical.starts_with(workspace) {
            return Err("HOOK_EXECUTABLE_REJECTED");
        }
        let mut options = std::fs::OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC);
        }
        let file = options
            .open(&canonical)
            .map_err(|_| "HOOK_EXECUTABLE_REJECTED")?;
        protected_file(&file)?;
        let bytes = pinned_bytes(&file)?;
        if !bytes.starts_with(b"\x7fELF") {
            return Err("HOOK_EXECUTABLE_REJECTED");
        }
        let result = Self {
            path: canonical,
            named: path.into(),
            file,
            digest: hash(&bytes),
        };
        result.recheck()?;
        Ok(result)
    }
    pub fn recheck(&self) -> Result<(), &'static str> {
        protected_file(&self.file)?;
        if std::fs::canonicalize(&self.named).map_err(|_| "HOOK_ARTIFACT_CHANGED")? != self.path {
            return Err("HOOK_ARTIFACT_CHANGED");
        }
        #[cfg(unix)]
        {
            let named = std::fs::metadata(&self.path).map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
            let pinned = self.file.metadata().map_err(|_| "HOOK_ARTIFACT_CHANGED")?;
            use std::os::unix::fs::MetadataExt;
            if named.dev() != pinned.dev() || named.ino() != pinned.ino() {
                return Err("HOOK_ARTIFACT_CHANGED");
            }
        }
        if hash(&pinned_bytes(&self.file)?) != self.digest {
            return Err("HOOK_ARTIFACT_CHANGED");
        }
        Ok(())
    }
    #[cfg(target_os = "linux")]
    fn invocation_path(&self) -> String {
        use std::os::fd::AsRawFd;
        // Owned until actual process/tree completion. LinuxSandbox adds only
        // this selected executable inode, never a /proc-wide permission. Its
        // pre_exec close_range(CLOEXEC) closes this FD only AFTER execve resolves
        // /proc/self/fd/N, so path replacement cannot select a different image.
        format!("/proc/self/fd/{}", self.file.as_raw_fd())
    }
}
impl Script {
    pub fn recheck(&self) -> Result<(), &'static str> {
        if hash(&read_script(&self.root, &self.relative)?) != self.digest {
            return Err("HOOK_ARTIFACT_CHANGED");
        }
        Ok(())
    }
}
#[cfg(target_os = "linux")]
pub(super) fn command_policy(
    ctx: &ToolContext,
    argv: &[String],
    timeout: u64,
) -> Result<(), &'static str> {
    let mut policy = ctx.policy.clone();
    policy.workspace_local_entries = false;
    // A stored approval never turns a prompt/forbidden command into Allow.
    let args = json!({"cmd":shell_words::join(argv),"timeout_ms":timeout,"confirm":false,"filesystem_scope":"workspace"});
    super::super::policy::validate_tool_arguments_for_workspace(
        "exec_command",
        &args,
        &policy,
        Some(&ctx.workspace),
    )
    .map_err(|_| "HOOK_POLICY_REJECTED")
}
#[cfg(target_os = "linux")]
pub(super) fn prepare(ctx: &ToolContext, spec: HookSpec) -> Result<RegisteredHook, &'static str> {
    if !cfg!(target_os = "linux") {
        return Err("HOOK_SANDBOX_UNAVAILABLE");
    }
    let executable = Artifact::open(Path::new(&spec.executable), ctx.workspace.root())?;
    let selected = Path::new(&spec.executable)
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("HOOK_EXECUTABLE_REJECTED")?;
    let actual = executable
        .path
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("HOOK_EXECUTABLE_REJECTED")?;
    if selected != actual
        && !(selected == "python3" && actual.starts_with("python3."))
        && !(selected == "sh" && matches!(actual, "dash" | "bash"))
    {
        return Err("HOOK_EXECUTABLE_REJECTED");
    }
    let cwd = ctx
        .workspace
        .resolve_existing(&spec.cwd)
        .map_err(|_| "HOOK_CWD_REJECTED")?
        .path;
    if !cwd.is_dir() {
        return Err("HOOK_CWD_REJECTED");
    }
    let mut argv = vec![spec.executable.clone()];
    let script = if let Some(path) = &spec.script {
        ctx.workspace
            .reject_unsafe_text(path)
            .map_err(|_| "HOOK_SCRIPT_REJECTED")?;
        let relative = PathBuf::from(path);
        let mut options = std::fs::OpenOptions::new();
        options.read(true);
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC);
        let root = options
            .open(ctx.workspace.root())
            .map_err(|_| "HOOK_SCRIPT_REJECTED")?;
        let bytes = read_script(&root, &relative)?;
        if std::str::from_utf8(&bytes).is_err() || bytes.contains(&0) {
            return Err("HOOK_SCRIPT_REJECTED");
        }
        let name = Path::new(&spec.executable)
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("HOOK_EXECUTABLE_REJECTED")?;
        if name.starts_with("python3") || name == "python" || name == "node" {
            argv.push("-".into());
        } else if matches!(name, "sh" | "bash" | "dash") {
            argv.extend(["-s".into(), "--".into()]);
        } else {
            return Err("HOOK_INTERPRETER_UNSUPPORTED");
        }
        Some(Script {
            root,
            relative,
            digest: hash(&bytes),
            bytes,
        })
    } else {
        None
    };
    argv.extend(spec.args.clone());
    command_policy(ctx, &argv, spec.timeout_ms)?;
    let policy_argv = argv.clone();
    argv[0] = executable.invocation_path();
    // Policy authority comes from the current native command allowlist, not
    // from accepting a Hook manifest. The separately checked immutable argv and
    // script digest only narrow what this locally approved registration runs.
    let command = Command::new(policy_argv.clone()).map_err(|_| "HOOK_POLICY_REJECTED")?;
    let rules = ctx
        .policy
        .allowed_commands
        .iter()
        .map(|name| PrefixRule::new(vec![TokenPattern::exact(name)?], ExecDecision::Allow))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "HOOK_POLICY_REJECTED")?;
    let host = HostExecutable::new(selected, [spec.executable.clone()])
        .map_err(|_| "HOOK_POLICY_REJECTED")?;
    let policy = ExecPolicy::new(rules, vec![host], true).map_err(|_| "HOOK_POLICY_REJECTED")?;
    if policy.evaluate(&command).decision != Some(ExecDecision::Allow) {
        return Err("HOOK_POLICY_REJECTED");
    }
    Ok(RegisteredHook {
        spec,
        executable,
        script,
        argv,
        policy_argv,
        cwd,
        policy,
    })
}

#[cfg(all(test, target_os = "linux"))]
mod pin_tests {
    use super::*;
    use coding_tools_local_agent::{ExecSpec, LinuxSandbox, ProcessManager};
    #[test]
    fn executable_path_swap_after_recheck_executes_only_original_pinned_inode() {
        let root = tempfile::tempdir().unwrap();
        let aliases = tempfile::tempdir().unwrap();
        let alias = aliases.path().join("python3");
        std::os::unix::fs::symlink("/usr/bin/python3", &alias).unwrap();
        let executable = Artifact::open(&alias, root.path()).unwrap();
        executable.recheck().unwrap();
        std::fs::remove_file(&alias).unwrap();
        std::os::unix::fs::symlink("/usr/bin/false", &alias).unwrap();
        assert!(executable.recheck().is_err());
        // Simulate a swap in the recheck→exec race: the actual launch path is the
        // held FD, and sandbox policy names only its selected executable inode.
        let spec = ExecSpec::new(
            vec![executable.invocation_path(), "--version".into()],
            root.path(),
        )
        .unwrap()
        .with_sandbox(LinuxSandbox::new(root.path()).unwrap().read_only());
        let outcome =
            tauri::async_runtime::block_on(ProcessManager::new(1).unwrap().run(spec)).unwrap();
        assert!(outcome.command_ok(), "{outcome:?}");
        assert!(String::from_utf8_lossy(&outcome.stdout).contains("Python"));
    }
    #[test]
    fn agent_owned_binary_is_rejected_even_when_made_read_only() {
        use std::os::unix::fs::PermissionsExt;
        let root = tempfile::tempdir().unwrap();
        let binaries = tempfile::tempdir().unwrap();
        let binary = binaries.path().join("copy");
        std::fs::copy("/usr/bin/true", &binary).unwrap();
        std::fs::set_permissions(&binary, std::fs::Permissions::from_mode(0o555)).unwrap();
        assert!(Artifact::open(&binary, root.path()).is_err());
    }
}

#[cfg(not(target_os = "linux"))]
pub(super) fn prepare(_ctx: &ToolContext, _spec: HookSpec) -> Result<RegisteredHook, &'static str> {
    Err("HOOK_SANDBOX_UNAVAILABLE")
}

#[cfg(all(test, target_os = "linux"))]
#[test]
fn sandboxed_pinned_shell_preserves_the_exact_native_approved_argv0() {
    use coding_tools_local_agent::{ExecSpec, LinuxSandbox, ProcessManager};
    let root = tempfile::tempdir().unwrap();
    let executable = Artifact::open(Path::new("/usr/bin/sh"), root.path()).unwrap();
    let spec = ExecSpec::new(
        vec![
            executable.invocation_path(),
            "-c".into(),
            "printf '%s' \"$0\"".into(),
        ],
        root.path(),
    )
    .unwrap()
    .with_argv0("/usr/bin/sh".into())
    .unwrap()
    .with_sandbox(LinuxSandbox::new(root.path()).unwrap().read_only());
    let result = tauri::async_runtime::block_on(ProcessManager::new(1).unwrap().run(spec)).unwrap();
    assert!(result.command_ok());
    assert_eq!(result.stdout, b"/usr/bin/sh");
}
