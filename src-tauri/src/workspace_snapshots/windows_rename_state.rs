//! Completion classification is separate so timeout cases can be tested without I/O.
pub(crate) const PENDING: i32 = 0x103;
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Completion {
    Complete,
    Failed,
    Uncertain,
}
pub(crate) fn classify(
    returned: i32,
    wait_status: Option<u32>,
    read_io_status: impl FnOnce() -> i32,
) -> Completion {
    if returned == PENDING && wait_status != Some(0) {
        // Never inspect memory the operating system may still be modifying.
        return Completion::Uncertain;
    }
    if returned != 0 && returned != PENDING {
        return Completion::Failed;
    }
    match read_io_status() {
        PENDING => Completion::Uncertain,
        0 => Completion::Complete,
        _ => Completion::Failed,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn timeout_or_failed_wait_never_reads_pending_memory() {
        for wait in [None, Some(258), Some(u32::MAX)] {
            assert_eq!(
                classify(PENDING, wait, || panic!("I/O memory must remain untouched")),
                Completion::Uncertain
            );
        }
        assert_eq!(
            classify(0xc0000043u32 as i32, None, || panic!(
                "Immediate failure needs no I/O status"
            )),
            Completion::Failed
        );
    }
    #[test]
    fn signaled_handle_is_not_sufficient_for_completion() {
        assert_eq!(
            classify(PENDING, Some(0), || PENDING),
            Completion::Uncertain
        );
        assert_eq!(classify(PENDING, Some(0), || 0), Completion::Complete);
        assert_eq!(
            classify(PENDING, Some(0), || 0xc0000043u32 as i32),
            Completion::Failed
        );
        assert_eq!(classify(0, None, || PENDING), Completion::Uncertain);
        assert_eq!(classify(0, None, || 0), Completion::Complete);
    }
}
