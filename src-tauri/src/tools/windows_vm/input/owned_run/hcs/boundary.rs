//! Data/decision helpers only. No handles, grants or retirement issuer.
use std::time::Instant;

pub(super) fn after_operation_checkpoint(
    deadline: Instant,
    cancelled: bool,
) -> Result<(), &'static str> {
    if cancelled || Instant::now() >= deadline {
        Err("WINDOWS_HCS_CREATE_CANCELLED_AFTER_ALLOCATION")
    } else {
        Ok(())
    }
}

/// Each unit must come from a checked copy into initialized local storage.
/// Stop at NUL: the reader is never asked for allocation padding after it.
pub(super) fn copied_utf16_prefix<R: FnMut(usize) -> Result<u16, &'static str>>(
    allocation_units: usize,
    deadline: Instant,
    mut reader: R,
) -> Result<String, &'static str> {
    if allocation_units == 0 || allocation_units > super::status::MAX_STATUS_BYTES / 2 {
        return Err("WINDOWS_HCS_EXIT_ALLOCATION_UNCONFIRMED");
    }
    let mut units = Vec::new();
    for index in 0..allocation_units {
        if Instant::now() >= deadline {
            return Err("WINDOWS_HCS_EXIT_DOCUMENT_DEADLINE");
        }
        let unit = reader(index)?;
        if Instant::now() >= deadline {
            return Err("WINDOWS_HCS_EXIT_DOCUMENT_DEADLINE");
        }
        if unit == 0 {
            return String::from_utf16(&units).map_err(|_| "WINDOWS_HCS_EXIT_DOCUMENT_REJECTED");
        }
        units.push(unit);
    }
    Err("WINDOWS_HCS_EXIT_DOCUMENT_REJECTED")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn allocated_operation_checkpoint_rejects_current_cancel_or_expiry() {
        let later = Instant::now() + Duration::from_secs(1);
        assert!(after_operation_checkpoint(later, true).is_err());
        assert!(after_operation_checkpoint(Instant::now(), false).is_err());
        assert!(after_operation_checkpoint(later, false).is_ok());
    }

    #[test]
    fn nul_stops_before_any_uninitialized_or_inaccessible_padding() {
        let mut reads = Vec::new();
        let result = copied_utf16_prefix(100, Instant::now() + Duration::from_secs(1), |i| {
            reads.push(i);
            match i {
                0 => Ok('x' as u16),
                1 => Ok(0),
                _ => panic!("padding must never be read"),
            }
        });
        assert_eq!(result.unwrap(), "x");
        assert_eq!(reads, vec![0, 1]);
    }

    #[test]
    fn failed_short_unterminated_or_invalid_utf16_copy_rejects() {
        let deadline = Instant::now() + Duration::from_secs(1);
        assert!(copied_utf16_prefix(2, deadline, |_| Err("COPY_UNKNOWN")).is_err());
        assert!(copied_utf16_prefix(2, deadline, |_| Ok('x' as u16)).is_err());
        assert!(copied_utf16_prefix(2, deadline, |i| Ok(if i == 0 { 0xd800 } else { 0 })).is_err());
        assert!(copied_utf16_prefix(0, deadline, |_| unreachable!()).is_err());
        assert!(copied_utf16_prefix(32_769, deadline, |_| unreachable!()).is_err());
    }

    #[test]
    fn expired_reader_is_never_called() {
        assert!(copied_utf16_prefix(2, Instant::now(), |_| {
            panic!("expired reader cannot run")
        })
        .is_err());
    }
}
