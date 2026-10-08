//! CI-only concrete owner. Production launch-image/ancestor authority is unresolved.
//! Image admission is local proof; HCS retirement and host trust remain independent.
use super::{native_drain, ToolContext};
use protocol::{Cleanup, Event, Fixture, GuestResult, Kind, Op, Request, State, Validator};
#[cfg(test)]
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::sync::{mpsc, Arc};
use std::time::{Duration, Instant};
use tokio::sync::watch;
mod host_io;
mod image;
mod launch;
mod protocol;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Outcome {
    Pending,
    Completed,
    Cancelled,
    Uncertain,
    NotStarted,
}
struct CiBundle {
    root: PathBuf,
    exe: PathBuf,
    sha256: String,
    source: String,
}
impl CiBundle {
    fn valid(&self) -> bool {
        let hashes = [(self.source.as_str(), 40), (self.sha256.as_str(), 64)];
        self.root.is_absolute()
            && self.exe.is_absolute()
            && self.exe == self.root.join("trusted-code/broker.exe")
            && hashes.iter().all(|(value, len)| {
                value.len() == *len
                    && value
                        .bytes()
                        .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
            })
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
enum OwnershipStatus {
    Unobserved,
    Active,
    Retired,
    RecoveryFenced,
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
    launch: Option<launch::LaunchReport>,
    ownership: OwnershipStatus,
}
#[derive(Clone)]
struct CompletionObserver {
    rx: watch::Receiver<Arc<Completion>>,
}
impl CompletionObserver {
    fn snapshot(&self) -> Arc<Completion> {
        self.rx.borrow().clone()
    }
    async fn wait(&self) -> Result<Arc<Completion>, String> {
        let mut rx = self.rx.clone();
        loop {
            let value = rx.borrow().clone();
            if value.outcome != Outcome::Pending {
                return Ok(value);
            }
            rx.changed()
                .await
                .map_err(|_| "owner lost; recovery fence retained")?;
        }
    }
    async fn wait_for_guest(&self) -> Result<Arc<Completion>, String> {
        let mut rx = self.rx.clone();
        loop {
            let value = rx.borrow().clone();
            if value.guest.is_some() {
                return Ok(value);
            }
            if value.outcome != Outcome::Pending {
                return Err(format!("{:?}", value.errors));
            }
            rx.changed()
                .await
                .map_err(|_| "owner lost; recovery fence retained")?;
        }
    }
}
enum Message {
    Control(Op),
    Frame(Event),
    End(Result<(), String>),
}
pub(crate) struct WindowsVmSession {
    control: mpsc::Sender<Message>,
    completion: CompletionObserver,
}
impl WindowsVmSession {
    // Only child tests can construct this bundle; no production arbitrary-path entry.
    fn start(ctx: &ToolContext, bundle: CiBundle, fixture: Fixture) -> Result<Self, String> {
        if !bundle.valid() {
            return Err("invalid private CI bundle".into());
        }
        if ctx.native_work.is_none() || ctx.root_scope.is_none() {
            return Err("paired root/cloud scopes required".into());
        }
        let guard = native_drain::child(ctx).map_err(|e| e.to_string())?;
        let v = Validator::new(bundle.source.clone(), uuid::Uuid::new_v4().to_string());
        let initial = owner_snapshot(
            &v,
            Outcome::Pending,
            Vec::new(),
            launch::LaunchReport::default(),
            OwnershipStatus::Active,
        );
        let (tx, rx) = watch::channel(Arc::new(initial));
        let (control, commands) = mpsc::channel();
        let sender = control.clone();
        std::thread::Builder::new()
            .name("windows-vm-owner".into())
            .spawn(move || run_owner(guard, bundle, fixture, v, commands, sender, tx))
            .map_err(|e| e.to_string())?;
        Ok(Self {
            control,
            completion: CompletionObserver { rx },
        })
    }
    fn observer(&self) -> CompletionObserver {
        self.completion.clone()
    }
    fn cancel(&self) {
        let _ = self.control.send(Message::Control(Op::Cancel));
    }
    fn finish(&self) {
        let _ = self.control.send(Message::Control(Op::Finish));
    }
}
impl Drop for WindowsVmSession {
    fn drop(&mut self) {
        self.cancel();
    }
}

impl Validator {
    fn snapshot(&self, outcome: Outcome, errors: Vec<String>) -> Completion {
        Completion {
            outcome,
            state: self.stage,
            session: self.session.clone(),
            vm_id: self.vm_id.clone(),
            runtime_id: self.runtime_id.clone(),
            guest: self.guest.clone(),
            cleanup: self.cleanup.clone(),
            trace: self.trace.clone(),
            errors,
            launch: None,
            ownership: OwnershipStatus::Unobserved,
        }
    }
}
fn owner_snapshot(
    v: &Validator,
    outcome: Outcome,
    errors: Vec<String>,
    launch: launch::LaunchReport,
    ownership: OwnershipStatus,
) -> Completion {
    let mut completion = v.snapshot(outcome, errors);
    completion.launch = Some(launch);
    completion.ownership = ownership;
    completion
}
fn note_error(errors: &mut Vec<String>, error: String) {
    if errors.len() < 32 {
        errors.push(error.chars().take(512).collect());
    }
}
struct OwnerProgress {
    sticky_uncertain: bool,
}
impl OwnerProgress {
    fn new() -> Self {
        Self {
            sticky_uncertain: false,
        }
    }
    fn mark_uncertain(&mut self) {
        self.sticky_uncertain = true;
    }
    fn outcome(&self, proposed: Outcome) -> Outcome {
        if self.sticky_uncertain {
            Outcome::Uncertain
        } else {
            proposed
        }
    }
    fn snapshot(
        &mut self,
        v: &Validator,
        proposed: Outcome,
        errors: Vec<String>,
        launch: launch::LaunchReport,
        ownership: OwnershipStatus,
    ) -> Completion {
        if proposed == Outcome::Uncertain {
            self.mark_uncertain();
        }
        owner_snapshot(v, self.outcome(proposed), errors, launch, ownership)
    }
}
fn retire_no_child(
    guard: Option<native_drain::NativeGuard>,
    report: &launch::LaunchReport,
) -> (Outcome, OwnershipStatus) {
    if report.no_child_proven() {
        native_drain::complete(guard);
        (Outcome::NotStarted, OwnershipStatus::Retired)
    } else {
        drop(guard);
        (Outcome::Uncertain, OwnershipStatus::RecoveryFenced)
    }
}
fn run_owner(
    mut guard: Option<native_drain::NativeGuard>,
    bundle: CiBundle,
    fixture: Fixture,
    mut v: Validator,
    commands: mpsc::Receiver<Message>,
    sender: mpsc::Sender<Message>,
    updates: watch::Sender<Arc<Completion>>,
) {
    let mut progress = OwnerProgress::new();
    let mut errors = Vec::new();
    let prepared = native_drain::begin(&mut guard)
        .map_err(|e| image::ImageFailure {
            message: e.to_string(),
            resources_retired: true,
        })
        .and_then(|()| image::RetainedImage::open(&bundle.exe, &bundle.sha256));
    let pin = match prepared {
        Ok(pin) => pin,
        Err(error) => {
            let mut report = launch::LaunchReport::default();
            report.local_handles_retired = error.resources_retired;
            let (outcome, ownership) = retire_no_child(guard, &report);
            let completion = progress.snapshot(&v, outcome, vec![error.message], report, ownership);
            updates.send_replace(Arc::new(completion));
            return;
        }
    };
    let spec = launch::LaunchSpec {
        application: bundle.exe.clone(),
        cwd: bundle.exe.parent().unwrap_or(&bundle.root).to_path_buf(),
        session_root: bundle.root.clone(),
    };
    let mut broker = launch::OwnedBroker::create(&spec, pin);
    if !broker.report.child_created {
        broker.retire(&host_io::IoReport::default());
        let (outcome, ownership) = retire_no_child(guard, &broker.report);
        errors.extend(broker.report.errors.clone());
        let completion = progress.snapshot(&v, outcome, errors, broker.report.clone(), ownership);
        updates.send_replace(Arc::new(completion));
        return;
    }
    if !broker.report.create_result_consistent {
        progress.mark_uncertain();
    }
    let (mut io, mut pending, mut seq) = (None::<host_io::HostIo>, None, 0);
    let (mut cancelled, mut finishing, mut terminal_sent, mut write_failed) =
        (false, false, false, false);
    let start = Instant::now();
    let (mut write_since, mut retirement_since) = (None, None);
    loop {
        broker.pump(!cancelled && !progress.sticky_uncertain);
        cancelled |= progress.observe_admission_timeout(&broker.report);
        let mut budget = 8;
        let mut host = io.as_mut().map(|io| io.poll_with_budget(&mut budget));
        for _ in 0..budget {
            let message = match commands.try_recv() {
                Ok(message) => message,
                Err(mpsc::TryRecvError::Empty) => break,
                Err(mpsc::TryRecvError::Disconnected) => {
                    progress.mark_uncertain();
                    cancelled = true;
                    break;
                }
            };
            match message {
                Message::Control(Op::Cancel) => cancelled = true,
                Message::Control(Op::Finish) => finishing = true,
                Message::Control(_) => {
                    progress.mark_uncertain();
                    cancelled = true;
                }
                Message::Frame(event) => {
                    if let Err(error) = v.accept(&event) {
                        note_error(&mut errors, error);
                        progress.mark_uncertain();
                        cancelled = true;
                    } else if event.kind == Kind::Prepared && !cancelled {
                        pending = Some(Op::Start);
                    }
                }
                Message::End(result) => {
                    cancelled |= progress.on_end(result, v.cleanup.is_some(), &mut errors);
                }
            }
        }
        if io.is_none() {
            if let Some(pipes) = broker.take_pipes() {
                io = Some(if broker.report.admitted() {
                    host_io::HostIo::protocol(pipes, sender.clone())
                } else {
                    host_io::HostIo::raw(pipes)
                });
                if broker.report.may_prepare() && !cancelled {
                    pending = Some(Op::Prepare);
                }
            }
        }
        let now = Instant::now();
        let elapsed = now.duration_since(start);
        let expired = |since: Option<Instant>, seconds| {
            since.is_some_and(|time| now.duration_since(time) >= Duration::from_secs(seconds))
        };
        let stalled = elapsed >= Duration::from_secs(540)
            || expired(write_since, 10)
            || expired(retirement_since, 180)
            || (broker.report.admitted()
                && v.stage == State::RegisteredNoEffects
                && elapsed >= Duration::from_secs(30));
        if stalled && !progress.sticky_uncertain {
            note_error(
                &mut errors,
                "cooperative owner deadline; actual ownership retained".into(),
            );
            progress.mark_uncertain();
            cancelled = true;
        }
        if let Some(report) = &host {
            if !report.errors.is_empty() {
                progress.mark_uncertain();
                cancelled = true;
            }
        }
        if broker.report.admitted() && !broker.report.errors.is_empty() {
            progress.mark_uncertain();
            cancelled = true;
        }
        if cancelled || finishing && v.guest.is_some() {
            retirement_since.get_or_insert(now);
            if !terminal_sent && !write_failed && v.cleanup.is_none() {
                pending = Some(if cancelled { Op::Cancel } else { Op::Finish });
            }
        }
        if !v.started && (cancelled || !broker.report.errors.is_empty()) {
            broker.terminate_before_start();
            pending = None;
            if let Some(io) = io.as_mut() {
                io.close_input();
            }
        }
        if let Some(io) = io.as_mut() {
            if io.idle() {
                write_since = None;
            }
            if let Some(op) = pending {
                if op == Op::Start && !v.started {
                    v.start_attempted();
                    broker.report.start_attempted = true;
                }
                let request = Request {
                    version: 1,
                    source: bundle.source.clone(),
                    session: v.session.clone(),
                    seq,
                    op,
                    fixture,
                };
                match io.try_request(request) {
                    Ok(true) => {
                        seq += 1;
                        pending = None;
                        write_since.get_or_insert(now);
                        if op == Op::Prepare {
                            broker.report.prepare_released = true;
                        }
                        if matches!(op, Op::Cancel | Op::Finish) {
                            terminal_sent = true;
                        }
                    }
                    Ok(false) => {}
                    // Pending terminal operation remains latched.
                    Err(error) => {
                        note_error(&mut errors, error);
                        progress.mark_uncertain();
                        cancelled = true;
                        pending = None;
                        write_failed = true;
                        io.close_input();
                    }
                }
            }
            io.close_after_terminal(terminal_sent, broker.report.process_signaled);
            if host.is_none() {
                host = Some(io.poll_with_budget(&mut 0));
            }
        }
        if let Some(host) = host {
            broker.report.host_io = Some(host.clone());
            if broker.report.exit_event_continued && broker.report.process_signaled && host.joined()
            {
                broker.retire(&host);
                let known_pre_start =
                    !v.started && host.clean() && broker.report.local_handles_retired;
                let successful = !progress.sticky_uncertain
                    && broker.report.clean_success()
                    && v.finish(host.clean(), broker.report.exit_code == Some(0), cancelled);
                let (proposed, ownership) =
                    if !progress.sticky_uncertain && (successful || known_pre_start) {
                        native_drain::complete(guard);
                        (
                            if known_pre_start {
                                Outcome::NotStarted
                            } else if cancelled {
                                Outcome::Cancelled
                            } else {
                                Outcome::Completed
                            },
                            OwnershipStatus::Retired,
                        )
                    } else {
                        note_error(
                            &mut errors,
                            "uncertain cleanup; paired recovery fence retained".into(),
                        );
                        drop(guard);
                        (Outcome::Uncertain, OwnershipStatus::RecoveryFenced)
                    };
                errors.extend(broker.report.errors.clone());
                errors.extend(host.errors);
                let completion =
                    progress.snapshot(&v, proposed, errors, broker.report.clone(), ownership);
                updates.send_replace(Arc::new(completion));
                return;
            }
        }
        if progress.sticky_uncertain {
            v.failed = true;
        }
        updates.send_replace(Arc::new(progress.snapshot(
            &v,
            Outcome::Pending,
            errors.clone(),
            broker.report.clone(),
            OwnershipStatus::Active,
        )));
    }
}
#[cfg(test)]
mod launch_tests;
#[cfg(test)]
mod native_tests;
#[cfg(test)]
mod tests;
