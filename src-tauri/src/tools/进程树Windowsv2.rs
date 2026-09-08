use std::io;
use std::mem::size_of;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use tokio::process::{Child, Command};
use windows::core::PCWSTR;
use windows::Win32::Foundation::HANDLE;
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Thread32First, Thread32Next, THREADENTRY32, TH32CS_SNAPTHREAD,
};
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject, TerminateJobObject,
    JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows::Win32::System::Threading::{OpenThread, ResumeThread, THREAD_SUSPEND_RESUME};

pub(crate) struct ProcessTree(Option<OwnedHandle>);

fn winerr(error: windows::core::Error) -> io::Error { io::Error::other(error.to_string()) }
fn handle(owned: &OwnedHandle) -> HANDLE { HANDLE(owned.as_raw_handle()) }

impl ProcessTree {
    fn new() -> io::Result<Self> {
        // API success transfers a unique, non-inherited kernel handle to us.
        let raw = unsafe { CreateJobObjectW(None, PCWSTR::null()) }.map_err(winerr)?;
        let owned = unsafe { OwnedHandle::from_raw_handle(raw.0) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        unsafe { SetInformationJobObject(handle(&owned), JobObjectExtendedLimitInformation,
            &limits as *const _ as *const _, size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32) }
            .map_err(winerr)?;
        Ok(Self(Some(owned)))
    }

    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        if let Some(owned) = self.0.take() {
            // Closing the last job handle also enforces kill-on-close on failure.
            unsafe { TerminateJobObject(handle(&owned), 1) }.map_err(winerr)?;
        }
        Ok(())
    }
}

impl Drop for ProcessTree {
    fn drop(&mut self) { let _ = self.terminate(); }
}

pub(super) async fn spawn(command: &mut Command) -> io::Result<(Child, ProcessTree)> {
    let job = ProcessTree::new()?;
    // Preserve existing console flags and keep the child suspended until assigned.
    // No command byte can execute before the descendant ownership boundary exists.
    command.creation_flags(0x0800_0204); // NO_WINDOW | NEW_PROCESS_GROUP | SUSPENDED
    let mut child = command.spawn()?;
    let attached = (|| {
        let raw = child.raw_handle().ok_or_else(|| io::Error::other("Missing child handle"))?;
        let id = child.id().ok_or_else(|| io::Error::other("Missing child id"))?;
        unsafe { AssignProcessToJobObject(handle(job.0.as_ref().expect("new job")), HANDLE(raw)) }.map_err(winerr)?;
        resume_primary_thread(id)
    })();
    if let Err(err) = attached {
        let _ = child.kill().await;
        return Err(err);
    }
    Ok((child, job))
}

fn resume_primary_thread(process_id: u32) -> io::Result<()> {
    let raw = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) }.map_err(winerr)?;
    let snapshot = unsafe { OwnedHandle::from_raw_handle(raw.0) };
    let mut entry = THREADENTRY32 { dwSize: size_of::<THREADENTRY32>() as u32, ..Default::default() };
    unsafe { Thread32First(handle(&snapshot), &mut entry) }.map_err(winerr)?;
    loop {
        if entry.th32OwnerProcessID == process_id {
            let raw = unsafe { OpenThread(THREAD_SUSPEND_RESUME, false, entry.th32ThreadID) }.map_err(winerr)?;
            let thread = unsafe { OwnedHandle::from_raw_handle(raw.0) };
            if unsafe { ResumeThread(handle(&thread)) } == u32::MAX { return Err(io::Error::last_os_error()); }
            return Ok(());
        }
        if unsafe { Thread32Next(handle(&snapshot), &mut entry) }.is_err() { break; }
    }
    Err(io::Error::other("Suspended child primary thread not found; refusing unmanaged execution"))
}
