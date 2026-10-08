//! Concrete writer/guard tests and six explicitly opted-in harmless native launches.
use super::host_io::{HostIo, IoReport};
use super::image::{ImageIdentity, RetainedImage};
use super::launch::{LaunchFault, LaunchReport, LaunchSpec, OwnedBroker};
use super::*;
use coding_tools_cloud_agent::work::WorkDrain;
use serde_json::{json, Value};
use std::os::windows::fs::MetadataExt;
use std::path::Path;
use std::sync::{Condvar, Mutex};
use std::time::{Duration, Instant};

fn paired() -> (
    tempfile::TempDir,
    ToolContext,
    WorkDrain,
    Option<native_drain::NativeGuard>,
) {
    let root = tempfile::tempdir().unwrap();
    let workspace = root.path().join("workspace");
    let harness = root.path().join("harness");
    std::fs::create_dir(&workspace).unwrap();
    std::fs::create_dir(&harness).unwrap();
    let mut ctx = ToolContext::for_test(workspace, harness).unwrap();
    let cloud = WorkDrain::new();
    let mut parent_cloud = cloud.register().unwrap();
    let mut parent_root = ctx.root_work.as_ref().unwrap().register().unwrap();
    parent_cloud.begin().unwrap();
    parent_root.begin().unwrap();
    ctx.native_work = Some(parent_cloud.scope());
    ctx.root_scope = Some(parent_root.scope());
    let mut guard = native_drain::child(&ctx).unwrap();
    native_drain::begin(&mut guard).unwrap();
    parent_cloud.complete();
    parent_root.complete();
    cloud.seal();
    (root, ctx, cloud, guard)
}

#[test]
fn launch_boundary_errors_preserve_owned_effects() {
    for entered in [false, true] {
        let (root, ctx, cloud, guard) = paired();
        let pin = root.path().join("retained.dat");
        std::fs::write(&pin, b"not an executable").unwrap();
        let hash = format!("{:x}", Sha256::digest(b"not an executable"));
        let image = RetainedImage::open(&pin, &hash).unwrap();
        let spec = LaunchSpec {
            application: if entered {
                root.path().join("absent.exe")
            } else {
                root.path().join("invalid\0.exe")
            },
            cwd: root.path().into(),
            session_root: root.path().into(),
        };
        let mut owner = OwnedBroker::create(&spec, image);
        assert_eq!(owner.report.create_call_entered, entered);
        assert_eq!(owner.report.create_call_returned, entered);
        assert!(!owner.report.child_created && !owner.report.admitted());
        assert!(!owner.report.no_child_proven());
        assert!(owner.retire(&IoReport::default()));
        assert!(owner.report.no_child_proven() && owner.report.pin_retired);
        assert!(owner.report.host_io.is_none(), "no workers were started");
        assert!(!owner.report.errors.is_empty());
        assert!(!owner.report.prepare_released && !owner.report.start_attempted);
        native_drain::complete(guard);
        assert_eq!(cloud.status().outstanding, 0);
        assert!(!cloud.status().unconfirmed);
        assert!(ctx.root_work.as_ref().unwrap().restore().is_ok());
    }
    for returned in [false, true] {
        let (_root, ctx, cloud, guard) = paired();
        let report = LaunchReport {
            create_call_entered: true,
            create_call_returned: returned,
            create_result_consistent: false,
            pid: u32::from(returned),
            local_handles_retired: true,
            ..Default::default()
        };
        assert!(
            !report.no_child_proven(),
            "in-flight/partial result is unknown"
        );
        assert!(!report.admitted());
        drop(guard); // Real running guard loss persists both recovery fences.
        assert!(cloud.status().unconfirmed);
        assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
    }
    let v = Validator::new("a".repeat(40), uuid::Uuid::new_v4().to_string());
    let latch = Arc::new((Mutex::new(false), Condvar::new()));
    let mut io = HostIo::test_writer(latch.clone());
    for failure in ["null hFile", "identity query", "hash query", "first Continue"] {
        let report = LaunchReport {
            child_created: true,
            create_event: true,
            image_hfile_present: failure != "null hFile",
            identity_match: failure == "first Continue",
            image_handle_closed: true,
            pre_admission_empty: true,
            errors: vec![failure.into()],
            ..Default::default()
        };
        assert!(!report.admitted() && !report.clean_success());
        if report.may_prepare() {
            io.try_request(request(&v, 0, Op::Prepare)).unwrap();
        }
        assert!(io.idle(), "failed gate released Prepare to actual writer");
        assert!(!report.prepare_released && !report.start_attempted);
    }
    *latch.0.lock().unwrap() = true;
    latch.1.notify_all();
    io.close_input();
    let deadline = Instant::now() + Duration::from_secs(5);
    while !io.poll().writer_joined {
        assert!(Instant::now() < deadline);
        std::thread::yield_now();
    }
    let neutral = v.snapshot(Outcome::Pending, vec![]);
    assert!(neutral.launch.is_none());
    assert_eq!(neutral.ownership, OwnershipStatus::Unobserved);
}

fn request(v: &Validator, seq: u64, op: Op) -> Request {
    Request {
        version: 1,
        source: v.source.clone(),
        session: v.session.clone(),
        seq,
        op,
        fixture: Fixture::Runtimes,
    }
}

#[tokio::test]
async fn blocked_writer_and_cancel_leave_owner_responsive() {
    for end in [Ok(()), Err("reader failed before cleanup".into())] {
        let (_root, ctx, cloud, guard) = paired();
        let v = Validator::new("a".repeat(40), uuid::Uuid::new_v4().to_string());
        let mut progress = OwnerProgress::new();
        let report = LaunchReport::default();
        let initial = progress.snapshot(
            &v,
            Outcome::Pending,
            vec![],
            report.clone(),
            OwnershipStatus::Active,
        );
        let (updates, rx) = watch::channel(Arc::new(initial));
        let (control, commands) = mpsc::channel();
        let session = WindowsVmSession {
            control,
            completion: CompletionObserver { rx },
        };
        let observer = session.observer();
        let latch = Arc::new((Mutex::new(false), Condvar::new()));
        let mut io = HostIo::test_writer(latch.clone());
        assert!(io.try_request(request(&v, 0, Op::Prepare)).unwrap());
        let deadline = Instant::now() + Duration::from_secs(5);
        while !io.try_request(request(&v, 1, Op::Start)).unwrap() {
            assert!(
                Instant::now() < deadline,
                "writer did not take first request"
            );
            tokio::task::yield_now().await;
        }
        assert!(!io.try_request(request(&v, 2, Op::Cancel)).unwrap());
        assert!(!io.poll().writer_joined && !io.idle());
        assert!(
            tokio::time::timeout(Duration::from_millis(20), observer.wait())
                .await
                .is_err()
        );
        assert!(matches!(
            commands.try_recv(),
            Err(mpsc::TryRecvError::Empty)
        ));
        assert_eq!(cloud.status().outstanding, 1);
        drop(session);
        assert!(matches!(
            commands.try_recv(),
            Ok(Message::Control(Op::Cancel))
        ));
        let mut errors = Vec::new();
        assert!(progress.on_end(end, false, &mut errors));
        assert!(!errors.is_empty());
        io.close_after_terminal(false, false);
        assert!(!io.try_request(request(&v, 2, Op::Cancel)).unwrap());
        updates.send_replace(Arc::new(progress.snapshot(
            &v,
            Outcome::Pending,
            errors.clone(),
            report.clone(),
            OwnershipStatus::Active,
        )));
        let uncertain = observer.wait().await.unwrap();
        assert_eq!(uncertain.outcome, Outcome::Uncertain);
        assert_eq!(uncertain.ownership, OwnershipStatus::Active);
        assert_eq!(cloud.status().outstanding, 1);
        assert!(!cloud.status().unconfirmed);
        assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
        *latch.0.lock().unwrap() = true;
        latch.1.notify_all();
        let deadline = Instant::now() + Duration::from_secs(5);
        while !io.try_request(request(&v, 2, Op::Cancel)).unwrap() {
            assert!(Instant::now() < deadline, "latched Cancel was lost");
            io.poll();
            tokio::task::yield_now().await;
        }
        io.close_after_terminal(true, false);
        let joined = loop {
            let actual = io.poll();
            if actual.writer_joined {
                break actual;
            }
            assert!(
                Instant::now() < deadline,
                "writer did not finish after release"
            );
            tokio::task::yield_now().await;
        };
        assert!(joined.stdin_closed && joined.errors.is_empty());
        assert!(
            !joined.stdout_joined && !joined.stderr_joined,
            "no fabricated readers"
        );
        assert!(!joined.stdout_eof && !joined.stderr_eof);
        drop(guard);
        updates.send_replace(Arc::new(progress.snapshot(
            &v,
            Outcome::Completed,
            errors,
            report,
            OwnershipStatus::RecoveryFenced,
        )));
        assert_eq!(observer.snapshot().outcome, Outcome::Uncertain);
        assert_eq!(observer.snapshot().ownership, OwnershipStatus::RecoveryFenced);
        assert!(cloud.status().unconfirmed);
        assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
    }
}

struct Case {
    root: PathBuf,
    dir: PathBuf,
    manifest: Value,
    id: &'static str,
}
impl Case {
    fn new(id: &'static str) -> Self {
        assert_eq!(std::env::var("CTM_VM_LAUNCH_NATIVE").as_deref(), Ok("1"));
        let root =
            PathBuf::from(std::env::var_os("CTM_VM_SESSION_ROOT").unwrap()).join("launch");
        assert!(root.is_absolute());
        let manifest: Value =
            serde_json::from_slice(&std::fs::read(root.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(
            manifest["source"].as_str(),
            std::env::var("GITHUB_SHA").ok().as_deref()
        );
        let dir = root.join("cases").join(id);
        if id != "native_launch_junction_redirect_rejects" {
            std::fs::create_dir(&dir).unwrap();
            std::fs::create_dir(dir.join("cwd")).unwrap();
        }
        assert!(!dir.join("cwd/marker.txt").try_exists().unwrap());
        Self {
            root,
            dir,
            manifest,
            id,
        }
    }
    fn image(&self, name: &str) -> PathBuf {
        self.root.join("trusted").join(format!("{name}.exe"))
    }
    fn pin(&self, path: &Path, name: &str) -> RetainedImage {
        RetainedImage::open(path, self.manifest[name]["sha256"].as_str().unwrap()).unwrap()
    }
    fn identity(&self, path: &Path, name: &str) -> ImageIdentity {
        let mut pin = self.pin(path, name);
        let identity = pin.identity.clone();
        pin.close().unwrap();
        identity
    }
    fn good(&self, fault: Option<LaunchFault>) -> LaunchReport {
        let application = self.image("good");
        self.run(self.pin(&application, "good"), application, fault)
    }
    fn run(
        &self,
        image: RetainedImage,
        application: PathBuf,
        fault: Option<LaunchFault>,
    ) -> LaunchReport {
        let (_root, ctx, cloud, guard) = paired();
        let spec = LaunchSpec {
            application,
            cwd: self.dir.join("cwd"),
            session_root: self.root.clone(),
        };
        let mut owner = OwnedBroker::create(&spec, image);
        if let Some(fault) = fault {
            owner.set_fault(fault);
        }
        let mut io = None;
        let deadline = Instant::now() + Duration::from_secs(30);
        let mut timed_out = false;
        let retired = loop {
            owner.pump(true);
            if io.is_none() {
                io = owner.take_pipes().map(HostIo::raw);
            }
            owner.poll_process();
            let actual = io.as_mut().map(HostIo::poll).unwrap_or_default();
            if owner.retire(&actual) {
                break true;
            }
            if !timed_out && Instant::now() >= deadline {
                timed_out = true;
                let recorded = save(&format!("{}-timeout", self.id), json!({
                    "case":self.id, "source":self.manifest["source"], "launch":owner.report, "host_io":actual,
                    "retired":false, "ownership":"Active", "outcome":"Uncertain"
                }));
                if let Err(error) = recorded {
                    eprintln!("unresolved launch evidence write failed: {error}");
                }
            }
            if timed_out {
                owner.terminate_before_start();
            }
        };
        let report = owner.report.clone();
        let marker = std::fs::read(self.dir.join("cwd/marker.txt"));
        let marker_absent =
            matches!(&marker, Err(error) if error.kind() == std::io::ErrorKind::NotFound);
        let clean = !timed_out && (report.clean_success() || report.rejection_retired());
        if retired && clean {
            native_drain::complete(guard);
        } else {
            drop(guard);
        }
        let value = json!({"case":self.id, "source":self.manifest["source"], "launch":report,
            "retired":retired, "cooperative_timeout":timed_out, "marker_absent_after_retirement":marker_absent,
            "marker":marker.as_ref().ok(), "paired_fences_drained":!cloud.status().unconfirmed && cloud.status().outstanding==0,
            "paired_recovery_fenced":cloud.status().unconfirmed,
            "production_admission":false, "production_launch_authority":false, "workspace_integration":false,
            "network_denial_proven":false, "general_dll_authority":false,
            "descendant_containment_by_debugger":false, "hard_syscall_deadline":false});
        save(self.id, value).unwrap();
        assert!(retired && clean, "{report:?}");
        assert!(report.create_call_entered && report.create_call_returned && report.child_created);
        assert!(report.create_result_consistent && report.pid != 0 && report.tid != 0);
        assert!(report.create_event && report.image_hfile_present && report.image_handle_closed);
        assert!(report.exit_event_continued && report.process_signaled && report.pin_retired);
        assert!(report.host_io.as_ref().unwrap().clean());
        assert!(!report.prepare_released && !report.start_attempted);
        assert_eq!(cloud.status().outstanding, 0);
        assert!(!cloud.status().unconfirmed);
        assert!(ctx.root_work.as_ref().unwrap().restore().is_ok());
        if report.admitted() {
            assert_eq!(marker.unwrap(), b"A\n");
        } else {
            assert!(
                marker_absent,
                "checked after actual process/IO retirement"
            );
            let io = report.host_io.as_ref().unwrap();
            assert_eq!((io.stdout_bytes, io.stderr_bytes), (0, 0));
            assert!(io.raw_stdout.is_empty() && io.raw_stderr.is_empty());
        }
        report
    }
}

fn save(name: &str, value: Value) -> std::io::Result<()> {
    let path = PathBuf::from(std::env::var_os("CTM_VM_SESSION_EVIDENCE").unwrap())
        .join(format!("{name}.json"));
    let mut output = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    let written = serde_json::to_writer_pretty(&mut output, &value)
        .map_err(std::io::Error::other)
        .and_then(|()| output.sync_all());
    let closed = image::close_file(output).map_err(std::io::Error::other);
    written.and(closed)
}

#[test]
#[ignore = "requires reviewed harmless fixture build and explicit native opt-in"]
fn native_launch_matching_image_retires() {
    let case = Case::new("native_launch_matching_image_retires");
    let report = case.good(None);
    assert!(report.clean_success() && report.pre_admission_empty);
    assert_eq!(report.retained, report.observed);
    assert_eq!(report.exit_code, Some(0));
    let io = report.host_io.unwrap();
    assert_eq!(io.raw_stdout, b"A\n");
    assert_eq!(io.raw_stderr, b"E\n");
}

#[test]
#[ignore = "requires reviewed harmless fixture build and explicit native opt-in"]
fn native_launch_wrong_image_rejects() {
    let case = Case::new("native_launch_wrong_image_rejects");
    let selected = case.identity(&case.image("bad"), "bad");
    let report = case.run(
        case.pin(&case.image("good"), "good"),
        case.image("bad"),
        None,
    );
    assert_eq!(report.observed.as_ref(), Some(&selected));
    assert_ne!(report.retained.as_ref(), Some(&selected));
    assert!(!report.identity_match && !report.admitted() && report.rejection_retired());
    assert!(report.pre_admission_empty && !report.errors.is_empty());
}

#[test]
#[ignore = "requires reviewed harmless fixture build and explicit native opt-in"]
fn native_launch_same_bytes_new_id_rejects() {
    let case = Case::new("native_launch_same_bytes_new_id_rejects");
    let pin = case.pin(&case.image("good"), "good");
    let selected = case.identity(&case.image("same"), "good");
    assert_eq!(pin.identity.sha256, selected.sha256);
    assert_eq!(pin.identity.size, selected.size);
    assert_ne!(
        (pin.identity.volume, pin.identity.file_id),
        (selected.volume, selected.file_id)
    );
    let report = case.run(pin, case.image("same"), None);
    assert_eq!(report.observed.as_ref(), Some(&selected));
    assert!(!report.identity_match && report.rejection_retired() && report.pre_admission_empty);
}

#[test]
#[ignore = "requires prepared owned junctions and explicit native opt-in"]
fn native_launch_junction_redirect_rejects() {
    let case = Case::new("native_launch_junction_redirect_rejects");
    for name in ["active", "spare"] {
        let attributes = std::fs::symlink_metadata(case.dir.join(name))
            .unwrap()
            .file_attributes();
        assert_ne!(attributes & 0x400, 0);
    }
    let application = case.dir.join("active/image.exe");
    let pin = case.pin(&application, "good");
    let selected = case.identity(&case.dir.join("spare/image.exe"), "bad");
    std::fs::rename(case.dir.join("active"), case.dir.join("displaced")).unwrap();
    std::fs::rename(case.dir.join("spare"), case.dir.join("active")).unwrap();
    assert_eq!(
        case.identity(&application, "bad"),
        selected,
        "real redirection required"
    );
    let report = case.run(pin, application, None);
    assert_eq!(report.observed.as_ref(), Some(&selected));
    assert_ne!(report.retained, report.observed);
    assert!(report.rejection_retired() && report.pre_admission_empty);
}

#[test]
#[ignore = "requires reviewed harmless fixture build and explicit native opt-in"]
fn native_launch_cancel_before_continue() {
    let case = Case::new("native_launch_cancel_before_continue");
    let report = case.good(Some(LaunchFault::CancelAtCreate));
    assert!(report.identity_match && report.pre_admission_empty);
    assert_eq!(report.retained, report.observed);
    assert!(!report.first_continue_succeeded && report.rejection_retired());
}

#[test]
#[ignore = "requires exact closed-pipe observation and explicit native opt-in"]
fn native_launch_wait_fault_preserves_raw_evidence() {
    let case = Case::new("native_launch_wait_fault_preserves_raw_evidence");
    let report = case.good(Some(LaunchFault::WaitBeforeCreate));
    assert!(report.native_errors.iter().any(|(_, code)| *code == 31));
    assert_eq!(report.stdout_peek_error, Some(109));
    assert_eq!(report.stderr_peek_error, Some(109));
    assert!(!report.pre_admission_empty && !report.admitted());
    assert!(report.termination_requested && report.rejection_retired());
    assert!(!report.errors.is_empty());
}
