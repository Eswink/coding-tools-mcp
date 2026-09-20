//! User-selectable durations are seconds, never a client-side refresh timer.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum NewChatAdmission {
    #[default]
    Review,
    LocalWindow,
    DenyNew,
}

impl NewChatAdmission {
    fn is_review(value: &Self) -> bool {
        *value == Self::Review
    }

    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Review => "review",
            Self::LocalWindow => "local_window",
            Self::DenyNew => "deny_new",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct SessionPolicy {
    pub exclusive: bool,
    pub access_token_ttl_seconds: u64,
    pub refresh_session_ttl_seconds: u64,
    pub chat_lease_ttl_seconds: u64,
    /// Zero disables idle expiry. Refresh requests never count as chat activity.
    pub chat_idle_timeout_seconds: u64,
    /// Controls creation of brand-new local chat-approval requests only.
    ///
    /// The backward-compatible Review default is omitted on disk so an
    /// operator can return all workspaces to Review before downgrading to a
    /// pre-ISSUE-010 binary whose strict SessionPolicy rejects unknown fields.
    #[serde(default, skip_serializing_if = "NewChatAdmission::is_review")]
    pub new_chat_admission: NewChatAdmission,
}
impl Default for SessionPolicy {
    fn default() -> Self {
        Self { exclusive: true, access_token_ttl_seconds: 3600,
            refresh_session_ttl_seconds: 30 * 86400, chat_lease_ttl_seconds: 86400,
            chat_idle_timeout_seconds: 0, new_chat_admission: NewChatAdmission::Review }
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
        assert_eq!(p.chat_idle_timeout_seconds, 0);
        assert_eq!(p.new_chat_admission, NewChatAdmission::Review);
        p.validate().unwrap();
    }
    #[test]
    fn review_default_is_omitted_for_bounded_downgrade_compatibility() {
        let review = SessionPolicy::default();
        let encoded = serde_json::to_value(&review).unwrap();
        assert!(
            encoded.get("new_chat_admission").is_none(),
            "review default must not make old strict SessionPolicy reject the file: {encoded}"
        );

        let mut gated = review;
        gated.new_chat_admission = NewChatAdmission::LocalWindow;
        let encoded = serde_json::to_value(&gated).unwrap();
        assert_eq!(encoded["new_chat_admission"], "local_window");
    }

    #[test]
    fn new_chat_admission_is_backward_compatible_and_strict() {
        for (raw, expected) in [
            (r#"{"new_chat_admission":"review"}"#, NewChatAdmission::Review),
            (r#"{"new_chat_admission":"local_window"}"#, NewChatAdmission::LocalWindow),
            (r#"{"new_chat_admission":"deny_new"}"#, NewChatAdmission::DenyNew),
        ] {
            let policy: SessionPolicy = serde_json::from_str(raw).unwrap();
            assert_eq!(policy.new_chat_admission, expected);
        }
        assert!(serde_json::from_str::<SessionPolicy>(
            r#"{"new_chat_admission":"allow_everything"}"#
        ).is_err());
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
