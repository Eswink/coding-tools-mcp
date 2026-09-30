//! Opt-in real OS credential + fresh-process root ledger verification.
//! All paths, encrypted documents and credentials are owned disposable fixtures.
use super::*;
use crate::{harness::Harness, tools::root_work::RootWorkTracker};
use sha2::{Digest, Sha256};

#[test]
fn native_root_cross_process_crash_fences() {
    const ROOT: &str = "CTM_NATIVE_ROOT_RESTART_FIXTURE";
    const ROLE: &str = "CTM_NATIVE_ROOT_RESTART_ROLE";
    const TEST: &str =
        "data::secure_file::native_tests::root_restart::native_root_cross_process_crash_fences";
    if let Some(root) = std::env::var_os(ROOT) {
        let root = PathBuf::from(root).canonicalize().unwrap();
        match std::env::var(ROLE).unwrap().as_str() {
            "clean" => {
                let tracker = RootWorkTracker::for_workspace(&root).unwrap();
                let mut work = tracker.register().unwrap();
                work.begin().unwrap();
                fs::write(root.join("effect.txt"), "one").unwrap();
                work.complete();
            }
            "reopen-clean" => {
                let tracker = RootWorkTracker::for_workspace(&root).unwrap();
                let mut work = tracker.register().unwrap();
                work.begin().unwrap();
                assert_eq!(fs::read_to_string(root.join("effect.txt")).unwrap(), "one");
                work.complete();
            }
            "busy-crash" => {
                let tracker = RootWorkTracker::for_workspace(&root).unwrap();
                let mut work = tracker.register().unwrap();
                work.begin().unwrap();
                fs::write(root.join("effect.txt"), "one").unwrap();
                // Simulate abrupt process loss: no Rust Drop may publish Clean.
                std::process::exit(0);
            }
            "restore-crash" => {
                let tracker = RootWorkTracker::for_workspace(&root).unwrap();
                let mut restore = tracker.restore().unwrap();
                restore.before_write().unwrap();
                fs::write(root.join("effect.txt"), "one").unwrap();
                std::process::exit(0);
            }
            "denied" => {
                assert!(RootWorkTracker::for_workspace(&root).is_err());
                assert!(RootWorkTracker::enroll_managed(&root).is_err());
                assert_eq!(fs::read_to_string(root.join("effect.txt")).unwrap(), "one");
            }
            _ => panic!("unknown disposable fixture role"),
        }
        return;
    }

    struct Cleanup {
        namespace: PathBuf,
        key: Option<String>,
    }
    impl Drop for Cleanup {
        fn drop(&mut self) {
            // Only a namespace proved absent before this fixture is removed.
            // Never reset any existing production or another test's ledger.
            if let Some(key) = &self.key {
                if let Ok(entry) = keyring::Entry::new(SERVICE, key) {
                    let _ = entry.delete_credential();
                }
            }
            let _ = fs::remove_dir_all(&self.namespace);
        }
    }
    for role in ["clean", "busy-crash", "restore-crash"] {
        let root = tempfile::tempdir().unwrap();
        let workspace = root.path().join("workspace");
        fs::create_dir(&workspace).unwrap();
        let workspace = workspace.canonicalize().unwrap();
        let binding = format!(
            "{:x}",
            Sha256::digest(workspace.to_string_lossy().as_bytes())
        );
        let namespace = Harness::default_root()
            .unwrap()
            .join("native-root-work-v1")
            .join(binding);
        assert!(
            !namespace.exists(),
            "fixture must never adopt an existing root ledger"
        );
        let mut cleanup = Cleanup {
            namespace: namespace.clone(),
            key: None,
        };
        let child = |role: &str| {
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", TEST, "--nocapture"])
                .env(ROOT, &workspace)
                .env(ROLE, role)
                .output()
                .unwrap();
            // No credential values or child output are exported by this fixture.
            assert!(
                output.status.success(),
                "native root child role failed: {role}"
            );
            assert!(
                String::from_utf8_lossy(&output.stdout).contains("running 1 test"),
                "native root child must execute its exact fixture, not an empty filter"
            );
        };
        child(role);
        let document = namespace.join("auth.json");
        cleanup.key = Some(codec::key_id_for_path(&document).unwrap());
        let ciphertext = fs::read(&document).unwrap();
        let (plaintext, encrypted) = Vault::new(&NativeKeyStore).read(&document).unwrap();
        assert!(encrypted, "root ledger must use actual native encryption");
        let value: serde_json::Value = serde_json::from_str(&plaintext).unwrap();
        assert_eq!(
            value["phase"],
            match role {
                "clean" => "clean",
                "busy-crash" => "busy",
                _ => "restore",
            }
        );
        assert!(!String::from_utf8_lossy(&ciphertext).contains("\"phase\""));
        child(if role == "clean" {
            "reopen-clean"
        } else {
            "denied"
        });
        if role != "clean" {
            assert_eq!(
                fs::read(&document).unwrap(),
                ciphertext,
                "denial must preserve the crash fence"
            );
        } else {
            // Loss of the real OS credential is also a fence, not re-enrollment.
            keyring::Entry::new(SERVICE, cleanup.key.as_ref().unwrap())
                .unwrap()
                .delete_credential()
                .unwrap();
            let before = fs::read(&document).unwrap();
            child("denied");
            assert_eq!(fs::read(&document).unwrap(), before);
        }
        assert_eq!(
            fs::read_to_string(workspace.join("effect.txt")).unwrap(),
            "one"
        );
    }
}
