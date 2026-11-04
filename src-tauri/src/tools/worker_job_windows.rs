//! Windows parent Job Object for one worker (SPEC-A1 §4.1).
use super::{ACTIVE_PROCESS_LIMIT, JOB_MEMORY_LIMIT_BYTES};
use std::collections::HashMap;
use std::io;
use std::mem::size_of;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::sync::{Arc, Mutex, OnceLock};
use windows::core::PCWSTR;
use windows::Win32::Foundation::HANDLE;
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectBasicAccountingInformation,
    JobObjectExtendedLimitInformation, QueryInformationJobObject, SetInformationJobObject,
    TerminateJobObject, JOBOBJECT_BASIC_ACCOUNTING_INFORMATION,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_ACTIVE_PROCESS,
    JOB_OBJECT_LIMIT_JOB_MEMORY, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

/// One parent Job per worker. Must **not** set `JobObjectBasicUIRestrictions`
/// (that breaks Win8+ nesting with the per-command Job).
pub(crate) struct WorkerParentJob(OwnedHandle);

fn winerr(error: windows::core::Error) -> io::Error {
    io::Error::other(error.to_string())
}

fn handle(owned: &OwnedHandle) -> HANDLE {
    HANDLE(owned.as_raw_handle())
}

impl WorkerParentJob {
    pub(crate) fn create() -> io::Result<Self> {
        // API success transfers a unique, non-inherited kernel handle to us.
        let raw = unsafe { CreateJobObjectW(None, PCWSTR::null()) }.map_err(winerr)?;
        let owned = unsafe { OwnedHandle::from_raw_handle(raw.0) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_JOB_MEMORY;
        limits.BasicLimitInformation.ActiveProcessLimit = ACTIVE_PROCESS_LIMIT;
        limits.JobMemoryLimit = JOB_MEMORY_LIMIT_BYTES;
        unsafe {
            SetInformationJobObject(
                handle(&owned),
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        }
        .map_err(winerr)?;
        Ok(Self(owned))
    }

    pub(crate) fn assign_process(&self, process: HANDLE) -> io::Result<()> {
        unsafe { AssignProcessToJobObject(handle(&self.0), process) }.map_err(winerr)
    }

    pub(crate) fn terminate(&self) -> io::Result<()> {
        unsafe { TerminateJobObject(handle(&self.0), 1) }.map_err(winerr)
    }

    /// One observation of this owned parent Job only.
    pub(crate) fn is_empty(&self) -> io::Result<bool> {
        let mut accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
        unsafe {
            QueryInformationJobObject(
                Some(handle(&self.0)),
                JobObjectBasicAccountingInformation,
                &mut accounting as *mut _ as *mut _,
                size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                None,
            )
        }
        .map_err(winerr)?;
        Ok(accounting.ActiveProcesses == 0)
    }

    #[cfg(test)]
    fn limit_flags_bits(&self) -> io::Result<u32> {
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        unsafe {
            QueryInformationJobObject(
                Some(handle(&self.0)),
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                None,
            )
        }
        .map_err(winerr)?;
        Ok(info.BasicLimitInformation.LimitFlags.0)
    }

    #[cfg(test)]
    fn active_process_limit(&self) -> io::Result<u32> {
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        unsafe {
            QueryInformationJobObject(
                Some(handle(&self.0)),
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                None,
            )
        }
        .map_err(winerr)?;
        Ok(info.BasicLimitInformation.ActiveProcessLimit)
    }

    #[cfg(test)]
    fn job_memory_limit(&self) -> io::Result<usize> {
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        unsafe {
            QueryInformationJobObject(
                Some(handle(&self.0)),
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                None,
            )
        }
        .map_err(winerr)?;
        Ok(info.JobMemoryLimit)
    }
}

impl Drop for WorkerParentJob {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
}

fn registry() -> &'static Mutex<HashMap<String, Arc<WorkerParentJob>>> {
    static REGISTRY: OnceLock<Mutex<HashMap<String, Arc<WorkerParentJob>>>> = OnceLock::new();
    REGISTRY.get_or_init(Default::default)
}

/// Prepare (once) the parent Job for `worker_id`. Concurrent first callers keep
/// whichever `Arc` was stored first (same pattern as Linux `for_worker` cgroup).
pub(crate) fn for_worker(worker_id: &str) -> io::Result<Arc<WorkerParentJob>> {
    if let Some(known) = registry()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(worker_id)
    {
        return Ok(known.clone());
    }
    let prepared = Arc::new(WorkerParentJob::create()?);
    Ok(registry()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .entry(worker_id.to_owned())
        .or_insert(prepared)
        .clone())
}

/// Cancel path: `TerminateJobObject(parent)` then one `is_empty` observation.
/// `Ok(false)` when this worker never prepared a parent Job.
pub(crate) fn terminate_worker_job(worker_id: &str) -> io::Result<bool> {
    let job = registry()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(worker_id)
        .cloned();
    match job {
        Some(job) => {
            job.terminate()?;
            // One-shot confirm (SPEC §4.1). Short-lived ActiveProcesses>0 is ok;
            // bookkeeping kills still run after cancel returns.
            let _ = job.is_empty()?;
            Ok(true)
        }
        None => Ok(false),
    }
}

/// Discard path: forget the worker's parent Job (Drop → Terminate + handle close /
/// `KILL_ON_JOB_CLOSE`).
pub(crate) fn release_worker_job(worker_id: &str) {
    let _ = registry()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(worker_id);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tools::worker_job::parent_limit_flags_bits;

    #[test]
    fn create_parent_job_is_empty_with_spec_limits() {
        let job = WorkerParentJob::create().expect("create parent job");
        assert!(job.is_empty().expect("query empty"));
        assert_eq!(job.limit_flags_bits().unwrap(), parent_limit_flags_bits());
        assert_eq!(job.active_process_limit().unwrap(), ACTIVE_PROCESS_LIMIT);
        assert_eq!(job.job_memory_limit().unwrap(), JOB_MEMORY_LIMIT_BYTES);
    }

    #[test]
    fn for_worker_reuses_same_arc_per_id_and_isolates_workers() {
        let suffix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let id_a = format!("c3win-a-{suffix}");
        let id_b = format!("c3win-b-{suffix}");
        let a1 = for_worker(&id_a).unwrap();
        let a2 = for_worker(&id_a).unwrap();
        let b1 = for_worker(&id_b).unwrap();
        assert!(Arc::ptr_eq(&a1, &a2), "same worker must share parent Job");
        assert!(
            !Arc::ptr_eq(&a1, &b1),
            "distinct workers must not share a parent Job"
        );
        release_worker_job(&id_a);
        release_worker_job(&id_b);
    }

    #[test]
    fn terminate_without_prepare_returns_false() {
        let id = format!(
            "c3win-never-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        assert!(!terminate_worker_job(&id).unwrap());
    }

    #[test]
    fn terminate_then_release_forgets_parent_job() {
        let id = format!(
            "c3win-term-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let _ = for_worker(&id).unwrap();
        assert!(terminate_worker_job(&id).unwrap());
        assert!(
            for_worker(&id).is_ok(),
            "terminate keeps registry entry for further is_empty / late assigns"
        );
        release_worker_job(&id);
        assert!(
            !terminate_worker_job(&id).unwrap(),
            "release must drop the registry entry"
        );
    }
}
