use super::*;
impl SnapshotStore {
    /// Host must retain the real native drain/admission lease for this whole call.
    /// Callback is an in-process proof check, never an IPC boolean or model token.
    pub(crate) fn restore(
        &self,
        target: &impl TargetAuthority,
        plan: &RestorePlan,
        mut native_lease: impl FnMut(&RestorePlan) -> Result<()>,
    ) -> Result<RestoreReport> {
        let _lock = self.directory.lock()?;
        self.ready()?;
        self.validate_plan(target, plan)?;
        native_lease(plan)?;
        let root = self.target(target)?;
        let current = root.scan(true)?;
        if entries_digest(&current.entries)? != plan.current_digest {
            return Err(SnapshotError::Changed);
        }
        let (manifest, desired) = self.load(target, &plan.snapshot_id)?;
        if manifest.digest != plan.snapshot_digest {
            return Err(SnapshotError::Corrupt);
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        let transaction = self.directory.mkdir(&format!("transaction-{id}"))?;
        let stage = transaction.mkdir("stage")?;
        let backup = transaction.mkdir("backup")?;
        stage.materialize(&desired.entries, &desired.data)?;
        transaction.write_new(
            "plan.json",
            &serde_json::to_vec(plan).map_err(|_| SnapshotError::Corrupt)?,
            0o600,
        )?;
        // Durable intent exists before any original is displaced. Any failure keeps it locked.
        transaction.write_new("prepared", plan.approval_digest.as_bytes(), 0o600)?;
        let run = (|| -> Result<()> {
            let mut expected = current.entries.clone();
            let mut displaced = Vec::new();
            let names: std::collections::BTreeSet<String> = current
                .entries
                .iter()
                .chain(&desired.entries)
                .map(|e| e.path.split('/').next().unwrap().to_owned())
                .collect();
            for name in names {
                native_lease(plan)?;
                self.validate_plan(target, plan)?;
                if root.scan(true)?.entries != expected {
                    return Err(SnapshotError::Changed);
                }
                let prefix = format!("{name}/");
                let old: Vec<_> = current
                    .entries
                    .iter()
                    .filter(|e| e.path == name || e.path.starts_with(&prefix))
                    .cloned()
                    .collect();
                let new: Vec<_> = desired
                    .entries
                    .iter()
                    .filter(|e| e.path == name || e.path.starts_with(&prefix))
                    .cloned()
                    .collect();
                if old == new {
                    continue;
                }
                if !old.is_empty() {
                    root.move_new(&name, &backup, &name)?;
                    displaced.extend(old);
                    displaced.sort_by(|a, b| a.path.cmp(&b.path));
                    if backup.scan(false)?.entries != displaced {
                        return Err(SnapshotError::Changed);
                    }
                }
                // A concurrently recreated destination is never replaced by this move.
                if !new.is_empty() {
                    stage.move_new(&name, &root, &name)?;
                    root.apply_directory_modes(&new)?;
                }
                expected.retain(|e| e.path != name && !e.path.starts_with(&prefix));
                expected.extend(new);
                expected.sort_by(|a, b| a.path.cmp(&b.path));
                transaction.write_new(
                    &format!("step-{}", hash(name.as_bytes())),
                    b"applied",
                    0o600,
                )?;
            }
            native_lease(plan)?;
            self.target(target)?;
            if root.scan(true)?.entries != desired.entries
                || backup.scan(false)?.entries != displaced
            {
                return Err(SnapshotError::Changed);
            }
            transaction.write_new("complete", manifest.digest.as_bytes(), 0o600)?;
            Ok(())
        })();
        if run.is_err() {
            return Err(SnapshotError::RecoveryRequired);
        }
        Ok(RestoreReport {
            transaction_id: id,
            restored_digest: manifest.digest,
            retained_backup: true,
        })
    }
}
