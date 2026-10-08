//! CI-only concrete owner. Production launch-image/ancestor authority is unresolved.
//! Retained hashing checks mutation under the trusted private-parent assumption only.
use super::{native_drain, ToolContext};
use protocol::{Cleanup, Event, Fixture, GuestResult, Kind, Op, Request, State, Validator};
use sha2::{Digest, Sha256};
use std::io::Read;
use std::os::windows::fs::OpenOptionsExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{mpsc, Arc};
use tokio::sync::watch;
mod protocol;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Outcome { Pending, Completed, Cancelled, Uncertain, NotStarted }
struct CiBundle {
    root: PathBuf,
    exe: PathBuf,
    sha256: String,
    source: String,
}
#[derive(Clone, Debug)]
struct Completion {
    outcome: Outcome,
    state: State,
    session: String,
    vm_id: String,
    runtime_id: String,
    guest: Option<GuestResult>,
    cleanup: Option<Cleanup>,
    trace: Vec<(u64, Kind)>,
    errors: Vec<String>,
}
#[derive(Clone)]
struct CompletionObserver { rx: watch::Receiver<Arc<Completion>> }
impl CompletionObserver {
    fn snapshot(&self) -> Arc<Completion> { self.rx.borrow().clone() }
    async fn wait(&self) -> Result<Arc<Completion>, String> {
        let mut rx = self.rx.clone();
        loop {
            let value = rx.borrow().clone();
            if value.outcome != Outcome::Pending { return Ok(value); }
            rx.changed().await.map_err(|_| "owner lost; recovery fence retained")?;
        }
    }
    async fn wait_for_guest(&self) -> Result<Arc<Completion>, String> {
        let mut rx = self.rx.clone();
        loop {
            let value = rx.borrow().clone();
            if value.guest.is_some() { return Ok(value); }
            if value.outcome != Outcome::Pending { return Err(format!("{:?}", value.errors)); }
            rx.changed().await.map_err(|_| "owner lost; recovery fence retained")?;
        }
    }
}
enum Message { Control(Op), Frame(Event), End(Result<(), String>) }
pub(crate) struct WindowsVmSession {
    control: mpsc::Sender<Message>,
    completion: CompletionObserver,
}
impl WindowsVmSession {
    // Only child tests can construct this bundle; no production arbitrary-path entry.
    fn start(ctx: &ToolContext, bundle: CiBundle, fixture: Fixture) -> Result<Self, String> {
        if ctx.native_work.is_none() || ctx.root_scope.is_none() {
            return Err("paired root/cloud scopes required".into());
        }
        let guard = native_drain::child(ctx).map_err(|e| e.to_string())?;
        let v = Validator::new(bundle.source.clone(), uuid::Uuid::new_v4().to_string());
        let (tx, rx) = watch::channel(Arc::new(v.snapshot(Outcome::Pending, Vec::new())));
        let (control, commands) = mpsc::channel();
        let sender = control.clone();
        std::thread::Builder::new().name("windows-vm-owner".into())
            .spawn(move || run_owner(guard, bundle, fixture, v, commands, sender, tx))
            .map_err(|e| e.to_string())?;
        Ok(Self { control, completion: CompletionObserver { rx } })
    }
    fn observer(&self) -> CompletionObserver { self.completion.clone() }
    fn cancel(&self) { let _ = self.control.send(Message::Control(Op::Cancel)); }
    fn finish(&self) { let _ = self.control.send(Message::Control(Op::Finish)); }
}
impl Drop for WindowsVmSession { fn drop(&mut self) { self.cancel(); } }

impl Validator {
    fn snapshot(&self, outcome: Outcome, errors: Vec<String>) -> Completion {
        Completion { outcome, state: self.stage, session: self.session.clone(), vm_id: self.vm_id.clone(),
            runtime_id: self.runtime_id.clone(), guest: self.guest.clone(), cleanup: self.cleanup.clone(), trace: self.trace.clone(), errors }
    }
}
fn pin(bundle: &CiBundle) -> Result<std::fs::File, String> {
    let mut file = std::fs::OpenOptions::new().read(true).share_mode(1).open(&bundle.exe)
        .map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    let mut bytes = [0u8; 8192];
    loop {
        let n = file.read(&mut bytes).map_err(|e| e.to_string())?;
        if n == 0 { break; }
        hasher.update(&bytes[..n]);
    }
    if format!("{:x}", hasher.finalize()) != bundle.sha256 { return Err("broker mutation check".into()); }
    Ok(file) // Held through actual helper wait, not a production launch-image proof.
}
fn run_owner(
    mut guard: Option<native_drain::NativeGuard>, bundle: CiBundle, fixture: Fixture,
    mut v: Validator, commands: mpsc::Receiver<Message>, sender: mpsc::Sender<Message>,
    updates: watch::Sender<Arc<Completion>>,
) {
    let prepared = (|| {
        native_drain::begin(&mut guard).map_err(|e| e.to_string())?;
        let pinned = pin(&bundle)?;
        let child = Command::new(&bundle.exe).arg("--session-root").arg(&bundle.root)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
            .spawn().map_err(|e| e.to_string())?;
        Ok::<_, String>((pinned, child))
    })();
    let (_pinned, mut child) = match prepared {
        Ok(value) => value,
        Err(error) => {
            native_drain::complete(guard);
            updates.send_replace(Arc::new(v.snapshot(Outcome::NotStarted, vec![error])));
            return;
        }
    };
    let mut stdin = child.stdin.take().expect("owned piped stdin");
    let mut stdout = child.stdout.take().expect("owned piped stdout");
    let mut stderr = child.stderr.take().expect("owned piped stderr");
    let reader = std::thread::spawn(move || {
        let mut total = 0;
        let result = loop {
            match protocol::read_event(&mut stdout, &mut total) {
                Ok(Some(event)) => { if sender.send(Message::Frame(event)).is_err() { break Err("owner lost".into()); } }
                Ok(None) => break Ok(()),
                Err(error) => break Err(error),
            }
        };
        let _ = sender.send(Message::End(result));
    });
    let errors_reader = std::thread::spawn(move || {
        let (mut count, mut bytes) = (0usize, [0u8; 8192]);
        loop {
            match stderr.read(&mut bytes) {
                Ok(0) => return count <= protocol::MAX_FRAME,
                Ok(n) => count = count.saturating_add(n),
                Err(_) => return false,
            }
        }
    });
    let (mut seq, mut total) = (0, 0);
    let request_session = v.session.clone();
    let mut send = |op| {
        let request = Request { version: 1, source: bundle.source.clone(), session: request_session.clone(), seq, op, fixture };
        seq += 1;
        protocol::write_request(&mut stdin, &request, &mut total)
    };
    let (mut cancelled, mut teardown, mut finishing) = (false, false, false);
    let mut errors = Vec::new();
    if let Err(error) = send(Op::Prepare) { v.failed = true; errors.push(error); }
    loop {
        let mut next = None;
        match commands.recv() {
            Ok(Message::Control(Op::Cancel)) => { cancelled = true; if !teardown && v.cleanup.is_none() { next = Some(Op::Cancel); } }
            Ok(Message::Control(Op::Finish)) => { if !finishing && !teardown { finishing = true; if v.guest.is_some() { next = Some(Op::Finish); } } }
            Ok(Message::Control(_)) => { v.failed = true; }
            Ok(Message::Frame(event)) => {
                if !event.error.is_empty() { errors.push(format!("host error: {}", event.error)); }
                if let Err(error) = v.accept(&event) { errors.push(error); if !teardown { next = Some(Op::Cancel); } }
                else if event.kind == Kind::Prepared && !teardown { v.start_attempted(); next = Some(Op::Start); }
                else if event.kind == Kind::Guest && finishing && !teardown { next = Some(Op::Finish); }
            }
            Ok(Message::End(result)) => { if let Err(error) = result { v.failed = true; errors.push(error); if !teardown { let _ = send(Op::Cancel); } } break; }
            Err(_) => { v.failed = true; errors.push("owner channel lost".into()); break; }
        }
        if let Some(op) = next {
            teardown |= op == Op::Cancel || op == Op::Finish;
            if let Err(error) = send(op) { v.failed = true; errors.push(error); }
        }
        updates.send_replace(Arc::new(v.snapshot(Outcome::Pending, errors.clone())));
    }
    drop(send);
    drop(stdin);
    let reader_joined = reader.join().is_ok();
    let host_joined = errors_reader.join().unwrap_or(false) && reader_joined;
    let helper_ok = child.wait().is_ok_and(|status| status.success());
    let outcome = if v.finish(host_joined, helper_ok, cancelled) {
        native_drain::complete(guard);
        if cancelled { Outcome::Cancelled } else { Outcome::Completed }
    } else {
        errors.push("uncertain cleanup; paired recovery fence retained".into());
        drop(guard);
        Outcome::Uncertain // Running guard Drop makes uncertainty persistent.
    };
    updates.send_replace(Arc::new(v.snapshot(outcome, errors)));
}
#[cfg(test)]
mod tests;
#[cfg(test)]
mod native_tests;
