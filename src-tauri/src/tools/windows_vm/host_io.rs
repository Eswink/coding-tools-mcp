//! Finite writer queue and actual EOF/join accounting; no owner-side blocking IO.
use super::{
    image::{self, close_file, Handle},
    protocol, Message, Op, Request,
};
use serde::Serialize;
use std::fs::File;
use std::io::{Read, Write};
use std::mem::size_of;
use std::sync::mpsc::{self, Receiver, SyncSender, TrySendError};
use std::thread::JoinHandle;
use windows::Win32::Foundation::{
    SetHandleInformation, ERROR_INSUFFICIENT_BUFFER, HANDLE, HANDLE_FLAGS, HANDLE_FLAG_INHERIT,
};
use windows::Win32::Security::SECURITY_ATTRIBUTES;
use windows::Win32::System::{Pipes::CreatePipe, Threading::*};

pub(super) struct Pipes {
    pub stdin: File,
    pub stdout: File,
    pub stderr: File,
}
#[derive(Clone, Debug, Default, Serialize)]
pub(super) struct IoReport {
    pub writer_joined: bool,
    pub stdout_joined: bool,
    pub stderr_joined: bool,
    pub stdin_closed: bool,
    pub stdout_closed: bool,
    pub stderr_closed: bool,
    pub stdout_eof: bool,
    pub stderr_eof: bool,
    pub stdout_bytes: usize,
    pub stderr_bytes: usize,
    pub raw_stdout: Vec<u8>,
    pub raw_stderr: Vec<u8>,
    pub errors: Vec<String>,
}
impl IoReport {
    pub fn joined(&self) -> bool {
        self.writer_joined && self.stdout_joined && self.stderr_joined
    }
    pub fn clean(&self) -> bool {
        self.joined()
            && self.stdin_closed
            && self.stdout_closed
            && self.stderr_closed
            && self.stdout_eof
            && self.stderr_eof
            && self.errors.is_empty()
    }
}
#[derive(Default)]
struct ReadResult {
    bytes: usize,
    eof: bool,
    closed: bool,
    raw: Vec<u8>,
    errors: Vec<String>,
}
fn reader(mut file: File, sender: Option<mpsc::Sender<Message>>) -> ReadResult {
    let mut result = ReadResult::default();
    if let Some(sender) = sender {
        let end = loop {
            match protocol::read_event(&mut file, &mut result.bytes) {
                Ok(Some(event)) => {
                    if sender.send(Message::Frame(event)).is_err() {
                        break Err("owner lost".into());
                    }
                }
                Ok(None) => {
                    result.eof = true;
                    break Ok(());
                }
                Err(error) => break Err(error),
            }
        };
        if let Err(error) = &end {
            result.errors.push(error.clone());
        }
        let _ = sender.send(Message::End(end));
    } else {
        let mut bytes = [0u8; 8192];
        loop {
            match file.read(&mut bytes) {
                Ok(0) => {
                    result.eof = true;
                    break;
                }
                Ok(n) => {
                    result.bytes = result.bytes.saturating_add(n);
                    let room = protocol::MAX_FRAME.saturating_sub(result.raw.len());
                    result.raw.extend_from_slice(&bytes[..n.min(room)]);
                }
                Err(error) => {
                    result.errors.push(format!("pipe read: {error:?}"));
                    break;
                }
            }
        }
        if result.bytes > protocol::MAX_FRAME {
            result.errors.push("raw pipe bound exceeded".into());
        }
    }
    match close_file(file) {
        Ok(()) => result.closed = true,
        Err(error) => result.errors.push(error),
    }
    result
}
struct WriteResult {
    closed: bool,
    errors: Vec<String>,
}
fn writer<W: Write>(
    mut sink: W,
    requests: Receiver<Request>,
    ack: mpsc::Sender<Result<(), String>>,
    close: impl FnOnce(W) -> Result<(), String>,
) -> WriteResult {
    let mut total = 0;
    let mut errors = Vec::new();
    while let Ok(request) = requests.recv() {
        let terminal = matches!(request.op, Op::Cancel | Op::Finish);
        let result = protocol::write_request(&mut sink, &request, &mut total);
        let failed = result.is_err();
        if let Err(error) = &result {
            errors.push(error.clone());
        }
        let _ = ack.send(result);
        if terminal || failed {
            break;
        }
    }
    let closed = match close(sink) {
        Ok(()) => true,
        Err(error) => {
            errors.push(error);
            false
        }
    };
    WriteResult { closed, errors }
}
pub(super) struct HostIo {
    requests: Option<SyncSender<Request>>,
    ack: Receiver<Result<(), String>>,
    inflight: usize,
    writer: Option<JoinHandle<WriteResult>>,
    stdout: Option<JoinHandle<ReadResult>>,
    stderr: Option<JoinHandle<ReadResult>>,
    report: IoReport,
}
impl HostIo {
    fn spawn(pipes: Pipes, sender: Option<mpsc::Sender<Message>>) -> Self {
        let (requests, rx) = mpsc::sync_channel(1);
        let (tx, ack) = mpsc::channel();
        Self {
            requests: Some(requests),
            ack,
            inflight: 0,
            writer: Some(std::thread::spawn(move || {
                writer(pipes.stdin, rx, tx, close_file)
            })),
            stdout: Some(std::thread::spawn(move || reader(pipes.stdout, sender))),
            stderr: Some(std::thread::spawn(move || reader(pipes.stderr, None))),
            report: IoReport::default(),
        }
    }
    pub fn protocol(pipes: Pipes, sender: mpsc::Sender<Message>) -> Self {
        Self::spawn(pipes, Some(sender))
    }
    pub fn raw(pipes: Pipes) -> Self {
        let mut io = Self::spawn(pipes, None);
        io.close_input();
        io
    }
    pub fn try_request(&mut self, request: Request) -> Result<bool, String> {
        let sender = self
            .requests
            .as_ref()
            .ok_or("stdin writer already closed")?;
        match sender.try_send(request) {
            Ok(()) => {
                self.inflight += 1;
                Ok(true)
            }
            Err(TrySendError::Full(_)) => Ok(false),
            Err(TrySendError::Disconnected(_)) => Err("stdin writer lost".into()),
        }
    }
    pub fn close_input(&mut self) {
        self.requests.take();
    }
    pub fn close_after_terminal(&mut self, terminal_accepted: bool, process_signaled: bool) {
        if terminal_accepted || process_signaled {
            self.close_input();
        }
    }
    pub fn idle(&self) -> bool {
        self.inflight == 0
    }
    pub fn poll(&mut self) -> IoReport {
        self.poll_with_budget(&mut 8)
    }
    pub fn poll_with_budget(&mut self, budget: &mut usize) -> IoReport {
        for _ in 0..*budget {
            let Ok(result) = self.ack.try_recv() else {
                break;
            };
            *budget -= 1;
            self.inflight = self.inflight.saturating_sub(1);
            if let Err(error) = result {
                self.report.errors.push(error);
                self.close_input();
            }
        }
        if self
            .writer
            .as_ref()
            .is_some_and(|worker| worker.is_finished())
        {
            self.report.writer_joined = true;
            match self.writer.take().unwrap().join() {
                Ok(result) => {
                    self.report.stdin_closed = result.closed;
                    self.report.errors.extend(result.errors);
                }
                Err(_) => self.report.errors.push("stdin worker panicked".into()),
            }
        }
        for (worker, stdout) in [(&mut self.stdout, true), (&mut self.stderr, false)] {
            if !worker.as_ref().is_some_and(|worker| worker.is_finished()) {
                continue;
            }
            if stdout {
                self.report.stdout_joined = true;
            } else {
                self.report.stderr_joined = true;
            }
            match worker.take().unwrap().join() {
                Ok(result) => {
                    if stdout {
                        self.report.stdout_eof = result.eof;
                        self.report.stdout_closed = result.closed;
                        self.report.stdout_bytes = result.bytes;
                        self.report.raw_stdout = result.raw;
                    } else {
                        self.report.stderr_eof = result.eof;
                        self.report.stderr_closed = result.closed;
                        self.report.stderr_bytes = result.bytes;
                        self.report.raw_stderr = result.raw;
                    }
                    self.report.errors.extend(result.errors);
                }
                Err(_) => self.report.errors.push("output worker panicked".into()),
            }
        }
        self.report.clone()
    }
    #[cfg(test)]
    pub fn test_writer(
        latch: std::sync::Arc<(std::sync::Mutex<bool>, std::sync::Condvar)>,
    ) -> Self {
        struct Latched(std::sync::Arc<(std::sync::Mutex<bool>, std::sync::Condvar)>);
        impl Write for Latched {
            fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
                let (lock, ready) = &*self.0;
                let mut released = lock.lock().unwrap();
                while !*released {
                    released = ready.wait(released).unwrap();
                }
                Ok(bytes.len())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let (requests, rx) = mpsc::sync_channel(1);
        let (tx, ack) = mpsc::channel();
        Self {
            requests: Some(requests),
            ack,
            inflight: 0,
            writer: Some(std::thread::spawn(move || {
                writer(Latched(latch), rx, tx, |_| Ok(()))
            })),
            stdout: None,
            stderr: None,
            report: IoReport::default(),
        }
    }
}

struct Attributes {
    _storage: Vec<usize>,
    pointer: LPPROC_THREAD_ATTRIBUTE_LIST,
}
impl Attributes {
    fn new(handles: &[HANDLE; 3]) -> Result<Self, String> {
        let mut bytes = 0;
        let first = unsafe { InitializeProcThreadAttributeList(None, 1, None, &mut bytes) };
        if first.as_ref().err().map(image::raw_error) != Some(ERROR_INSUFFICIENT_BUFFER.0)
            || bytes == 0
            || bytes > 65536
        {
            return Err(format!(
                "attribute-list size query failed: raw={:?}, bytes={bytes}",
                first.err().as_ref().map(image::raw_error)
            ));
        }
        let mut storage = vec![0usize; bytes.div_ceil(size_of::<usize>())];
        let pointer = LPPROC_THREAD_ATTRIBUTE_LIST(storage.as_mut_ptr().cast());
        unsafe { InitializeProcThreadAttributeList(Some(pointer), 1, None, &mut bytes) }
            .map_err(|e| image::win_error("attribute init", e))?;
        let owned = Self {
            _storage: storage,
            pointer,
        };
        unsafe {
            UpdateProcThreadAttribute(
                pointer,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST as usize,
                Some(handles.as_ptr().cast()),
                size_of::<[HANDLE; 3]>(),
                None,
                None,
            )
        }
        .map_err(|e| image::win_error("handle list", e))?;
        Ok(owned)
    }
}
impl Drop for Attributes {
    fn drop(&mut self) {
        unsafe { DeleteProcThreadAttributeList(self.pointer) };
    }
}
// Every pointer registered below refers to stable heap storage through creation.
pub(super) struct PreparedLaunch {
    pub application: Vec<u16>,
    pub command: Vec<u16>,
    pub cwd: Vec<u16>,
    pub environment: Vec<u16>,
    pub startup: STARTUPINFOEXW,
    _attributes: Attributes,
    _handles: Box<[HANDLE; 3]>,
}
impl PreparedLaunch {
    pub fn new(spec: &super::launch::LaunchSpec, ends: &mut [Handle; 6]) -> Result<Self, String> {
        let application = image::wide(&spec.application)?;
        let cwd = image::wide(&spec.cwd)?;
        let root = image::wide(&spec.session_root)?;
        let mut command = Vec::new();
        image::quoted(&application, &mut command);
        command.extend(" --session-root ".encode_utf16());
        image::quoted(&root, &mut command);
        command.push(0);
        if command.len() > 32767 {
            return Err("command length bound".into());
        }
        let environment = image::environment(&root)?;
        let security = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            bInheritHandle: true.into(),
            ..Default::default()
        };
        for index in [0, 2, 4] {
            let (left, right) = ends.split_at_mut(index + 1);
            unsafe { CreatePipe(&mut left[index].0, &mut right[0].0, Some(&security), 0) }
                .map_err(|e| image::win_error("CreatePipe", e))?;
        }
        for i in [1, 2, 4] {
            unsafe { SetHandleInformation(ends[i].0, HANDLE_FLAG_INHERIT.0, HANDLE_FLAGS(0)) }
                .map_err(|e| image::win_error("pipe inheritance", e))?;
        }
        let handles = Box::new([ends[0].0, ends[3].0, ends[5].0]);
        let attributes = Attributes::new(&handles)?;
        let mut startup = STARTUPINFOEXW::default();
        startup.lpAttributeList = attributes.pointer;
        startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = handles[0];
        startup.StartupInfo.hStdOutput = handles[1];
        startup.StartupInfo.hStdError = handles[2];
        Ok(Self {
            application,
            command,
            cwd,
            environment,
            startup,
            _attributes: attributes,
            _handles: handles,
        })
    }
}

// EOF is an observation, not permission to discard a queued cancellation.
impl super::OwnerProgress {
    pub(super) fn on_end(
        &mut self,
        result: Result<(), String>,
        cleanup_accepted: bool,
        errors: &mut Vec<String>,
    ) -> bool {
        let error = match result {
            Ok(()) if cleanup_accepted => return false,
            Ok(()) => "stdout EOF before accepted cleanup".into(),
            Err(error) => error,
        };
        super::note_error(errors, error);
        self.mark_uncertain();
        true
    }
}
