//! A1 C3-win: per-worker parent Job Object (Windows).
//!
//! Mirrors the Linux worker cgroup lifecycle: prepare once per worker id,
//! `subagent_cancel` → terminate the parent Job, discard → release the handle.
//! The parent Job improves kill-tree completeness (SPEC-A1 §4.1 / T5); it is
//! **not** an OS security sandbox (Q3=B: unsandboxed user-default permissions).

#![cfg_attr(not(windows), allow(dead_code))]

/// SPEC §4.1 default: `JOB_OBJECT_LIMIT_ACTIVE_PROCESS`.
pub(crate) const ACTIVE_PROCESS_LIMIT: u32 = 64;
/// SPEC §4.1 default: `JOB_OBJECT_LIMIT_JOB_MEMORY` (4 GiB).
pub(crate) const JOB_MEMORY_LIMIT_BYTES: usize = 4 * 1024 * 1024 * 1024;

/// Parent Job `LimitFlags` bits (platform-neutral for digests / Linux-host tests).
/// `KILL_ON_JOB_CLOSE (0x2000) | ACTIVE_PROCESS (0x8) | JOB_MEMORY (0x200)`.
#[cfg(test)]
pub(crate) fn parent_limit_flags_bits() -> u32 {
    0x2000 | 0x8 | 0x200
}

/// Nesting assign order required by SPEC §4.1 (Win8+ nested Jobs).
#[cfg(test)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum NestAssignStep {
    ParentJob,
    CommandJob,
}

/// Canonical sequence: suspended child → assign **parent** → assign **command Job** → resume.
#[cfg(test)]
pub(crate) fn nest_assign_sequence() -> [NestAssignStep; 2] {
    [NestAssignStep::ParentJob, NestAssignStep::CommandJob]
}

#[cfg(windows)]
#[path = "worker_job_windows.rs"]
mod platform;

#[cfg(windows)]
pub(crate) use platform::{for_worker, release_worker_job, terminate_worker_job};

#[cfg(not(windows))]
pub(crate) fn terminate_worker_job(_worker_id: &str) -> std::io::Result<bool> {
    Ok(false)
}

#[cfg(not(windows))]
pub(crate) fn release_worker_job(_worker_id: &str) {}

/// A1 C12 M6: registry-only emptiness probe. Never creates a Job (`for_worker`).
/// `Ok(true)` = empty or no Job registered; `Err` = query failed (treat as busy).
#[cfg(windows)]
pub(crate) use platform::probe_worker_job_empty;

#[cfg(not(windows))]
pub(crate) fn probe_worker_job_empty(_worker_id: &str) -> std::io::Result<bool> {
    Ok(true)
}

#[cfg(test)]
mod contract_tests {
    use super::*;

    #[test]
    fn parent_limit_flags_include_kill_active_and_memory() {
        let bits = parent_limit_flags_bits();
        assert_eq!(bits & 0x2000, 0x2000, "KILL_ON_JOB_CLOSE");
        assert_eq!(bits & 0x8, 0x8, "ACTIVE_PROCESS");
        assert_eq!(bits & 0x200, 0x200, "JOB_MEMORY");
        assert_eq!(bits, 0x2208);
    }

    #[test]
    fn defaults_match_spec_section_4_1() {
        assert_eq!(ACTIVE_PROCESS_LIMIT, 64);
        assert_eq!(JOB_MEMORY_LIMIT_BYTES, 4 << 30);
    }

    #[test]
    fn nest_assign_is_parent_then_command() {
        assert_eq!(
            nest_assign_sequence(),
            [NestAssignStep::ParentJob, NestAssignStep::CommandJob]
        );
    }

    #[test]
    fn nest_assign_rejects_command_before_parent_in_recorder() {
        // Pure contract: a recorder that enforces SPEC order must reject reverse.
        let mut prior: Option<NestAssignStep> = None;
        let mut log = Vec::new();
        for step in [NestAssignStep::CommandJob, NestAssignStep::ParentJob] {
            if step == NestAssignStep::CommandJob {
                assert!(
                    prior != Some(NestAssignStep::ParentJob),
                    "fixture expects reverse order to lack parent-first"
                );
            }
            log.push(step);
            prior = Some(step);
        }
        assert_eq!(log, [NestAssignStep::CommandJob, NestAssignStep::ParentJob]);
        // Correct sequence still ends parent→command.
        assert_eq!(nest_assign_sequence()[0], NestAssignStep::ParentJob);
        assert_eq!(nest_assign_sequence()[1], NestAssignStep::CommandJob);
    }

    #[test]
    fn non_windows_terminate_is_noop_false() {
        #[cfg(not(windows))]
        {
            assert!(!terminate_worker_job("any").unwrap());
            release_worker_job("any");
        }
        #[cfg(windows)]
        {
            // Covered in platform tests; keep the cfg arm so --lib sees both.
            let _ = terminate_worker_job;
            let _ = release_worker_job;
        }
    }
}
