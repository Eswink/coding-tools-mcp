//! Reconnect policy for the always-on live Agent (S1).
//! Pure classification and pacing only: no I/O, no wall clock, no authority.
use crate::AgentError;
use std::time::Duration;

/// What the supervisor may do after a session ends with an error.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryClass {
    /// Transient: back off and reconnect. Never replays work (the journal and
    /// the cloud admission ledger decide that, not this loop).
    Retryable,
    /// A person must act (re-import credentials, trust the CA, review the
    /// journal). Retrying cannot help and would only hammer the gateway.
    NeedsOperator,
    /// Internal invariant failure. Stop and surface it; never loop.
    Fatal,
}

/// Total over `AgentError`; deliberately no wildcard arm so a new variant must
/// be classified consciously.
pub fn classify_retry(error: AgentError) -> RetryClass {
    use AgentError::*;
    match error {
        Transport | LocalAuthority | Capacity | Protocol | ExecutionUnknown => {
            RetryClass::Retryable
        }
        Configuration | Credentials | Journal | Authentication | Tls => RetryClass::NeedsOperator,
        Arguments | Cancelled | Exhausted | Duplicate => RetryClass::Fatal,
    }
}

/// Base delay before reconnect attempt `attempt` (1-based): 1s, 2s, 4s .. 30s cap.
pub fn backoff_base(attempt: u32) -> Duration {
    Duration::from_secs((1u64 << attempt.saturating_sub(1).min(5)).min(30))
}
/// Base delay plus 0..=25% jitter. `jitter_permille` is clamped to 0..=1000.
pub fn backoff_delay(attempt: u32, jitter_permille: u64) -> Duration {
    let base = backoff_base(attempt);
    base + base * (jitter_permille.min(1000) as u32) / 4000
}
/// Injectable randomness so reconnect pacing is deterministic under test.
pub trait Jitter: Send + Sync + 'static {
    /// A value in 0..=1000.
    fn permille(&self) -> u64;
}
/// Production source: OS CSPRNG. Never needs to be secret, only decorrelated.
pub struct SystemJitter;
impl Jitter for SystemJitter {
    fn permille(&self) -> u64 {
        use ring::rand::SecureRandom;
        let mut b = [0u8; 2];
        if ring::rand::SystemRandom::new().fill(&mut b).is_err() {
            return 500;
        }
        u64::from(u16::from_le_bytes(b)) * 1000 / u64::from(u16::MAX)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AgentError::*;

    #[test]
    fn backoff_doubles_from_one_second_and_caps_at_thirty() {
        let secs: Vec<u64> = (1..=9).map(|n| backoff_base(n).as_secs()).collect();
        assert_eq!(secs, [1, 2, 4, 8, 16, 30, 30, 30, 30]);
        assert_eq!(backoff_base(0).as_secs(), 1);
        assert_eq!(backoff_base(u32::MAX).as_secs(), 30);
    }
    #[test]
    fn jitter_adds_at_most_a_quarter_and_never_subtracts() {
        assert_eq!(backoff_delay(1, 0), Duration::from_secs(1));
        assert_eq!(backoff_delay(1, 1000), Duration::from_millis(1250));
        assert_eq!(backoff_delay(6, 0), Duration::from_secs(30));
        assert_eq!(backoff_delay(6, 1000), Duration::from_millis(37_500));
        assert_eq!(backoff_delay(6, 9_999_999), Duration::from_millis(37_500));
    }
    #[test]
    fn system_jitter_stays_in_range_and_varies() {
        let j = SystemJitter;
        let samples: Vec<u64> = (0..64).map(|_| j.permille()).collect();
        assert!(samples.iter().all(|v| *v <= 1000));
        assert!(samples.iter().any(|v| *v != samples[0]));
    }

    #[test]
    fn recoverable_errors_are_retryable() {
        for e in [
            Transport,
            LocalAuthority,
            Capacity,
            Protocol,
            ExecutionUnknown,
        ] {
            assert_eq!(classify_retry(e), RetryClass::Retryable, "{e:?}");
        }
    }
    #[test]
    fn operator_fixable_errors_stop_retrying() {
        for e in [Configuration, Credentials, Journal, Authentication, Tls] {
            assert_eq!(classify_retry(e), RetryClass::NeedsOperator, "{e:?}");
        }
    }
    #[test]
    fn internal_invariant_errors_are_fatal() {
        for e in [Arguments, Cancelled, Exhausted, Duplicate] {
            assert_eq!(classify_retry(e), RetryClass::Fatal, "{e:?}");
        }
    }
    #[test]
    fn classification_is_total_over_agent_error() {
        // Adding an AgentError variant must force a conscious retry decision here.
        fn exhaustive(e: crate::AgentError) -> RetryClass {
            match e {
                Transport | LocalAuthority | Capacity | Protocol | ExecutionUnknown => {
                    RetryClass::Retryable
                }
                Configuration | Credentials | Journal | Authentication | Tls => {
                    RetryClass::NeedsOperator
                }
                Arguments | Cancelled | Exhausted | Duplicate => RetryClass::Fatal,
            }
        }
        for e in [
            Arguments,
            Configuration,
            Credentials,
            Journal,
            Protocol,
            Authentication,
            Tls,
            Transport,
            Exhausted,
            Cancelled,
            LocalAuthority,
            Capacity,
            Duplicate,
            ExecutionUnknown,
        ] {
            assert_eq!(classify_retry(e), exhaustive(e));
        }
    }
}
