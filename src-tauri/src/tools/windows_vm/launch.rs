//! The creating thread owns all debug events and the independent process handle.
use super::host_io::{IoReport, Pipes};
use super::image::{self, Handle, ImageIdentity, RetainedImage};
use serde::Serialize;
use std::marker::PhantomData;
use std::path::PathBuf;
use std::rc::Rc;
use std::time::{Duration, Instant};
use windows::core::{PCWSTR, PWSTR};
use windows::Win32::Foundation::*;
use windows::Win32::System::Diagnostics::Debug::*;
use windows::Win32::System::Pipes::PeekNamedPipe;
use windows::Win32::System::Threading::*;

pub(super) struct LaunchSpec {
    pub application: PathBuf,
    pub cwd: PathBuf,
    pub session_root: PathBuf
}
#[derive(Clone, Debug, Default, Serialize)]
pub(super) struct LaunchReport {
    pub retained: Option<ImageIdentity>,
    pub observed: Option<ImageIdentity>,
    pub create_call_entered: bool,
    pub create_call_returned: bool,
    pub create_result_consistent: bool,
    pub child_created: bool,
    pub pid: u32,
    pub tid: u32,
    pub create_event: bool,
    pub image_hfile_present: bool,
    pub identity_match: bool,
    pub image_handle_closed: bool,
    pub first_continue_succeeded: bool,
    pub prepare_released: bool,
    pub start_attempted: bool,
    pub stdout_peek_error: Option<u32>,
    pub stderr_peek_error: Option<u32>,
    pub pre_admission_empty: bool,
    pub termination_requested: bool,
    pub exit_event_continued: bool,
    pub process_signaled: bool,
    pub exit_code: Option<u32>,
    pub debug_exit_code: Option<u32>,
    pub host_io: Option<IoReport>,
    pub local_handles_retired: bool,
    pub pin_retired: bool,
    pub errors: Vec<String>,
    pub native_errors: Vec<(String, u32)>,
    pub event_count: u32,
}
impl LaunchReport {
    fn definite_no_child(&self) -> bool {
        !self.child_created && self.pid == 0 && self.tid == 0
        && ((!self.create_call_entered && !self.create_call_returned)
            || (self.create_call_entered && self.create_call_returned && self.create_result_consistent))
    }
    pub fn no_child_proven(&self) -> bool {
        self.definite_no_child() && self.local_handles_retired
    }
    pub fn admitted(&self) -> bool {
        self.identity_match && self.image_handle_closed && self.first_continue_succeeded
    }
    pub fn may_prepare(&self) -> bool {
        self.admitted() && self.errors.is_empty() && self.pre_admission_empty && self.create_event && self.image_hfile_present
    }
    pub fn clean_success(&self) -> bool {
        self.admitted() && self.exit_event_continued && self.process_signaled && self.exit_code == Some(0)
        && self.local_handles_retired && self.pin_retired && self.errors.is_empty()
        && self.host_io.as_ref().is_some_and(IoReport::clean)
    }
    pub fn rejection_retired(&self) -> bool {
        self.create_result_consistent && !self.first_continue_succeeded && self.termination_requested && self.exit_event_continued
        && self.process_signaled && self.local_handles_retired && self.pin_retired
        && self.host_io.as_ref().is_some_and(IoReport::clean)
    }
}
#[cfg(test)]
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum LaunchFault {
    CancelAtCreate,
    WaitBeforeCreate
}
pub(super) struct OwnedBroker {
    pub report: LaunchReport,
    image: RetainedImage,
    process: Handle,
    thread: Handle,
    ends: [Handle; 6],
    transferred: bool,
    close_failed: bool,
    rejected: bool,
    breakpoint: bool,
    pending: Option<(u32, NTSTATUS, bool, bool)>,
    deadline: Instant,
    _owner: PhantomData<Rc<()>>,
    #[cfg(test)]
    fault: Option<LaunchFault>,
}
impl OwnedBroker {
    pub fn create(spec: &LaunchSpec, image: RetainedImage) -> Self {
        let mut owner = Self {
            report: LaunchReport {
                retained: Some(image.identity.clone()),
                ..Default::default()
            },
            image,
            process: Handle::empty(),
            thread: Handle::empty(),
            ends: std::array::from_fn(|_| Handle::empty()),
            transferred: false,
            close_failed: false,
            rejected: false,
            breakpoint: false,
            pending: None,
            deadline: Instant::now() + Duration::from_secs(5),
            _owner: PhantomData,
            #[cfg(test)]
            fault: None,
        };
        if let Err(error) = owner.create_native(spec) {
            owner.fail(error);
        }
        for i in [0, 3, 5] {
            if let Err(error) = owner.ends[i].close() {
                owner.close_failed = true;
                owner.fail(error);
            }
        }
        if let Err(error) = owner.thread.close() {
            owner.close_failed = true;
            owner.fail(error);
        }
        owner
    }
    fn create_native(&mut self, spec: &LaunchSpec) -> Result<(), String> {
        let mut prepared = super::host_io::PreparedLaunch::new(spec, &mut self.ends)?;
        let mut pi = PROCESS_INFORMATION::default();
        self.report.create_call_entered = true;
        let created = unsafe {
            CreateProcessW(PCWSTR(prepared.application.as_ptr()), Some(PWSTR(prepared.command.as_mut_ptr())), None, None, true,
                DEBUG_ONLY_THIS_PROCESS | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                Some(prepared.environment.as_ptr().cast()), PCWSTR(prepared.cwd.as_ptr()), &prepared.startup.StartupInfo, &mut pi)
        };
        self.report.create_call_returned = true;
        let empty = pi.hProcess.is_invalid() && pi.hThread.is_invalid() && pi.dwProcessId == 0 && pi.dwThreadId == 0;
        self.report.child_created = created.is_ok() || !empty;
        self.report.create_result_consistent = if created.is_ok() {
            !pi.hProcess.is_invalid() && !pi.hThread.is_invalid() && pi.dwProcessId != 0 && pi.dwThreadId != 0
        } else {
            empty
        };
        self.process = Handle(pi.hProcess);
        self.thread = Handle(pi.hThread);
        self.report.pid = pi.dwProcessId;
        self.report.tid = pi.dwThreadId;
        if let Err(error) = created {
            self.native("CreateProcessW", error);
            return Err("native creation failed".into());
        }
        if !self.report.create_result_consistent {
            return Err("inconsistent process information".into());
        }
        Ok(())
    }
    fn fail(&mut self, error: String) {
        if self.report.errors.len() < 32 {
            self.report.errors.push(error.chars().take(512).collect());
        }
    }
    fn native(&mut self, op: &str, error: windows::core::Error) {
        if self.report.native_errors.len() < 64 {
            self.report.native_errors.push((op.into(), image::raw_error(&error)));
        }
        self.fail(image::win_error(op, error));
    }
    #[cfg(test)]
    pub fn set_fault(&mut self, fault: LaunchFault) {
        self.fault = Some(fault);
    }
    pub fn terminate_before_start(&mut self) {
        if self.report.start_attempted {
            self.fail("refused broker kill after Start boundary".into());
            return;
        }
        self.poll_process();
        if self.report.termination_requested || self.report.process_signaled || self.process.0.is_invalid() {
            return;
        }
        match unsafe { TerminateProcess(self.process.0, 125) } {
            Ok(()) => self.report.termination_requested = true,
            Err(error) => {
                self.poll_process();
                if !self.report.process_signaled {
                    self.native("TerminateProcess", error);
                }
            }
        }
    }
    pub fn poll_process(&mut self) {
        if self.process.0.is_invalid() || self.report.process_signaled {
            return;
        }
        match unsafe { WaitForSingleObject(self.process.0, 0) } {
            WAIT_OBJECT_0 => {
                self.report.process_signaled = true;
                let mut code = 0;
                match unsafe { GetExitCodeProcess(self.process.0, &mut code) } {
                    Ok(()) => {
                        self.report.exit_code = Some(code);
                        if self.report.debug_exit_code.is_some_and(|event| event != code) {
                            self.fail("debug/process exit code mismatch".into());
                        }
                    },
                    Err(error) => self.native("GetExitCodeProcess", error),
                }
            }
            WAIT_TIMEOUT => {}
            _ => self.native("process wait", windows::core::Error::from_win32()),
        }
    }
    fn inspect_image(&mut self, event: &DEBUG_EVENT) {
        let mut image = Handle(unsafe { event.u.CreateProcessInfo.hFile });
        self.report.image_hfile_present = !image.0.is_invalid();
        match image::fingerprint(image.0) {
            Ok(identity) => {
                self.report.identity_match = self.report.retained.as_ref() == Some(&identity);
                self.report.observed = Some(identity);
            }
            Err(error) => self.fail(error),
        }
        let mut empty = true;
        for (index, stdout) in [(2, true), (4, false)] {
            let mut count = 0;
            let error = unsafe { PeekNamedPipe(
                    self.ends[index].0,
                    None,
                    0,
                    None,
                    Some(&mut count),
                    None
                ) }.err();
            if stdout {
                self.report.stdout_peek_error = error.as_ref().map(image::raw_error);
            }
            else {
                self.report.stderr_peek_error = error.as_ref().map(image::raw_error);
            }
            empty &= error.is_none() && count == 0;
            if let Some(error) = error {
                self.native("pre-admission peek", error);
            }
        }
        self.report.pre_admission_empty = empty;
        if !empty {
            self.fail("pre-admission pipe observation not empty".into());
        }
        match image.close() {
            Ok(()) => self.report.image_handle_closed = self.report.image_hfile_present,
            Err(error) => {
                self.close_failed = true;
                self.fail(error);
            }
        }
        if !self.report.identity_match {
            self.fail("actual image identity mismatch".into());
        }
    }
    pub fn pump(&mut self, allow_admission: bool) {
        if self.report.exit_event_continued || self.report.definite_no_child() {
            self.poll_process();
            std::thread::sleep(Duration::from_millis(10));
            return;
        }
        if !self.report.first_continue_succeeded && (!allow_admission || Instant::now() >= self.deadline) {
            self.rejected = true;
            self.fail("admission cancelled or deadline expired".into());
        }
        #[cfg(test)]
        if self.fault == Some(LaunchFault::WaitBeforeCreate) {
            self.fault = None;
            self.native(
                "injected WaitForDebugEvent",
                windows::core::Error::from_hresult(windows::core::HRESULT::from_win32(31)));
        }
        if !self.report.first_continue_succeeded && !self.report.errors.is_empty() {
            self.terminate_before_start();
        }
        if self.pending.is_none() {
            let mut event = DEBUG_EVENT::default();
            if let Err(error) = unsafe { WaitForDebugEvent(&mut event, 50) } {
                if image::raw_error(&error) != ERROR_SEM_TIMEOUT.0 {
                    self.native("WaitForDebugEvent", error);
                }
                self.poll_process();
                return;
            }
            self.report.event_count = self.report.event_count.saturating_add(1);
            if event.dwProcessId != self.report.pid {
                self.fail("debug event has wrong process".into());
                return;
            }
            if !self.report.create_event && event.dwDebugEventCode != CREATE_PROCESS_DEBUG_EVENT {
                self.fail("first event was not process creation".into());
            }
            let mut continuation = DBG_CONTINUE;
            match event.dwDebugEventCode {
                CREATE_PROCESS_DEBUG_EVENT => {
                    if self.report.create_event || event.dwThreadId != self.report.tid {
                        self.fail("duplicate or wrong initial thread".into());
                    }
                    self.report.create_event = true;
                    self.inspect_image(&event);
                    #[cfg(test)]
                    if self.fault == Some(LaunchFault::CancelAtCreate) {
                        self.fault = None;
                        self.rejected = true;
                        self.fail("injected cancellation before Continue".into());
                    }
                }
                LOAD_DLL_DEBUG_EVENT => {
                    if let Err(error) = Handle(
                        unsafe { event.u.LoadDll.hFile }
                    ).close() {
                        self.close_failed = true;
                        self.fail(error);
                    }
                }
                EXCEPTION_DEBUG_EVENT => {
                    let exception = unsafe { event.u.Exception };
                    continuation = DBG_EXCEPTION_NOT_HANDLED;
                    if exception.dwFirstChance != 0 && exception.ExceptionRecord.ExceptionCode == EXCEPTION_BREAKPOINT && !self.breakpoint && self.report.first_continue_succeeded {
                        self.breakpoint = true;
                        continuation = DBG_CONTINUE;
                    } else if exception.dwFirstChance == 0 {
                        self.fail(
                            format!("second-chance exception raw={}", exception.ExceptionRecord.ExceptionCode.0 as u32)
                        );
                    }
                }
                EXIT_PROCESS_DEBUG_EVENT => {
                    self.report.debug_exit_code = Some(
                        unsafe { event.u.ExitProcess.dwExitCode }
                    );
                }
                CREATE_THREAD_DEBUG_EVENT | EXIT_THREAD_DEBUG_EVENT | UNLOAD_DLL_DEBUG_EVENT | OUTPUT_DEBUG_STRING_EVENT => {}
                _ => self.fail("unexpected debug event".into()),
            }
            self.pending = Some(
                (event.dwThreadId, continuation, event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT, event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT)
            );
            // Remember event kind independently of a failed continuation retry.
            self.continue_event();
        } else {
            self.continue_event();
        }
        self.poll_process();
    }
    fn continue_event(&mut self) {
        let Some((tid, continuation, create, exit)) = self.pending else {
            return;
        };
        if create && !self.report.first_continue_succeeded && Instant::now() >= self.deadline {
            self.rejected = true;
            self.fail("admission deadline expired before first Continue".into());
        }
        if !self.report.first_continue_succeeded && (!self.report.errors.is_empty() || self.rejected) {
            self.terminate_before_start();
            if !self.report.termination_requested && !self.report.process_signaled {
                std::thread::sleep(Duration::from_millis(10));
                return;
            }
        }
        match unsafe { ContinueDebugEvent(self.report.pid, tid, continuation) } {
            Ok(()) => {
                self.pending = None;
                if create && self.report.errors.is_empty() && !self.rejected {
                    self.report.first_continue_succeeded = true;
                }
                if exit {
                    self.report.exit_event_continued = true;
                }
            }
            Err(error) => self.native("ContinueDebugEvent", error),
        }
    }
    pub fn take_pipes(&mut self) -> Option<Pipes> {
        if self.transferred || !self.report.create_event {
            return None;
        }
        if [1, 2, 4].iter().any(|&i| self.ends[i].0.is_invalid()) {
            return None;
        }
        self.transferred = true;
        let mut take = |i| std::mem::replace(&mut self.ends[i], Handle::empty()).into_file();
        Some(Pipes {
                stdin: take(1),
                stdout: take(2),
                stderr: take(4)
        })
    }
    pub fn retire(&mut self, io: &IoReport) -> bool {
        let no_child = self.report.definite_no_child();
        if !no_child && (!self.report.exit_event_continued || !self.report.process_signaled || !self.transferred || !io.joined()) {
            return false;
        }
        if self.transferred {
            self.report.host_io = Some(io.clone());
        }
        for index in 0..6 {
            if let Err(error) = self.ends[index].close() {
                self.close_failed = true;
                self.fail(error);
            }
        }
        for result in [self.thread.close(), self.process.close(), self.image.close()] {
            if let Err(error) = result {
                self.close_failed = true;
                self.fail(error);
            }
        }
        self.report.pin_retired = !self.close_failed;
        self.report.local_handles_retired = !self.close_failed;
        self.report.local_handles_retired
    }
}
