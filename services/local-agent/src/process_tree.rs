use std::io;
use tokio::process::{Child, Command};

#[cfg(unix)]
pub(crate) struct ProcessTree(Option<libc::pid_t>);

#[cfg(unix)]
impl ProcessTree {
    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        let Some(pgid) = self.0.take() else {
            return Ok(());
        };
        let result = unsafe { libc::kill(-pgid, libc::SIGKILL) };
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ESRCH) {
            Ok(())
        } else {
            Err(error)
        }
    }

    pub(crate) fn finish(&mut self) -> io::Result<()> {
        // The leader may already be reaped while descendants are still alive.
        self.terminate()
    }
}

#[cfg(unix)]
impl Drop for ProcessTree {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
}

#[cfg(unix)]
pub(crate) async fn spawn(command: &mut Command) -> io::Result<(Child, ProcessTree)> {
    use std::os::unix::process::CommandExt;

    command.kill_on_drop(true);
    command.as_std_mut().process_group(0);
    let child = command.spawn()?;
    let pid = child
        .id()
        .ok_or_else(|| io::Error::other("spawned child has no process id"))?;
    let pgid = libc::pid_t::try_from(pid)
        .map_err(|_| io::Error::other("process id is outside platform range"))?;
    Ok((child, ProcessTree(Some(pgid))))
}

#[cfg(windows)]
mod windows_impl {
    use super::*;
    use std::{
        mem::size_of,
        os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
    };
    use windows::{
        core::PCWSTR,
        Win32::{
            Foundation::{HANDLE, ERROR_NO_MORE_FILES},
            System::{
                Diagnostics::ToolHelp::{
                    CreateToolhelp32Snapshot, Thread32First, Thread32Next, THREADENTRY32,
                    TH32CS_SNAPTHREAD,
                },
                JobObjects::{
                    AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
                    TerminateJobObject, JobObjectExtendedLimitInformation,
                    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                },
                Threading::{
                    GetProcessIdOfThread, OpenThread, ResumeThread,
                    THREAD_QUERY_LIMITED_INFORMATION, THREAD_SUSPEND_RESUME,
                },
            },
        },
    };

    pub(crate) struct ProcessTree(Option<OwnedHandle>);

    fn winerr(error: windows::core::Error) -> io::Error {
        io::Error::other(error.to_string())
    }

    fn handle(owned: &OwnedHandle) -> HANDLE {
        HANDLE(owned.as_raw_handle())
    }

    impl ProcessTree {
        fn new() -> io::Result<Self> {
            let raw = unsafe { CreateJobObjectW(None, PCWSTR::null()) }.map_err(winerr)?;
            let owned = unsafe { OwnedHandle::from_raw_handle(raw.0) };
            let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            unsafe {
                SetInformationJobObject(
                    handle(&owned),
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as *const _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                )
            }
            .map_err(winerr)?;
            Ok(Self(Some(owned)))
        }

        pub(crate) fn terminate(&mut self) -> io::Result<()> {
            if let Some(owned) = self.0.take() {
                unsafe { TerminateJobObject(handle(&owned), 1) }.map_err(winerr)?;
            }
            Ok(())
        }

        pub(crate) fn finish(&mut self) -> io::Result<()> {
            // KILL_ON_JOB_CLOSE tears down any remaining descendants when the
            // direct child has already exited normally.
            self.0.take();
            Ok(())
        }

        pub(crate) fn disarm(&mut self) {
            self.0 = None;
        }
    }

    impl Drop for ProcessTree {
        fn drop(&mut self) {
            let _ = self.terminate();
        }
    }

    pub(crate) async fn spawn(command: &mut Command) -> io::Result<(Child, ProcessTree)> {
        let job = ProcessTree::new()?;
        command.kill_on_drop(true);
        command.creation_flags(0x0800_0204); // NO_WINDOW | NEW_PROCESS_GROUP | SUSPENDED
        let mut child = command.spawn()?;

        let attached = (|| {
            let raw = child
                .raw_handle()
                .ok_or_else(|| io::Error::other("spawned child has no process handle"))?;
            let process_id = child
                .id()
                .ok_or_else(|| io::Error::other("spawned child has no process id"))?;
            unsafe {
                AssignProcessToJobObject(
                    handle(job.0.as_ref().expect("new job must own a handle")),
                    HANDLE(raw),
                )
            }
            .map_err(winerr)?;
            resume_primary_thread(process_id)
        })();

        if let Err(error) = attached {
            let _ = child.kill().await;
            return Err(error);
        }

        Ok((child, job))
    }

    fn resume_primary_thread(process_id: u32) -> io::Result<()> {
        let raw =
            unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) }.map_err(winerr)?;
        let snapshot = unsafe { OwnedHandle::from_raw_handle(raw.0) };
        let mut entry = THREADENTRY32 {
            dwSize: size_of::<THREADENTRY32>() as u32,
            ..Default::default()
        };
        unsafe { Thread32First(handle(&snapshot), &mut entry) }.map_err(winerr)?;

        loop {
            if entry.th32OwnerProcessID == process_id {
                let raw = unsafe {
                    OpenThread(
                        THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION,
                        false,
                        entry.th32ThreadID,
                    )
                }
                .map_err(winerr)?;
                let thread = unsafe { OwnedHandle::from_raw_handle(raw.0) };
                let actual_owner = unsafe { GetProcessIdOfThread(handle(&thread)) };
                if actual_owner == 0 {
                    return Err(io::Error::last_os_error());
                }
                if actual_owner != process_id {
                    return Err(io::Error::other(
                        "thread ownership changed during suspended child startup",
                    ));
                }
                let previous_suspend_count = unsafe { ResumeThread(handle(&thread)) };
                match previous_suspend_count {
                    0 => {}
                    1 => return Ok(()),
                    u32::MAX => return Err(io::Error::last_os_error()),
                    count => {
                        return Err(io::Error::other(format!(
                            "unexpected suspend count {count}; refusing unconfirmed child startup"
                        )))
                    }
                }
            }

            if let Err(error) = unsafe { Thread32Next(handle(&snapshot), &mut entry) } {
                if error.code()
                    == windows::core::HRESULT::from_win32(ERROR_NO_MORE_FILES.0)
                {
                    break;
                }
                return Err(winerr(error));
            }
        }

        Err(io::Error::other(
            "suspended child primary thread not found; refusing unmanaged execution",
        ))
    }
}

#[cfg(windows)]
pub(crate) use windows_impl::{spawn, ProcessTree};
