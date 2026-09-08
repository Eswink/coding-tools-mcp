use std::sync::Mutex;

use crate::error::{AppError, AppResult};
use crate::settings::AppSettings;
#[cfg(not(test))]
use crate::workspace::legacy_import::import_legacy_profiles_if_empty;
use crate::workspace::WorkspaceProfile;

use super::migrate::{data_file_path, load_or_migrate, maybe_backup_legacy_files, save};
use super::model::AppData;

static DATA_FILE_LOCK: Mutex<()> = Mutex::new(());

const SHARED_KEYS: &[&str] = &[
    "oauth_client_id",
    "bearer_token",
    "oauth_client_secret",
    "oauth_password",
    "oauth_token_secret",
    "actions_api_key",
    "actions_oauth_client_secret",
    "actions_oauth_password",
    "actions_oauth_token_secret",
];

#[derive(Debug)]
pub struct DataStore {
    data: AppData,
    baseline: AppData,
}

impl DataStore {
    pub fn load() -> AppResult<Self> {
        let _guard = lock_data_file()?;
        let path = data_file_path()?;
        let existed_before = path.exists();
        let mut data = load_or_migrate()?;
        #[cfg(not(test))]
        let imported = import_legacy_profiles_if_empty(&mut data)?;
        #[cfg(test)]
        let imported = { let _ = &mut data; 0 };
        let store = Self { baseline: data.clone(), data };
        if !existed_before || imported > 0 {
            store.persist_unlocked()?;
        }
        maybe_backup_legacy_files(&path)?;
        Ok(store)
    }

    pub fn read_file<R>(f: impl FnOnce(&AppData) -> AppResult<R>) -> AppResult<R> {
        let _guard = lock_data_file()?;
        let data = load_or_migrate()?;
        f(&data)
    }

    pub fn update_file<R>(f: impl FnOnce(&mut AppData) -> AppResult<R>) -> AppResult<R> {
        let _guard = lock_data_file()?;
        let mut data = load_or_migrate()?;
        let result = f(&mut data)?;
        save(&data)?;
        Ok(result)
    }

    pub fn data(&self) -> &AppData {
        &self.data
    }

    /// Refresh read snapshots; save still checks for a writer racing after this read.
    pub fn refresh(&mut self) -> AppResult<()> {
        let _guard = lock_data_file()?;
        let current = load_or_migrate()?;
        self.baseline = current.clone();
        self.data = current;
        Ok(())
    }

    pub fn save(&mut self) -> AppResult<()> {
        let result = (|| {
            let _guard = lock_data_file()?;
            let current = load_or_migrate()?;
            self.commit_snapshot(current, save)
        })();
        if result.is_err() {
            // Failed mutations must not remain visible to subsequent UI reads.
            self.data = self.baseline.clone();
        }
        result
    }

    fn commit_snapshot(
        &mut self,
        current: AppData,
        persist: impl FnOnce(&AppData) -> AppResult<()>,
    ) -> AppResult<()> {
        let merged = merge_snapshot_value(
            Some(&serde_json::to_value(&self.baseline)?),
            Some(&serde_json::to_value(&self.data)?),
            Some(&serde_json::to_value(&current)?),
        );
        let candidate: AppData = match merged {
            Ok(Some(value)) => serde_json::from_value(value)?,
            _ => {
                self.data = current.clone();
                self.baseline = current;
                return Err(AppError::Message("同一配置项已被其他操作更新，本次修改未写入，请重试。".into()));
            }
        };
        let candidate = super::migrate::migrate_data(candidate)?;
        if let Err(error) = persist(&candidate) {
            self.data = self.baseline.clone();
            return Err(error);
        }
        self.baseline = candidate.clone();
        self.data = candidate;
        Ok(())
    }

    fn persist_unlocked(&self) -> AppResult<()> {
        save(&self.data)
    }

    pub fn settings(&self) -> AppSettings {
        AppSettings::from_data(&self.data)
    }

    pub fn update_settings(&mut self, settings: AppSettings) -> AppResult<()> {
        settings.apply_to(&mut self.data);
        self.save()
    }

    pub fn list(&self) -> &[WorkspaceProfile] {
        &self.data.profiles
    }

    pub fn get(&self, id: &str) -> Option<&WorkspaceProfile> {
        self.data.profiles.iter().find(|profile| profile.id == id)
    }

    pub fn add(&mut self, profile: WorkspaceProfile) -> AppResult<()> {
        self.data.profiles.push(profile);
        self.save()
    }

    pub fn update(&mut self, profile: WorkspaceProfile) -> AppResult<()> {
        let Some(index) = self
            .data
            .profiles
            .iter()
            .position(|item| item.id == profile.id)
        else {
            return Err(AppError::Message(format!(
                "workspace not found: {}",
                profile.id
            )));
        };
        self.data.profiles[index] = profile;
        self.save()
    }

    pub fn remove(&mut self, id: &str) -> AppResult<Option<WorkspaceProfile>> {
        let Some(index) = self.data.profiles.iter().position(|item| item.id == id) else {
            return Ok(None);
        };
        let removed = self.data.profiles.remove(index);
        self.data.workspace_secrets.remove(id);
        self.save()?;
        Ok(Some(removed))
    }

    pub fn init_workspace_secrets(&mut self, profile_id: &str) -> AppResult<()> {
        // One snapshot commit; retries preserve every already initialized secret.
        if seed_workspace_secrets(&mut self.data, profile_id) { self.save()?; }
        Ok(())
    }

    pub fn init_shared_secrets(&mut self) -> AppResult<()> {
        let mut changed = false;
        for key in SHARED_KEYS {
            if !self.data.shared_secrets.contains_key(*key) {
                self.data
                    .shared_secrets
                    .insert(key.to_string(), shared_value_for_key(key));
                changed = true;
            }
        }
        if changed {
            self.save()?;
        }
        Ok(())
    }

    pub fn get_workspace_secret(&self, profile_id: &str, key: &str) -> AppResult<Option<String>> {
        Ok(self
            .data
            .workspace_secrets
            .get(profile_id)
            .and_then(|secrets| secrets.get(key))
            .filter(|value| !value.is_empty())
            .cloned())
    }

    pub fn set_workspace_secret(
        &mut self,
        profile_id: &str,
        key: &str,
        value: &str,
    ) -> AppResult<()> {
        self.data
            .workspace_secrets
            .entry(profile_id.to_string())
            .or_default()
            .insert(key.to_string(), value.to_string());
        self.save()
    }

    pub fn regenerate_workspace_secret(&mut self, profile_id: &str, key: &str) -> AppResult<String> {
        let value = shared_value_for_key(key);
        self.set_workspace_secret(profile_id, key, &value)?;
        Ok(value)
    }

    pub fn remove_workspace_secrets(&mut self, profile_id: &str) -> AppResult<()> {
        self.data.workspace_secrets.remove(profile_id);
        self.save()
    }

    pub fn get_shared_secret(&self, key: &str) -> Option<String> {
        self.data.shared_secrets.get(key).cloned()
    }

    pub fn set_shared_secret(&mut self, key: &str, value: &str) -> AppResult<()> {
        self.data
            .shared_secrets
            .insert(key.to_string(), value.to_string());
        self.save()
    }

    pub fn regenerate_shared_secret(&mut self, key: &str) -> AppResult<String> {
        let value = random_secret();
        self.set_shared_secret(key, &value)?;
        Ok(value)
    }

    pub fn get_app_secret(&self, scope: &str, item_id: &str) -> Option<String> {
        self.data
            .app_secrets
            .get(scope)
            .and_then(|items| items.get(item_id))
            .filter(|value| !value.is_empty())
            .cloned()
    }

    pub fn set_app_secret(&mut self, scope: &str, item_id: &str, value: &str) -> AppResult<()> {
        self.data
            .app_secrets
            .entry(scope.to_string())
            .or_default()
            .insert(item_id.to_string(), value.to_string());
        self.save()
    }

    pub fn delete_app_secret(&mut self, scope: &str, item_id: &str) -> AppResult<()> {
        if let Some(items) = self.data.app_secrets.get_mut(scope) {
            items.remove(item_id);
            if items.is_empty() {
                self.data.app_secrets.remove(scope);
            }
        }
        self.save()
    }

}

/// Three-way merge preserves unrelated concurrent updates. Arrays are atomic:
/// a conflicting workspace-list edit fails rather than guessing how to merge it.
fn merge_snapshot_value(
    base: Option<&serde_json::Value>,
    proposed: Option<&serde_json::Value>,
    current: Option<&serde_json::Value>,
) -> Result<Option<serde_json::Value>, ()> {
    use serde_json::{Map, Value};
    if proposed == base { return Ok(current.cloned()); }
    if current == base || current == proposed { return Ok(proposed.cloned()); }
    if let (Some(Value::Object(proposed)), Some(Value::Object(current))) = (proposed, current) {
        if base.is_some_and(|value| !value.is_object()) { return Err(()); }
        let base = base.and_then(Value::as_object);
        let mut keys = std::collections::BTreeSet::new();
        if let Some(base) = base { keys.extend(base.keys()); }
        keys.extend(proposed.keys());
        keys.extend(current.keys());
        let mut merged = Map::new();
        for key in keys {
            if let Some(value) = merge_snapshot_value(base.and_then(|value| value.get(key)), proposed.get(key), current.get(key))? {
                merged.insert(key.clone(), value);
            }
        }
        return Ok(Some(Value::Object(merged)));
    }
    Err(())
}

struct DataFileLock {
    // Release the OS lock before allowing another thread through this process.
    _file: super::config_lock::ConfigFileLock,
    _thread: std::sync::MutexGuard<'static, ()>,
}

fn lock_data_file() -> AppResult<DataFileLock> {
    let thread = DATA_FILE_LOCK.lock()
        .map_err(|_| AppError::Message("data file lock poisoned".into()))?;
    let path = data_file_path()?.with_file_name("profiles.lock");
    let file = super::config_lock::ConfigFileLock::acquire(&path, std::time::Duration::from_secs(3))?;
    Ok(DataFileLock { _file: file, _thread: thread })
}

fn seed_workspace_secrets(data: &mut AppData, profile_id: &str) -> bool {
    let secrets = data.workspace_secrets.entry(profile_id.into()).or_default();
    let mut changed = false;
    // MCP oauth_client_secret is optional (PKCE), so do not synthesize it.
    for key in ["oauth_password", "oauth_token_secret", "bearer_token", "actions_api_key",
        "actions_oauth_client_secret", "actions_oauth_password", "actions_oauth_token_secret"] {
        if let std::collections::hash_map::Entry::Vacant(entry) = secrets.entry(key.into()) {
            entry.insert(random_secret());
            changed = true;
        }
    }
    changed
}

fn random_secret() -> String {
    format!("{}{}", uuid::Uuid::new_v4(), uuid::Uuid::new_v4()).replace('-', "")
}

fn shared_value_for_key(key: &str) -> String {
    if key == "oauth_client_id" {
        format!("chatgpt-client-{}", &uuid::Uuid::new_v4().to_string()[..12])
    } else {
        random_secret()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workspace_secret_roundtrip() {
        let id = uuid::Uuid::new_v4().to_string().replace('-', "");
        let mut store = DataStore::load().expect("load");
        store
            .set_workspace_secret(&id, "oauth_client_secret", "roundtrip-secret")
            .expect("set");
        let loaded = store
            .get_workspace_secret(&id, "oauth_client_secret")
            .expect("get");
        assert_eq!(loaded.as_deref(), Some("roundtrip-secret"));
        store.remove_workspace_secrets(&id).expect("remove");
    }

    #[test]
    fn failed_persistence_restores_in_memory_state() {
        let baseline = AppData::default();
        let mut store = DataStore { data: baseline.clone(), baseline: baseline.clone() };
        store.data.last_workspace_id = "must-not-remain".into();
        assert!(store.commit_snapshot(baseline, |_| Err(AppError::Message("disk failure".into()))).is_err());
        assert!(store.data.last_workspace_id.is_empty());
    }

    #[test]
    fn stale_snapshot_does_not_overwrite_a_new_secret() {
        let mut baseline = AppData::default();
        baseline.shared_secrets.insert("oauth_token_secret".into(), "original".into());
        let mut store = DataStore { data: baseline.clone(), baseline: baseline.clone() };
        store.data.shared_secrets.insert("oauth_token_secret".into(), "conflicting-value".into());
        let mut latest = baseline;
        latest.shared_secrets.insert("oauth_token_secret".into(), "newer-value".into());
        let wrote = std::cell::Cell::new(false);
        assert!(store.commit_snapshot(latest, |_| { wrote.set(true); Ok(()) }).is_err());
        assert!(!wrote.get());
        assert_eq!(store.data.shared_secrets["oauth_token_secret"], "newer-value");
        assert!(store.data.last_workspace_id.is_empty());
    }

    #[test]
    fn unrelated_concurrent_secret_is_preserved_when_saving_workspace_selection() {
        let baseline = AppData::default();
        let mut store = DataStore { data: baseline.clone(), baseline: baseline.clone() };
        store.data.last_workspace_id = "selected".into();
        let mut latest = baseline;
        latest.shared_secrets.insert("oauth_token_secret".into(), "newer-value".into());
        store.commit_snapshot(latest, |candidate| {
            assert_eq!(candidate.last_workspace_id, "selected");
            assert_eq!(candidate.shared_secrets["oauth_token_secret"], "newer-value");
            Ok(())
        }).unwrap();
        assert_eq!(store.data.shared_secrets["oauth_token_secret"], "newer-value");
    }

    #[test]
    fn deletion_does_not_win_over_a_concurrent_secret_rotation() {
        let base = serde_json::json!({"key":"old"});
        let proposed = serde_json::json!({});
        let current = serde_json::json!({"key":"rotated"});
        assert!(merge_snapshot_value(Some(&base), Some(&proposed), Some(&current)).is_err());
    }

    #[test]
    fn divergent_array_edits_are_not_silently_combined() {
        let base = serde_json::json!([1]);
        let proposed = serde_json::json!([2]);
        let current = serde_json::json!([3]);
        assert!(merge_snapshot_value(Some(&base), Some(&proposed), Some(&current)).is_err());
    }

    #[test]
    fn successful_snapshot_commit_updates_the_next_comparison_baseline() {
        let baseline = AppData::default();
        let mut store = DataStore { data: baseline.clone(), baseline: baseline.clone() };
        store.data.last_workspace_id = "saved".into();
        store.commit_snapshot(baseline, |_| Ok(())).unwrap();
        assert_eq!(store.baseline.last_workspace_id, "saved");
        assert_eq!(store.data.last_workspace_id, "saved");
    }

    #[test]
    fn shared_oauth_client_id_uses_client_id_format() {
        let value = shared_value_for_key("oauth_client_id");
        assert!(value.starts_with("chatgpt-client-"));
        assert_eq!(value.len(), "chatgpt-client-".len() + 12);
    }
    #[test]
    fn workspace_initialization_is_idempotent_and_preserves_existing_tokens() {
        let mut data = AppData::default();
        data.workspace_secrets.entry("workspace".into()).or_default()
            .insert("bearer_token".into(), "existing-canary-v6".into());
        assert!(seed_workspace_secrets(&mut data, "workspace"));
        assert_eq!(data.workspace_secrets["workspace"].len(), 7);
        assert_eq!(data.workspace_secrets["workspace"]["bearer_token"], "existing-canary-v6");
        let before = data.workspace_secrets.clone();
        assert!(!seed_workspace_secrets(&mut data, "workspace"));
        assert_eq!(before, data.workspace_secrets);
        assert!(!data.workspace_secrets["workspace"].contains_key("oauth_client_secret"));
    }

    #[test]
    fn initializing_all_workspace_keys_rolls_back_as_one_snapshot_on_failure() {
        let baseline = AppData::default();
        let mut store = DataStore { data: baseline.clone(), baseline: baseline.clone() };
        seed_workspace_secrets(&mut store.data, "workspace");
        let writes = std::cell::Cell::new(0);
        assert!(store.commit_snapshot(baseline, |candidate| {
            writes.set(writes.get() + 1);
            assert_eq!(candidate.workspace_secrets["workspace"].len(), 7);
            Err(AppError::Message("simulated disk failure".into()))
        }).is_err());
        assert_eq!(writes.get(), 1);
        assert!(store.data.workspace_secrets.is_empty());
    }

}
