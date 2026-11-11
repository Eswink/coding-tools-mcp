//! A1 C12: in-memory `core.longpaths=true` for the config-free object repo.
//!
//! Uses libgit2's `git_config_backend_from_values` (sys API, not GIT_EXTERN) plus
//! `git_config_add_backend` at APP level. Never reads user/global/system config and
//! never writes a config file. Direct `libgit2-sys` with `vendored` is required so
//! the non-exported `from_values` symbol links (system libgit2 builds with hidden
//! visibility). `LIBGIT2_NO_VENDOR` is not supported for this crate.

use super::worktree::WorktreeResult;
use super::worktree_boundary::failure;
use git2::{Binding, Config};
use libgit2_sys as raw;
use std::ffi::CString;
use std::os::raw::{c_char, c_int};
use std::ptr;

// Exact signature from libgit2 include/git2/sys/config.h (extern, not GIT_EXTERN).
extern "C" {
    fn git_config_backend_from_values(
        out: *mut *mut raw::git_config_backend,
        values: *const *const c_char,
        len: usize,
        opts: *mut std::ffi::c_void,
    ) -> c_int;
}

/// Build an empty [`Config`] with a single in-memory APP entry `core.longpaths=true`.
/// Fail-closed: any FFI failure becomes `GIT_FAILED` (never silent empty config).
pub(super) fn longpaths_config() -> WorktreeResult<Config> {
    let config = Config::new().map_err(|_| failure("GIT_FAILED"))?;
    let value = CString::new("core.longpaths=true").map_err(|_| failure("GIT_FAILED"))?;
    let mut values: [*const c_char; 1] = [value.as_ptr()];
    let mut backend: *mut raw::git_config_backend = ptr::null_mut();

    // SAFETY: `value` lives for the call; `opts` is NULL (libgit2 default in-memory
    // backend); `backend` is written only on success (rc==0).
    let rc = unsafe {
        git_config_backend_from_values(&mut backend, values.as_mut_ptr(), 1, ptr::null_mut())
    };
    if rc != 0 || backend.is_null() {
        return Err(failure("GIT_FAILED"));
    }

    // SAFETY: `config.raw()` is a live `git_config*`; level APP (7); repo NULL;
    // force=0. On success ownership of `backend` moves to `git_config` — do not free.
    // On failure we must free via the backend's `free` field.
    let add_rc = unsafe {
        raw::git_config_add_backend(
            config.raw(),
            backend,
            raw::GIT_CONFIG_LEVEL_APP,
            ptr::null(),
            0,
        )
    };
    if add_rc != 0 {
        // SAFETY: from_values succeeded so `backend` is valid and its `free` is set.
        unsafe {
            if let Some(free) = (*backend).free {
                free(backend);
            }
        }
        return Err(failure("GIT_FAILED"));
    }
    Ok(config)
}

#[cfg(test)]
mod tests {
    use super::*;
    use git2::ConfigLevel;

    #[test]
    fn longpaths_config_reads_back_true_with_exactly_one_entry() {
        let config = longpaths_config().expect("longpaths_config");
        assert_eq!(config.get_bool("core.longpaths").expect("get_bool"), true);
        let mut entries = config.entries(None).expect("entries");
        let mut count = 0usize;
        while let Some(entry) = entries.next() {
            let entry = entry.expect("entry");
            count += 1;
            assert_eq!(entry.name().expect("name"), "core.longpaths");
            assert_eq!(entry.value().expect("value"), "true");
            assert_eq!(entry.level(), ConfigLevel::App);
        }
        assert_eq!(count, 1, "must not pull user/global/system config");
    }

    /// A1 C12b nit 1: the only backend is libgit2's read-only in-memory one, so
    /// there is no writable (file) backend a set could land in.
    #[test]
    fn longpaths_config_has_no_writable_ondisk_backend() {
        let mut config = longpaths_config().unwrap();
        assert!(
            config.set_bool("core.longpaths", false).is_err(),
            "set must fail: no writable/on-disk backend"
        );
        assert!(config.set_str("user.name", "x").is_err());
        assert!(config.get_bool("core.longpaths").unwrap());
        assert!(config.get_entry("user.name").is_err());
    }
}
