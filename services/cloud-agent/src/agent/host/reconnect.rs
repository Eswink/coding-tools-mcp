//! Reconnect policy for the always-on live Agent (S1).
//! Pure classification and pacing only: no I/O, no wall clock, no authority.
use crate::AgentError;

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AgentError::*;

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
