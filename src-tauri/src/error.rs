use std::fmt;

use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum StartupFailureReason {
    SessionBusMissing,
    SecretServiceUnavailable,
    SecretServiceLockedOrDenied,
    KeyEntryMissing,
    EncryptedConfigKeyMissing,
    ConfigInvalidOrUnsupported,
    ConfigPermissionOrIo,
    UnknownSecureStorageFailure,
}

impl StartupFailureReason {
    pub(crate) const fn code(self) -> &'static str {
        match self {
            Self::SessionBusMissing => "session_bus_missing",
            Self::SecretServiceUnavailable => "secret_service_unavailable",
            Self::SecretServiceLockedOrDenied => "secret_service_locked_or_denied",
            Self::KeyEntryMissing => "key_entry_missing",
            Self::EncryptedConfigKeyMissing => "encrypted_config_key_missing",
            Self::ConfigInvalidOrUnsupported => "config_invalid_or_unsupported",
            Self::ConfigPermissionOrIo => "config_permission_or_io",
            Self::UnknownSecureStorageFailure => "unknown_secure_storage_failure",
        }
    }

    pub(crate) const fn user_message(self) -> &'static str {
        match self {
            Self::SessionBusMissing => "未检测到可用的用户 D-Bus 会话总线；原配置已保留。请从正常桌面登录会话启动应用后重试。",
            Self::SecretServiceUnavailable => "系统 Secret Service 暂不可用；原配置已保留。请确认桌面凭据服务可用后重试。",
            Self::SecretServiceLockedOrDenied => "系统凭据库已锁定或访问未获授权；原配置已保留。请解锁登录钥匙串或允许访问后重试。",
            Self::KeyEntryMissing => "系统凭据库中未找到所需密钥项；不会自动创建替代密钥，原配置已保留。",
            Self::EncryptedConfigKeyMissing => "原加密配置对应的系统密钥不存在；不会生成替代密钥或覆盖密文。请使用原系统账户及其凭据备份恢复。",
            Self::ConfigInvalidOrUnsupported => "加密配置格式无效、认证失败或版本不受支持；原文件已保留，禁止重置或明文降级。",
            Self::ConfigPermissionOrIo => "配置文件或目录当前不可安全访问；原配置已保留。请检查当前用户的文件所有权、权限和存储状态后重试。",
            Self::UnknownSecureStorageFailure => "配置存储暂不可用；应用已进入受限恢复模式。请修复系统凭据库或原配置后重试。原配置不会被重置或降级为明文。",
        }
    }
}

impl fmt::Display for StartupFailureReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.user_message())
    }
}

pub(crate) fn classify_keyring_error(error: &keyring::Error) -> StartupFailureReason {
    match error {
        keyring::Error::NoStorageAccess(_) => StartupFailureReason::SecretServiceLockedOrDenied,
        keyring::Error::NoEntry => StartupFailureReason::KeyEntryMissing,
        keyring::Error::PlatformFailure(_) | keyring::Error::NoDefaultStore => {
            #[cfg(target_os = "linux")]
            {
                if std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_none() {
                    StartupFailureReason::SessionBusMissing
                } else {
                    StartupFailureReason::SecretServiceUnavailable
                }
            }
            #[cfg(not(target_os = "linux"))]
            {
                StartupFailureReason::UnknownSecureStorageFailure
            }
        }
        _ => StartupFailureReason::UnknownSecureStorageFailure,
    }
}

#[derive(Debug, Error)]
pub enum AppError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("{0}")]
    StartupStorage(StartupFailureReason),
    #[error("{0}")]
    Message(String),
}

impl AppError {
    pub(crate) fn startup_storage(reason: StartupFailureReason) -> Self {
        Self::StartupStorage(reason)
    }

    pub(crate) fn startup_failure_reason(&self) -> StartupFailureReason {
        match self {
            Self::StartupStorage(reason) => *reason,
            Self::Io(_) => StartupFailureReason::ConfigPermissionOrIo,
            Self::Json(_) => StartupFailureReason::ConfigInvalidOrUnsupported,
            Self::Message(message) => classify_storage_message(message),
        }
    }
}

fn classify_storage_message(message: &str) -> StartupFailureReason {
    if message.starts_with("配置加密密钥不存在")
        || message.starts_with("配置加密密钥丢失")
    {
        StartupFailureReason::EncryptedConfigKeyMissing
    } else if message.starts_with("加密配置格式无效")
        || message.starts_with("配置文件 ")
        || message.starts_with("配置版本 ")
        || message.starts_with("配置超过安全大小限制")
        || message.starts_with("配置文件不能是符号链接")
    {
        StartupFailureReason::ConfigInvalidOrUnsupported
    } else {
        StartupFailureReason::UnknownSecureStorageFailure
    }
}

impl serde::Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn startup_reason_codes_are_stable_and_messages_do_not_echo_backend_errors() {
        let reason = StartupFailureReason::SecretServiceLockedOrDenied;
        assert_eq!(reason.code(), "secret_service_locked_or_denied");
        assert!(!reason.user_message().contains("BadEncoding"));
        assert!(!reason.user_message().contains("fixture-secret"));
    }

    #[test]
    fn known_configuration_failures_are_classified_without_returning_the_original_text() {
        let missing = AppError::Message("配置加密密钥不存在；fixture-secret-must-not-leak".into());
        assert_eq!(missing.startup_failure_reason(), StartupFailureReason::EncryptedConfigKeyMissing);
        let invalid = AppError::Message("配置版本 99 高于当前支持版本 1".into());
        assert_eq!(invalid.startup_failure_reason(), StartupFailureReason::ConfigInvalidOrUnsupported);
    }
}
