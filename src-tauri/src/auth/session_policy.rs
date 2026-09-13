//! User-selectable durations are seconds, never a client-side refresh timer.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct SessionPolicy {
    pub exclusive: bool,
    pub access_token_ttl_seconds: u64,
    pub refresh_session_ttl_seconds: u64,
    pub chat_lease_ttl_seconds: u64,
    /// Zero disables idle expiry. Refresh requests never count as chat activity.
    pub chat_idle_timeout_seconds: u64,
}
impl Default for SessionPolicy {
    fn default() -> Self {
        Self { exclusive: true, access_token_ttl_seconds: 3600,
            refresh_session_ttl_seconds: 30 * 86400, chat_lease_ttl_seconds: 86400,
            chat_idle_timeout_seconds: 0 }
    }
}
impl SessionPolicy {
    pub fn validate(&self) -> Result<(), String> {
        for (name, value, min, max) in [
            ("access_token_ttl_seconds", self.access_token_ttl_seconds, 300, 28800),
            ("refresh_session_ttl_seconds", self.refresh_session_ttl_seconds, 86400, 90 * 86400),
            ("chat_lease_ttl_seconds", self.chat_lease_ttl_seconds, 3600, 30 * 86400),
        ] {
            if !(min..=max).contains(&value) { return Err(format!("{name} 必须为 {min}..{max} 秒的整数")); }
        }
        if self.chat_idle_timeout_seconds != 0 && !(1800..=86400).contains(&self.chat_idle_timeout_seconds) {
            return Err("chat_idle_timeout_seconds 必须为 0（关闭）或 1800..86400 秒".into());
        }
        if self.chat_idle_timeout_seconds > self.chat_lease_ttl_seconds {
            return Err("空闲时限不得大于聊天授权时限".into());
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_config_uses_safe_long_development_defaults() {
        let p: SessionPolicy = serde_json::from_str("{}").unwrap();
        assert_eq!(p, SessionPolicy::default()); assert!(p.exclusive);
        assert_eq!(p.chat_idle_timeout_seconds, 0); p.validate().unwrap();
    }
    #[test]
    fn rejects_invalid_units_types_ranges_and_unknown_fields() {
        for raw in [r#"{"access_token_ttl_seconds":1.5}"#, r#"{"access_token_ttl_seconds":-1}"#,
            r#"{"access_token_ttl_seconds":"60"}"#, r#"{"refresh_interval":60}"#] {
            assert!(serde_json::from_str::<SessionPolicy>(raw).is_err());
        }
        for key in ["access_token_ttl_seconds", "refresh_session_ttl_seconds", "chat_lease_ttl_seconds"] {
            for n in [0, u64::MAX] {
                let mut v = serde_json::json!({}); v[key] = n.into();
                assert!(serde_json::from_value::<SessionPolicy>(v).unwrap().validate().is_err());
            }
        }
        let mut p = SessionPolicy::default(); p.chat_idle_timeout_seconds = 1; assert!(p.validate().is_err());
        p.chat_idle_timeout_seconds = 7200; p.chat_lease_ttl_seconds = 3600; assert!(p.validate().is_err());
    }
}
